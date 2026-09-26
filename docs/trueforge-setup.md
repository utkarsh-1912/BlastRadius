# TrueForge: Setup Instructions

Step-by-step to get Blast Radius actually running *on* TrueForge (not just in local-fallback mode). For what each piece does, see [trueforge-integration.md](trueforge-integration.md) and [trueforge-implementation.md](trueforge-implementation.md). For AWS credentials specifically, see [aws-setup.md](aws-setup.md).

## 0. Prerequisites

- Node.js (for `npx @truefoundry/trueforge`) — **on Windows, TrueForge runs inside WSL Ubuntu**, not natively. If you hit `ECONNREFUSED` talking to the MCP server despite it clearly running, that's almost certainly the WSL/Windows networking split — see [wsl-networking.md](wsl-networking.md), a dedicated page for this exact problem.
- Python env with `server/requirements.txt` installed (this pins `mcp<2` and `starlette>=0.40,<0.47` deliberately — see the comments in `requirements.txt` if a fresh `pip install` of something else drags in incompatible versions)
- A model API key: `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` (make sure `MODEL_ID` actually matches whichever one you set — `MODEL_ID=claude-sonnet-5` with `OPENAI_API_KEY` set will try to register a nonexistent OpenAI model and fail)
- A sandbox provider key for real sandbox execution: `DAYTONA_API_KEY` (get one at app.daytona.io → **API Keys**). The key needs three specific scopes checked at creation: `write:sandboxes`, `write:snapshots`, `delete:snapshots` — a key missing any of these fails registration with a clear `422` naming exactly which scope is missing; if your dashboard doesn't let you edit an existing key's scopes, just create a new one with all three checked.
- AWS credentials (real account, or `moto_server`) — see [aws-setup.md](aws-setup.md)

## 1. Start TrueForge

```bash
npx @truefoundry/trueforge@latest
```

Runs on `http://localhost:8790` by default (local mode, SQLite, no auth). Leave this running in its own terminal.

**If you'll point it at `localhost` services** (the `blast-radius-aws-iam` MCP server, or a local `moto_server`), TrueForge's outbound SSRF guard blocks `localhost` by default. Start it with:

```bash
OUTBOUND_URL_ALLOWED_HOSTS='["localhost","127.0.0.1"]' npx @truefoundry/trueforge@latest
```

## 2. Fill in `.env`

```bash
cp .env.example .env
```

At minimum for TrueForge specifically:

```env
TRUEFORGE_BASE_URL=http://localhost:8790
DAYTONA_API_KEY=<your-key>              # for real sandbox execution
ANTHROPIC_API_KEY=<your-key>            # or OPENAI_API_KEY
MODEL_ID=claude-sonnet-5                # or your preferred model id
IAM_MCP_TOKEN=<any random 32+ char string>
IAM_MCP_PORT=8792
```

`clean_blank_env()` (`server/env_utils.py`) means it's safe to leave optional fields blank in `.env` — a blank `AWS_PROFILE=` line, for instance, is treated as unset rather than crashing boto3. See [trueforge-implementation.md](trueforge-implementation.md) if you're curious why that matters.

## 3. Start the MCP tool layer

```bash
python integrations/aws-iam-mcp/server.py
```

Runs on `http://localhost:8792/mcp` by default. This must be running *before* step 4 registers it, and needs to keep running for the agent to actually call its tools later.

## 4. Register everything in TrueForge

```bash
python scripts/setup_trueforge.py
```

This is idempotent (safe to re-run) and does four things, each printed with ✓/!/✗:

1. **Model provider** — registers `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` under a resource slug, producing a fully-qualified model name (e.g. `anthropic/claude-sonnet-5`).
2. **Sandbox provider** — registers `DAYTONA_API_KEY` (skipped with a warning if unset — assumes you configured it once in the TrueForge UI instead).
3. **MCP server** — registers `blast-radius-aws-iam` at `http://localhost:${IAM_MCP_PORT}/mcp` with header auth (`IAM_MCP_TOKEN`).
4. **Agent** — creates or updates the `blast-radius` agent from `agent/blast-radius.agent.json`, substituting `${MODEL_FQN}` with the model registered in step 1. `agent/blast-radius.agent.json` lists two skills (`blast-radius-analysis`, `approval`) under `manifest.skills`, but this step never registers them as TrueForge skills — TrueForge's `skills` field expects each one already registered separately via `PUT /settings/skills` (a git-backed manifest), which this project doesn't do. Instead, the script strips `skills` from the manifest and inlines each skill file's markdown directly into the agent's `instructions` before registering. You won't see a "skills" step in the output because of this — it happens silently as part of step 4, and the printed line says how many were inlined (`2 skill(s) inlined`).

If any step fails, the script prints a concrete fix (e.g. *"TrueForge blocks localhost by default. Restart it with: ..."*) and exits non-zero — fix the named issue and re-run.

## 5. Start the app

```bash
make api    # FastAPI backend, :8010
make web    # Next.js dashboard, :3000
```

`main.py`'s `_build_orchestrator()` only builds a `TrueForgeClient` if `TRUEFORGE_BASE_URL` is set *and* `reachable()` succeeds — so if TrueForge isn't up yet, the app still runs, just without sandbox execution (clearly logged per-run).

## 6. Verify it's actually using TrueForge, not the fallback

Two separate things are worth checking, and they can fail independently:

**A. The MCP connection** — TrueForge → Settings → MCP Servers → `blast-radius-aws-iam` should show **connected**, with all 7 tools listed. If it shows an error here, nothing downstream will work regardless of what the agent's instructions say — fix this first (see the Troubleshooting table below).

**B. That the agent is actually calling those tools**, not just that the connection exists. Open TrueForge's own chat UI directly (`http://localhost:8790`, not the Blast Radius dashboard), start a **new** session with the `blast-radius` agent, and send the demo request. Watch for real tool calls (`get_role_policies`, `get_cloudtrail_history`, `compute_blast_radius`) in the turn's steps — not the agent falling back to suggesting AWS CLI commands or exploring the sandbox filesystem for log files that don't exist. If it does either of those, the MCP connection likely wasn't live when that session started (a session can cache "no tools" from before you fixed the connection) — start a genuinely new session after confirming (A).

Separately, for the dashboard specifically (`POST /api/review` or the UI), check:
- The response's `sandbox_used` field is `true` (not `false`).
- The agent timeline does **not** contain `"TrueForge sandbox unavailable"`.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `setup_trueforge.py` fails at "model provider" | No API key in `.env`, or `MODEL_ID` doesn't match the provider whose key is set (e.g. an Anthropic model name with `OPENAI_API_KEY`) | Set the matching key + `MODEL_ID` pair |
| `setup_trueforge.py` fails at "sandbox (Daytona)" with a `422` naming missing scopes | The Daytona API key lacks `write:sandboxes`/`write:snapshots`/`delete:snapshots` | Create a new key at app.daytona.io → API Keys with all three checked |
| `setup_trueforge.py` fails at "agent" with `Unknown skill "..." — not configured` | An older build of `setup_trueforge.py` that referenced skills instead of inlining them (fixed — pull latest) | `git pull`, re-run; current script inlines skill files instead of registering them (see step 4 above) |
| `setup_trueforge.py` fails at "mcp: blast-radius-aws-iam" with `Outbound URL blocked for host "localhost"` | TrueForge's SSRF guard | Restart TrueForge with `OUTBOUND_URL_ALLOWED_HOSTS='["localhost","127.0.0.1"]'` (see step 1) |
| `ECONNREFUSED 127.0.0.1:<port>` connecting to the MCP server, even though it's clearly running | TrueForge (in WSL) and the MCP server (on Windows) are on opposite sides of the WSL/Windows network boundary — not the same issue as the SSRF guard above | See the dedicated page: [wsl-networking.md](wsl-networking.md) |
| Every review logs `"TrueForge sandbox unavailable"` | Agent not registered, or no sandbox provider | Re-run `setup_trueforge.py`; check its output for `✗ sandbox (Daytona)` |
| The agent responds to a real request with plausible-looking but made-up data (fake service names, dates, numbers) | Was hit and fixed — see [trueforge-integration.md's "Agent honesty"](trueforge-integration.md#agent-honesty-the-anti-fabrication-rule) | Confirm you're on the current `agent/blast-radius.agent.json` (`git pull`, re-run `setup_trueforge.py`) — it now has an explicit rule against this |
| The agent responds with zero tool calls, e.g. suggesting AWS CLI commands or explaining concepts instead of using MCP tools | The MCP connection wasn't live when that session started | Confirm (A) above, then start a genuinely **new** session — an existing one can have cached "no tools available" |
| `400 Invalid input` creating a session | A schema mismatch between this client and your TrueForge version | Check `server/agent/trueforge_client.py: create_session` — the request body's field name (currently `agent`) may have changed between TrueForge versions; the error message names the offending field |
| A review takes 60+ seconds and then still falls back | TrueForge accepted the session/turn but never produced a terminal state within `exec_python`'s 20s timeout | Check the session directly in TrueForge's UI for what the agent turn actually did; consider raising `exec_python`'s `timeout_s` once you've confirmed it's just slow, not stuck |
