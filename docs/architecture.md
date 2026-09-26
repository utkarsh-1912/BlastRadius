# Architecture

## Component map

| Path | Responsibility |
|---|---|
| `server/blast_radius/model.py` | Plain dataclasses: Role, AttachedPolicy, CandidatePermission, HistoricalEvent, EventVerdict, BlastRadiusResult. No I/O. |
| `server/blast_radius/local_evaluator.py` | A from-scratch IAM policy evaluator — no AWS SDK, no credentials. This is what runs in the TrueForge sandbox. |
| `server/blast_radius/reference_evaluator.py` | A SECOND, independently-written evaluator (different wildcard-matching approach, different evaluation order) used as the authoritative cross-check when the real AWS simulator isn't reachable (e.g. under moto). |
| `server/blast_radius/candidates.py` | IDENTIFY CANDIDATES: literal (non-wildcard) actions granted but absent from CloudTrail within the lookback window. Sorts by severity (`risk.py`) so the report shows the biggest wins first. |
| `server/blast_radius/risk.py` | Severity tiering (critical/high/medium/low) for candidates — a display/prioritization signal only, never load-bearing for `safe_to_remove`. |
| `server/blast_radius/simulator.py` | SANDBOX SIMULATE: replays every historical event matching a candidate's action against the hypothetical (action-removed) policy, using only `local_evaluator`. |
| `server/blast_radius/sandbox_code.py` | Renders `simulator.py`'s logic as a fully self-contained script (embeds the policy + events as JSON) for the TrueForge sandbox's `exec` tool. |
| `server/blast_radius/validator.py` | VALIDATE: merges the sandbox's local verdicts with `AwsPolicySimulator`'s (or, in demo mode, `ReferenceEvaluator`'s) verdicts for the same events. Fails closed on any disagreement. |
| `server/aws_integration/client.py` | The only place that calls the IAM write API. Narrow surface: list/get roles, one surgical `revoke_actions()`, and `list_policy_attachments()` for cross-role checks on shared managed policies. |
| `server/aws_integration/cloudtrail.py` | Real CloudTrail `LookupEvents`, or `DemoCloudTrailSource` reading a labeled historical export. |
| `server/aws_integration/simulate.py` | Wraps the real, read-only `iam:SimulateCustomPolicy` API. |
| `server/agent/understand.py` | UNDERSTAND: NL request → role filter, lookback window (capped at `MAX_LOOKBACK_DAYS = 90`), exclusions. Deterministic heuristic parser. |
| `server/agent/orchestrator.py` | The full workflow. Owns the one method (`commit_and_verify`) allowed to write to AWS IAM, gated on run status. Also: cross-role blast radius for shared managed policies, and a standalone single-permission check (`check_permission()`) that needs no approval workflow since it never writes. |
| `server/agent/store.py` | SQLite-backed audit history of past reviews, surviving API restarts (read-only after a restart — approving a stale run requires re-running the review, by design). |
| `server/main.py` | FastAPI: `POST /api/review`, `GET /api/review/{id}`, `POST /api/review/{id}/approve`, `POST /api/review/{id}/reject`, `GET /api/reviews` (history), `POST /api/check` (standalone permission check). |
| `integrations/aws-iam-mcp/server.py` | The MCP server TrueForge calls. Seven tools; `revoke_permissions` is the only write, gated by the agent manifest. Same 90-day lookback cap as `understand.py`. |
| `agent/blast-radius.agent.json` | TrueForge agent manifest — includes an explicit anti-fabrication rule; see [trueforge-integration.md](trueforge-integration.md#agent-honesty-the-anti-fabrication-rule). |
| `apps/web/` | Next.js dashboard: a left-sidebar enterprise layout (`components/Sidebar.tsx`) over four pages (`/` new review, `/reviews` history, `/reviews/[id]` detail, `/check` standalone check), built on a small UI primitive library (`components/ui/`). Every `app/api/*` route proxies through `lib/proxy.ts`, which turns an unreachable backend into a clean `502 {"error": ...}` instead of Next's bare 500. |

## The workflow

```
UNDERSTAND         -> agent/understand.py
RETRIEVE           -> aws_integration/client.py (roles+policies) + cloudtrail.py (history)
IDENTIFY CANDIDATES-> blast_radius/candidates.py: literal actions absent from history
SANDBOX SIMULATE   -> blast_radius/simulator.py (in the sandbox if TrueForge/Daytona are
                      configured, else in-process — logged as a fallback either way)
VALIDATE           -> blast_radius/validator.py: cross-check against AWS's real API, or
                      the reference evaluator when that API isn't reachable
EXPLAIN            -> orchestrator groups results into safe_changes / unsafe_candidates
STOP               -> orchestrator sets status = "awaiting_approval" and returns
APPROVE            -> POST /api/review/{id}/approve (human-triggered only)
COMMIT             -> agent/orchestrator.py: commit_and_verify() -> AwsIamClient.revoke_actions()
VERIFY             -> commit_and_verify() re-reads the role and confirms every removed
                      action is actually gone
```

## Why replay against ALL available history, not just the lookback window

A candidate, by construction, has zero CloudTrail events within the lookback window (that's the definition of "unused" in `candidates.py`) — so replaying only that window would always find nothing to check, and the simulation step would be vacuous. Instead, the simulator replays against every event available, however old. This means:

- An action with **zero evidence of ever being called** replays against nothing, agrees trivially, and is reported safe with high confidence.
- An action that **was called once, long ago**, and is not covered by any other grant in the policy, will always show that specific historical call would now be denied — because it's tautologically true that removing the only permission a call needed breaks that call. Blast Radius treats this as a real signal, not noise: it means the permission has *actual evidence of past use*, however rare, and excludes it from the auto-approved list rather than silently lumping it in with a permission that's never been touched. This is the one-line distinction a recency-only tool (including AWS's own Access Analyzer) cannot make.
- An action that **was called before, but is now covered by a broader grant elsewhere** (e.g. a wildcard `s3:*` statement added later) correctly replays as still-allowed — proving the specific literal grant is redundant and genuinely safe to clean up, not just quiet.

## Two evaluators, and what "independent" actually means here

`local_evaluator.py` and `reference_evaluator.py` implement the same subset of IAM policy semantics (Effect, Action/NotAction, Resource/NotResource wildcard matching, fail-closed on Condition) with deliberately different code: different wildcard-matching implementations (hand-rolled regex escape vs. `fnmatch.translate`) and different evaluation strategies (early-exit scan vs. gather-then-set-combine). `test_reference_evaluator.py` proves they agree on the same cases — so a disagreement caught by `validator.py` at runtime is a real signal about an ambiguous or edge-case policy, not incidental implementation drift.

In production, `AwsPolicySimulator` (the real `iam:SimulateCustomPolicy` API) is always preferred over `ReferenceEvaluator` — the latter only engages when the real API call fails for any reason (moto doesn't implement it at all; a real AWS account should never hit this fallback), and the UI always shows which one actually ran.

## Cross-role blast radius for shared managed policies

`revoke_actions()` on a customer-managed policy rewrites the policy's default *version* — which changes what **every** role, user, or group it's attached to can do, not just the role a review happened to start from. `Orchestrator._extend_across_shared_attachments()` handles this: for any candidate whose source policy is `kind == "managed"`, it calls `AwsIamClient.list_policy_attachments()`, and for every *other* attached role, fetches that role's own full statement set and its own CloudTrail history, then replays the candidate action against *that* role too. A permission is only reported safe if it's independently safe for every attachment — `tests/test_shared_policy.py` proves this catches a case a single-role review would miss (a permission unused by role A but still used by role B, both sharing one managed policy).

`commit_and_verify()` groups by policy ARN (not by role) for managed policies specifically, so a shared policy is rewritten exactly once — calling `revoke_actions` twice for the same managed policy would burn one of IAM's five policy-version slots for nothing and could race with itself.

## The 90-day lookback cap

AWS CloudTrail's default Event History (`LookupEvents`, what `aws_integration/cloudtrail.py:CloudTrailSource` calls) only retains 90 days of management events without a dedicated Trail or CloudTrail Lake configured. A request for a longer window genuinely cannot be honored against real AWS, so `agent/understand.py`'s `MAX_LOOKBACK_DAYS = 90` caps it rather than silently returning less history than the user thinks they asked for — `UnderstoodRequest.lookback_capped` and `.requested_lookback_days` make the cap visible (in the orchestrator's timeline, and in the UI's `ConstraintPanel`) whenever it actually applied. The same cap is enforced independently in `integrations/aws-iam-mcp/server.py`'s `get_cloudtrail_history`/`find_unused_permissions` tools, since the TrueForge agent calls those directly and bypasses `understand.py` entirely — and `agent/blast-radius.agent.json`'s instructions tell the agent to state the cap plainly if a user asks for more, rather than silently using a shorter window.

## What's explicitly out of scope for this MVP

Per the hackathon's build priorities: no user/group-level review (roles only), no resource-level blast radius for wildcard action grants (only literal actions are ever proposed), no cross-account role-assumption chains, no scheduled/recurring reviews, no multi-cloud (AWS IAM only). These are documented future directions in the README, not silently-patched gaps.
