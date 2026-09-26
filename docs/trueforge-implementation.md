# TrueForge: Implementation

Where the TrueForge-facing code actually lives, and what each piece does.

## File map

| File | Role |
|---|---|
| [`server/agent/trueforge_client.py`](../server/agent/trueforge_client.py) | The only code that speaks HTTP to TrueForge. A thin REST client over `${TRUEFORGE_BASE_URL}/api/v1/...`. |
| [`server/blast_radius/sandbox_code.py`](../server/blast_radius/sandbox_code.py) | Renders the exact, self-contained Python script that gets executed inside the TrueForge sandbox for one candidate permission. |
| [`server/agent/orchestrator.py`](../server/agent/orchestrator.py) (`_sandbox_replay`, `_trueforge_broken`) | Calls `trueforge_client.exec_python()` for each candidate; falls back to an in-process local replay on any failure. |
| [`agent/blast-radius.agent.json`](../agent/blast-radius.agent.json) | The agent manifest registered *into* TrueForge (see [trueforge-integration.md](trueforge-integration.md)). |
| [`scripts/setup_trueforge.py`](../scripts/setup_trueforge.py) | Idempotent registration script: model provider, sandbox provider, MCP server, agent. |

## `TrueForgeClient` (`server/agent/trueforge_client.py`)

A dataclass wrapping `requests`, with three groups of methods:

**Setup-time (idempotent `PUT`/`POST`), used by `scripts/setup_trueforge.py`:**
- `put_model_provider(manifest)`, `put_sandbox_provider(manifest)`, `put_mcp_server(manifest)`
- `list_agents()` / `create_or_update_agent(name, description, manifest)`

**Runtime (sessions/turns/events):**
- `create_session(agent_name)` — `POST /sessions` with body `{"agent": agent_name}`
- `send_turn(session_id, message)` — `POST /sessions/{id}/turns` with a `user.message` input item
- `send_approval(session_id, tool_call_id, approve, reason)` — resumes a paused turn with a `user.tool_approval` input item
- `get_events(session_id)` / `get_turn(session_id, turn_id)` / `wait_for_turn(...)` — polls a turn to a terminal state (`done`/`error`/`cancelled`/`paused`)

**Sandbox execution:**
- `exec_python(script, agent_name=None, timeout_s=20.0)` — the method `orchestrator.py` actually calls. See below.

### How `exec_python` works

There is no dedicated "run this code" TrueForge API — sandbox execution only happens as a side effect of an agent's own tool use inside a turn. So `exec_python`:

1. Creates a session against the given agent (default: `blast-radius`, the one in `agent/blast-radius.agent.json`).
2. Sends one turn with an explicit instruction: *"Run EXACTLY the following Python script using the sandbox exec tool, verbatim, with no modification... just execute it and stop."* — with the script embedded as a fenced code block.
3. Polls the turn to completion (`wait_for_turn`, default 20s timeout).
4. Walks the turn's raw events (`get_events`) looking for a `model.message` event whose `tool_calls[i].tool_info` has `type == "truefoundry-system"` and `name == "exec"`, then finds the paired `tool.response` event (matched by `tool_call_id`) and returns its `content` as the sandbox's stdout.
5. **Any** failure at any step — session creation, an unregistered agent, no sandbox provider configured, a timeout, or an unexpected event shape — raises `TrueForgeUnavailable`. This is a single, uniform failure mode; the caller does not need to distinguish "TrueForge is down" from "the agent isn't registered" from "sandbox execution isn't wired up yet."

```python
# server/agent/orchestrator.py
def _sandbox_replay(self, run, candidate, all_stmts, events):
    if self.trueforge is not None and not self._trueforge_broken:
        try:
            script = render_sandbox_script(candidate, all_stmts, events)
            stdout = self.trueforge.exec_python(script)
            run.sandbox_used = True
            ...  # parse RESULT_JSON: line from stdout
        except TrueForgeUnavailable as e:
            self._trueforge_broken = True   # stop retrying for the rest of this review
            run.log("TrueForge sandbox unavailable", ..., kind="warn")
    return run_local_replay(candidate, all_stmts, events)  # local fallback
```

`_trueforge_broken` is a circuit breaker: the first failure in a review disables further TrueForge attempts for the rest of that review (a fresh `Orchestrator` is built per API request, so this never suppresses a retry on the *next* request) — without it, a review with N candidates pays TrueForge's failure latency N times instead of once.

## What's genuinely verified vs. best-effort

This session verified against a **real, running TrueForge instance** (not just moto/mocks):
- `reachable()` correctly detects a live instance and its `/capabilities` response.
- `create_session` was fixed mid-session from a wrong field name (`agent_name` → `agent`) after a real `400 Invalid input` response exposed the bug — see [trueforge-integration.md](trueforge-integration.md#known-gaps--what-to-verify-at-the-venue) for what that implies is still unverified.
- The `TrueForgeUnavailable` fallback path was exercised live multiple times and correctly falls back to a local replay with no crash and a clear log line.

**Not yet verified against a real instance** (no registered agent + no sandbox/model provider was available in this environment): a real turn that actually reaches the sandbox `exec` tool, gets a human approval prompt, and returns real stdout. The event-parsing logic in `_extract_exec_stdout` is written directly from the documented event schema (mirroring the reference `dress-rehearsal` project's `viewer/public/mapEvents.mjs`) but has not been exercised against a live sandbox execution. Treat it as the first thing to check at the hackathon venue once a model + Daytona are configured — see the setup doc's verification steps.
