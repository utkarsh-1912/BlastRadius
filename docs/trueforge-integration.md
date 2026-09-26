# TrueForge: Integration

How Blast Radius is wired *into* TrueForge — the agent manifest, the MCP tool layer, and the approval gate. For the client code that talks to TrueForge's HTTP API, see [trueforge-implementation.md](trueforge-implementation.md). For how to actually run it, see [trueforge-setup.md](trueforge-setup.md).

## Architecture

```
 Blast Radius API (FastAPI)
         |
         |  exec_python(script)            [server/agent/trueforge_client.py]
         v
    TrueForge  ────────────────────────────────────────────────────┐
     |    |                                                        |
     |    | registered agent: "blast-radius"                       |
     |    v          [agent/blast-radius.agent.json]                |
     |  MCP tool call (list_roles, get_role_policies,               |
     |   revoke_permissions, ...)                                   |
     |    v                                                         |
     |  blast-radius-aws-iam MCP server        sandbox exec tool ───┘
     |  [integrations/aws-iam-mcp/server.py]   (Daytona; runs
     |    |                                     sandbox_code.py's
     |    v                                     rendered script)
     |  AWS IAM + CloudTrail (boto3)
     |    (real account, or a local moto_server)
     v
  require_approval_for_tools: ["revoke_permissions"]
  → TrueForge itself pauses the turn and waits for a human
    `user.tool_approval` decision before this tool can run.
```

Two TrueForge-facing pieces exist side by side, and it's worth being precise about which is which:

1. **The MCP server** (`integrations/aws-iam-mcp/server.py`) — this is what the *agent inside TrueForge* calls when it decides, on its own, to read IAM state or (after approval) revoke a permission. It's a `FastMCP` "streamable-http" server exposing 7 tools.
2. **The sandbox exec path** (`trueforge_client.exec_python`) — this is what *Blast Radius's own backend* calls to ask TrueForge to run one specific, pre-written replay script inside its sandbox. It's a separate, orthogonal use of TrueForge (the compute-in-a-sandbox capability), not mediated by the MCP server at all.

Both are optional in the sense that the app degrades gracefully without either (see "Fallback behavior" below) — but only the MCP path is what actually makes this a **hackathon-eligible** "agent that acts," since it's what lets a real TrueForge agent turn read real AWS state and be gated before a real write.

## The MCP tool layer (`integrations/aws-iam-mcp/server.py`)

Seven tools, deliberately narrow (mirrors the earlier BuildPlan project's OpenProject tool layer):

| Tool | Read/Write | Purpose |
|---|---|---|
| `list_roles` | read | List IAM role names (optional prefix filter) |
| `get_role_policies` | read | A role's attached managed + inline policy statements |
| `get_cloudtrail_history` | read | Real (or labeled demo) historical API calls for a role |
| `find_unused_permissions` | read | Candidate permissions absent from CloudTrail within a lookback window |
| `compute_blast_radius` | read (pure compute) | The core safety check: replay real history against a hypothetical policy, using two independent evaluators |
| `revoke_permissions` | **write — the only one** | Surgically remove named actions from one policy |
| `verify_role_state` | read | Re-read a role after a commit and confirm removed actions are actually gone |

It imports directly from `server/` (`aws_integration.client`, `blast_radius.candidates`, etc.) — same Python process' dependency tree as the FastAPI backend, just exposed over MCP instead of REST. Run standalone: `python integrations/aws-iam-mcp/server.py` (needs `IAM_MCP_TOKEN`, `AWS_REGION`/credentials in `.env`).

## The agent manifest (`agent/blast-radius.agent.json`)

```json
{
  "name": "blast-radius",
  "manifest": {
    "model": { "name": "${MODEL_FQN}", ... },
    "instructions": "... 9-step procedure ...",
    "mcp_servers": [{
      "name": "blast-radius-aws-iam",
      "enable_tools": ["list_roles", "get_role_policies", "get_cloudtrail_history",
                        "find_unused_permissions", "compute_blast_radius",
                        "revoke_permissions", "verify_role_state"],
      "require_approval_for_tools": ["revoke_permissions"],
      "preload": true
    }],
    "skills": [{ "name": "blast-radius-analysis" }, { "name": "approval" }],
    "config": { "sandbox": { "enabled": true }, "ask_user_questions": { "enabled": false }, ... }
  }
}
```

The important line is `require_approval_for_tools: ["revoke_permissions"]`. This is enforced **by the TrueForge harness itself**, not by the agent's own instructions: when the agent decides to call `revoke_permissions`, TrueForge intercepts the call, emits a `tool.approval_required` event, and pauses the turn (`turn.update` with `state.status == "paused"`) until a `user.tool_approval` input item resumes it with `{"status": "allow"}` or `{"status": "deny"}`. The agent has no code path that bypasses this — it isn't a prompt instruction that a cleverly-worded request could talk it out of.

`${MODEL_FQN}` is a placeholder substituted at registration time by `scripts/setup_trueforge.py` (e.g. `anthropic/claude-sonnet-5`), from whichever model provider it configured.

Instructions and skills (`agent/skills/blast-radius-analysis.md`, `agent/skills/approval.md`) tell the agent the *procedure* (understand → retrieve → identify candidates → compute blast radius for each → present both the safe and flagged lists → stop → wait for approval → commit → verify) — but the procedure being followed correctly is not what makes this safe. The `require_approval_for_tools` gate is what makes it safe, independent of whether the agent follows instructions perfectly.

## Agent honesty: the anti-fabrication rule

Found live, the hard way: asked to review a role that didn't exist in the AWS account it was pointed at, the agent — with the MCP connection not actually live at the time — didn't say "role not found." It fabricated an entire plausible-looking report: invented service names, last-accessed dates, unused-permission counts, and a synthesized least-privilege policy JSON, none of it backed by any real tool call. That is the single worst failure mode possible for a tool whose entire premise is "never trust invented data, only real evidence" — worse than the tool simply not working, because it looks like it worked.

`agent/blast-radius.agent.json`'s instructions now open with an explicit, unconditional rule addressing exactly this: every fact the agent states must trace back to an actual tool call's actual returned content in that turn; if `list_roles`/`get_role_policies` returns no match, an empty result, or an error, the agent must say so plainly and stop — never invent example data, mockup dashboards, or "here's what it would look like" content, under any framing, regardless of how the request is phrased. This sits above the numbered procedure, not folded into step 2, because it needs to override the model's default instinct to be helpful and produce *a* nice-looking answer even when it has none.

If you ever see this again, it means the instructions weren't actually applied to that session (e.g. `setup_trueforge.py` wasn't re-run after a manifest change, or the session started before it was) — re-run setup and start a fresh session, don't assume the rule is unenforceable.

## Fallback behavior (what happens without a live TrueForge)

| Missing | Effect |
|---|---|
| `TRUEFORGE_BASE_URL` unset, or unreachable | `main.py`'s `_build_orchestrator()` sets `trueforge=None`; every candidate replays in-process instead of in a sandbox (`agent/orchestrator.py: _sandbox_replay`) — logged plainly, e.g. `"TrueForge sandbox unavailable"`. |
| Agent not registered / no sandbox provider (Daytona) configured | `exec_python()` raises `TrueForgeUnavailable` on the first candidate; the orchestrator's circuit breaker (`_trueforge_broken`) stops retrying for the rest of that review and falls back locally for every subsequent candidate. |
| Real AWS policy simulator unreachable (e.g. moto, which doesn't implement `SimulateCustomPolicy`) | Independent of TrueForge entirely — `agent/orchestrator.py: _validate` falls back to `blast_radius.reference_evaluator.ReferenceEvaluator`, a second, differently-implemented local evaluator. See [../docs/architecture.md](../docs/architecture.md#two-evaluators-and-what-independent-actually-means-here). |

None of these fallbacks are silent — every one produces a `kind="warn"` line in the agent timeline the UI shows, and the API response's `sandbox_used` / `validator_source` fields say exactly what actually ran.

## Known gaps / what to verify at the venue

This project was iterated against a real, running TrueForge instance (not just mocks), and several integration bugs it exposed are already fixed — see the [changelog below](#fixed-against-a-live-instance). What's still unverified, because it needs a fully configured Daytona sandbox provider that wasn't available while building this: a live turn actually reaching the sandbox `exec` tool and returning real, parseable stdout. The event-parsing logic in `_extract_exec_stdout` (`server/agent/trueforge_client.py`) is written directly from the documented event schema but has not itself been exercised end to end. Before the actual demo, with a real model + Daytona configured:

1. `python scripts/setup_trueforge.py` — confirm it reports every step `✓`.
2. Trigger one review through the UI or `POST /api/review` and check the agent timeline for `"Executing Python in TrueForge sandbox"` / `sandbox_used: true` in the response, rather than a `"TrueForge sandbox unavailable"` warning.
3. If it still falls back, check TrueForge's own session/turn UI for that session — the raw events will show exactly where the turn stalled or what the agent actually did instead of calling `exec`.

### Fixed against a live instance

Real bugs only a live TrueForge instance could have exposed, found and fixed while building this:

- `create_session`'s request body used the wrong field name (`agent_name` instead of `agent`) — caught via a real `400 Invalid input` response.
- `exec_python()` didn't exist at all on `TrueForgeClient` before this project needed it — it was a documented gap, not a bug, until it got implemented for real (session/turn/event-parsing) once a live instance was available to test against.
- `scripts/setup_trueforge.py` never registered the agent's `skills` correctly — TrueForge expects skills pre-registered via a separate API this project doesn't use, so agent creation 422'd with `Unknown skill "..." — not configured` until the script was changed to inline skill content into the agent's instructions instead.
- A WSL/Windows networking split (TrueForge in WSL, the MCP server on Windows) produced `ECONNREFUSED` even with everything actually running — see [wsl-networking.md](wsl-networking.md), a page dedicated to this because it's easy to misdiagnose as "the server crashed."
- The agent fabricating an entire fake report when it had no real tool access — see ["Agent honesty" above](#agent-honesty-the-anti-fabrication-rule).
