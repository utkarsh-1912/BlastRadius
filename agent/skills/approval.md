---
name: approval
description: The human-approval gate before any IAM revocation — what to show, and what "STOP" actually means.
---

# Approval

After blast-radius analysis is complete for every candidate on a role:

1. Show two lists, always both: permissions safe to remove (with proof — events checked, zero broken, which evaluator confirmed it), and permissions found but excluded (with the specific historical event that would have broken, and when).
2. State plainly how many permissions will actually change, and on which role(s) and policy(ies).
3. Say the analysis is complete but nothing has changed in AWS IAM yet.
4. STOP. Do not call `revoke_permissions`. The harness will not let you call it without a human approval decision anyway (`require_approval_for_tools`), but you must not attempt it, retry it, or rephrase around it.
5. If denied: call `verify_role_state` to confirm the role is unchanged, report that plainly, and end the turn.
6. If approved: call `revoke_permissions` once per (role, policy) pair with exactly the approved action list. Then call `verify_role_state` and only claim success if the removed actions are actually gone from a fresh read.
