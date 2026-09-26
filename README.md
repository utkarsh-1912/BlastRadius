# Blast Radius

AI AWS IAM Access-Review Agent

Built for the **TrueFoundry × Polaris "Agents That Act" Hackathon** (Access Reviewer theme).

## Problem

AWS's own IAM Access Analyzer can tell you a permission's last-accessed timestamp — "unused for 118 days." That's a hint. It is not proof that removing it is safe. Every real IAM cleanup effort stalls on the same fear: *what if this one permission is actually used by something that only runs once a quarter?* So the stale permissions pile up, and "we'll clean up IAM later" never happens.

## Solution

Blast Radius doesn't ask an LLM to guess whether a permission is safe to remove. It **proves it**, by replaying every real historical API call the role ever made against a hypothetical policy with that permission removed — using two independently-written IAM policy evaluators that must both agree, on every single event, before anything is ever proposed for removal.

```
LLM / heuristic   = understand the request, explain the result
Local evaluator   = deterministic sandbox replay (no AWS credentials)
AWS evaluator     = independent, authoritative cross-check (real iam:SimulateCustomPolicy)
Human             = approval of the one consequential action (revoke)
AWS IAM           = system of record
```

The agent never personally decides a permission is safe. Two separately-coded policy evaluators decide that, by replaying real evidence — and nothing is revoked in AWS IAM without an explicit human click.

## What makes this different from "unused for 90 days"

AWS Access Analyzer (and every tool built on top of it) stops at: *this permission hasn't been called recently.* Blast Radius goes one step further and asks the harder question: **if we'd removed it 90 days ago, what would actually have broken?**

In the seeded demo, this produces a genuinely useful distinction a recency-only tool cannot make:

| Permission | Last used | AWS Access Analyzer would say | Blast Radius says |
|---|---|---|---|
| `dynamodb:DeleteTable` | never | "unused — candidate for removal" | **Safe** — zero historical evidence, ever |
| `sns:Publish` | 160 days ago | "unused — candidate for removal" | **Flagged, excluded** — replay proves that exact historical call (an incident alert) would now be denied, and nothing else grants it |

Both look identical to a recency-based tool. Only a replay against real history tells them apart — and a security tool that can't tell them apart either over-revokes (breaks something rare but real) or under-revokes (leaves everything, out of caution). Blast Radius does neither: it auto-proposes only what it can prove is truly inert, and hands the genuinely ambiguous cases to a human with the specific evidence attached.

## Architecture

```
 Next.js UI  <-->  Blast Radius API (FastAPI)  <-->  Orchestrator (agent/orchestrator.py)
                                                            |            |
                                                  TrueForge Agent   AWS IAM + CloudTrail
                                                 (sandbox + LLM)    (Blast Radius Tool Layer)
                                                            |            |
                                                  Local policy       Real AWS account
                                                  evaluator (no      (or a local moto_server
                                                  credentials)        for a live demo)
```

- **`server/blast_radius/`** — the deterministic core: a from-scratch IAM policy evaluator (`local_evaluator.py`, no AWS SDK, no credentials — this is what runs in the TrueForge sandbox), candidate identification (`candidates.py`), the replay simulator (`simulator.py`), a second, differently-implemented evaluator used only as a demo-mode fallback (`reference_evaluator.py`), and the independent validator (`validator.py`) that requires both evaluators to agree.
- **`server/aws_integration/`** — a small, controlled AWS client: `client.py` (IAM reads + the one gated write), `cloudtrail.py` (real CloudTrail lookups, or a clearly-labeled demo export for brand-new accounts), `simulate.py` (the real `iam:SimulateCustomPolicy` cross-check).
- **`server/agent/orchestrator.py`** — UNDERSTAND → RETRIEVE → IDENTIFY CANDIDATES → SANDBOX SIMULATE → VALIDATE → EXPLAIN → STOP → APPROVE → COMMIT → VERIFY. The only module allowed to call the write path, and only when a run's status is `awaiting_approval`.
- **`integrations/aws-iam-mcp/`** — the actual MCP server TrueForge calls ("Blast Radius AWS IAM Tool Layer"). Seven tools, one of them (`revoke_permissions`) gated by TrueForge's own approval mechanism.
- **`agent/blast-radius.agent.json`** — the TrueForge agent manifest: model, the gated MCP write tool, sandbox on.
- **`apps/web/`** — the Next.js dashboard: request input, live agent timeline, safe-vs-flagged results table, validation stats, and the approve/reject gate.

## Why TrueForge

Two things about the harness matter here, exactly as they did for this team's earlier BuildPlan project:

1. **Sandbox execution is enforced by the harness, not by agent discipline.** The replay script (`blast_radius/sandbox_code.py`) that decides whether a historical call would still succeed runs in an isolated sandbox with zero AWS credentials and no network access — it can compute, and nothing else.
2. **Approval is enforced by the harness, not by a prompt instruction.** `agent/blast-radius.agent.json` lists `revoke_permissions` under `require_approval_for_tools`. TrueForge pauses the turn and waits for an explicit `user.tool_approval` event before that tool can run.

For the full detail on this — split across three pages so implementation, wiring, and how-to-run-it don't get tangled together — see:

- **[docs/trueforge-implementation.md](docs/trueforge-implementation.md)** — the actual client code that talks to TrueForge (`server/agent/trueforge_client.py`), how sandbox execution is driven end to end, and what's genuinely verified vs. best-effort.
- **[docs/trueforge-integration.md](docs/trueforge-integration.md)** — how Blast Radius is wired *into* TrueForge: the agent manifest, the MCP tool layer, the approval gate, and fallback behavior when any piece isn't configured.
- **[docs/trueforge-setup.md](docs/trueforge-setup.md)** — step-by-step instructions to actually run it on a live TrueForge instance, plus a troubleshooting table from real issues hit while building this.

## Sandbox security

The sandbox that replays historical events has no `AWS_ACCESS_KEY_ID`, no AWS SDK network access, and no ability to call `revoke_permissions` (that tool lives on the MCP server, not in the sandbox). It reads a JSON export of the policy and the historical event log, computes, and prints JSON — nothing else.

## Human approval model

- The safe-to-remove list is generated, independently cross-validated by a second evaluator, and shown next to the flagged/excluded list — then the agent **stops**.
- `commit_and_verify()` (`server/agent/orchestrator.py`) refuses to run unless the run's status is `awaiting_approval`; the only caller is `POST /api/review/{id}/approve`, which only fires on the dashboard's **Approve & Revoke** button.
- On the TrueForge side, the same gate exists independently via `require_approval_for_tools`.
- `tests/test_no_revoke_before_approval.py` runs the full pipeline against a moto-mocked AWS account and asserts zero IAM writes happened before an explicit approve, then verifies a real approve → commit → verify cycle actually mutates and re-reads IAM state.

## Setup

### 1. Configure environment

```bash
cp .env.example .env
```

**No AWS account yet?** Run a local, fully-API-compatible mock instead — real boto3 calls, real IAM semantics, just not a real account:

```bash
pip install "moto[server]"
moto_server -p 5555
# in .env: AWS_ENDPOINT_URL=http://localhost:5555, AWS_ACCESS_KEY_ID=testing, AWS_SECRET_ACCESS_KEY=testing
```

**Have an AWS account?** Leave `AWS_ENDPOINT_URL` unset and configure credentials the normal way (`AWS_PROFILE`, or `aws configure`). A brand-new account's CloudTrail history will be thin, so `USE_DEMO_CLOUDTRAIL=true` (the default) uses a labeled historical export instead — flip it to `false` once your account has real history to replay against.

### 2. Seed the demo role

```bash
pip install -r server/requirements.txt
python scripts/seed_demo_iam.py
```

This creates `data-pipeline-role` with a realistic mix of permissions (some used, some genuinely dead, one used-but-stale) via real `iam:CreateRole`/`iam:PutRolePolicy` calls — against your real AWS account or the moto server, whichever `.env` points at.

### 3. Start TrueForge and register Blast Radius

```bash
npx @truefoundry/trueforge@latest         # in one terminal
python integrations/aws-iam-mcp/server.py # in another
python scripts/setup_trueforge.py         # registers model, sandbox, MCP server, agent
```

### 4. Run the app

```bash
make api    # FastAPI backend on :8010
make web    # Next.js dashboard on :3000
```

Open `http://localhost:3000` and submit: *"Review IAM access for the data-pipeline-role role over the last 90 days."*

**Note:** if TrueForge/Daytona aren't configured, the orchestrator replays locally in-process instead of in the sandbox, and logs this plainly in the agent timeline. If the real AWS policy simulator isn't reachable (e.g. moto, which doesn't implement `SimulateCustomPolicy`), it falls back to a second, independently-written reference evaluator and says so — the two-evaluator-agreement guarantee holds either way, it's just not backed by a literal AWS API call in that mode.

## Environment variables

See [`.env.example`](.env.example): `AWS_REGION`, `AWS_ENDPOINT_URL` (moto/LocalStack demo mode), `AWS_PROFILE`, `USE_DEMO_CLOUDTRAIL`, `IAM_MCP_TOKEN`, `TRUEFORGE_BASE_URL`, `DAYTONA_API_KEY`, `ANTHROPIC_API_KEY` (or `OPENAI_API_KEY`).

## Testing

```bash
cd server
python -m pytest -q
```

29 tests, all against real code paths (moto for AWS, no live account needed to run them): the local policy evaluator (wildcards, explicit-deny-wins, fail-closed on Conditions), candidate identification, the independent validator's agree/disagree logic (including a fail-closed disagreement test), a second reference evaluator's parity with the first, real IAM read/write behavior, and — most importantly — `test_no_revoke_before_approval.py`, which proves no AWS IAM write ever happens before an explicit human approval, then exercises a full approve → commit → verify cycle against a real (moto-backed) IAM policy.

## AI disclosure

This repository's code, tests, and documentation were written with Claude (Anthropic), acting as lead engineer, in a single pair-programming session with the project owner. The project itself pivoted mid-session from an earlier OpenProject-based construction-scheduling agent (kept, unmodified, in the sibling `TP2-TFP` project) once the actual hackathon rules were clarified.

## Future research

`ReferenceEvaluator` is written independently enough from `local_evaluator.py` that a three-way check (local + reference + real AWS) is a natural extension — running all three even when a real AWS account is available, rather than only two, for a stronger agreement guarantee. Other natural extensions: resource-level (not just action-level) blast radius for wildcard grants, cross-account role assumption chains, and a scheduled/recurring review mode.
#   B l a s t R a d i u s  
 