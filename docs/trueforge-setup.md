# TrueForge: Setup Instructions

Step-by-step to get Blast Radius actually running *on* TrueForge (not just in local-fallback mode). For what each piece does, see [trueforge-integration.md](trueforge-integration.md) and [trueforge-implementation.md](trueforge-implementation.md).

## 0. Prerequisites

- Node.js (for `npx @truefoundry/trueforge`)
- Python env with `server/requirements.txt` installed
- A model API key: `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`
- A sandbox provider key for real sandbox execution: `DAYTONA_API_KEY` (get one at app.daytona.io — Sandboxes + Snapshots write scope)
- AWS credentials (real account, or `moto_server` — see the main [README](../README.md#setup))

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
4. **Agent** — creates or updates the `blast-radius` agent from `agent/blast-radius.agent.json`, substituting `${MODEL_FQN}` with the model registered in step 1.

If any step fails, the script prints a concrete fix (e.g. *"TrueForge blocks localhost by default. Restart it with: ..."*) and exits non-zero — fix the named issue and re-run.

## 5. Start the app

```bash
make api    # FastAPI backend, :8010
make web    # Next.js dashboard, :3000
```

`main.py`'s `_build_orchestrator()` only builds a `TrueForgeClient` if `TRUEFORGE_BASE_URL` is set *and* `reachable()` succeeds — so if TrueForge isn't up yet, the app still runs, just without sandbox execution (clearly logged per-run).

## 6. Verify it's actually using TrueForge, not the fallback

Run a review (UI or `POST /api/review`) and check:

- The response's `sandbox_used` field is `true` (not `false`).
- The agent timeline does **not** contain `"TrueForge sandbox unavailable"`.
- In TrueForge's own UI (`http://localhost:8790`), the `blast-radius` agent should show a new session with a turn whose events include an `exec` tool call.

If it still falls back, see [trueforge-integration.md's "Known gaps" section](trueforge-integration.md#known-gaps--what-to-verify-at-the-venue) — this exact path (a live turn reaching the sandbox `exec` tool and returning parseable output) was not exercised end-to-end in this session, since no model/Daytona credentials were available here.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `setup_trueforge.py` fails at "model provider" | No API key in `.env` | Set `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` |
| `setup_trueforge.py` fails at "mcp: blast-radius-aws-iam" with `Outbound URL blocked for host "localhost"` | TrueForge's SSRF guard | Restart TrueForge with `OUTBOUND_URL_ALLOWED_HOSTS='["localhost","127.0.0.1"]'` (see step 1) |
| Every review logs `"TrueForge sandbox unavailable"` | Agent not registered, or no sandbox provider | Re-run `setup_trueforge.py`; check its output for `✗ sandbox (Daytona)` |
| `400 Invalid input` creating a session | A schema mismatch between this client and your TrueForge version | Check `server/agent/trueforge_client.py: create_session` — the request body's field name (currently `agent`) may have changed between TrueForge versions; the error message names the offending field |
| A review takes 60+ seconds and then still falls back | TrueForge accepted the session/turn but never produced a terminal state within `exec_python`'s 20s timeout | Check the session directly in TrueForge's UI for what the agent turn actually did; consider raising `exec_python`'s `timeout_s` once you've confirmed it's just slow, not stuck |
