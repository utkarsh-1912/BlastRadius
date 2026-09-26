---
name: blast-radius-analysis
description: How to identify unused IAM permissions and prove, by replay, exactly what removing each one would have done — never trust "quiet for 90 days" alone.
---

# Blast Radius Analysis

AWS's own IAM Access Analyzer can tell you a permission's last-accessed timestamp. That is a *hint*, not a *proof*. Blast Radius's job is to turn that hint into a proof, or to correctly refuse to.

1. Read the role's actual policies (`get_role_policies`) — never assume what a role grants.
2. Call `find_unused_permissions` to shortlist literal actions absent from CloudTrail within the lookback window. Never propose a wildcard grant (`s3:*`, `*`) for removal — only literal actions.
3. For every candidate, call `compute_blast_radius`. This:
   - builds the hypothetical policy (the role's current statements minus this one action),
   - replays every historical call that ever used this action — not just within the lookback window, but everything available — against that hypothetical policy, using a credential-less local evaluator running in the sandbox,
   - independently cross-checks every one of those replayed events against the real AWS policy engine (`iam:SimulateCustomPolicy`), or a second, differently-implemented reference evaluator if the real API isn't reachable (e.g. a brand-new or demo account) — and says plainly which one it used.
4. A permission is safe to remove only when **both** evaluators agree on **every** replayed event, and none of them would have been denied. If a permission was genuinely used once, six months ago, and nothing else in the policy still grants it — that is real evidence it might still matter (an annual report job, an incident-response action) — so it is correctly excluded from the auto-approved list and surfaced separately for a human to decide, even though it also passes the "quiet for 90 days" heuristic.
5. Never let recency alone override an actual historical replay result. A permission that's been quiet for 90 days but broke a real call from further back is more informative than one with zero evidence of ever being used — treat them differently, and say why.
