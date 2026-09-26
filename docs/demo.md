# Demo script (5 minutes)

**Request used throughout:**
> Review IAM access for the data-pipeline-role role over the last 90 days.

### 0:00–0:30 — The problem
"Every IAM cleanup stalls on the same fear: what if this one stale-looking permission is actually used by something rare — a quarterly job, an incident response action? AWS's own Access Analyzer tells you 'unused for 90 days.' It never tells you what removing it would actually have done. That's the gap Blast Radius closes."

### 0:30–1:00 — The real role
Show the actual `data-pipeline-role` in AWS IAM (or the local moto-backed account): an inline policy with S3, DynamoDB, SNS and `iam:PassRole` permissions. "This is a real role, read through real `iam:GetRolePolicy` calls — not a mock."

### 1:00–1:30 — The request
Paste the demo request and click **Run Blast Radius Review**.

### 1:30–2:30 — Watch the agent work
Point at the Agent Activity timeline in the left panel of the review page:
```
Understanding request
Extracted parameters
Connected to AWS IAM
Retrieved role policies
Using exported CloudTrail history (labeled — a new demo account has no 90-day history yet)
Identified 4 candidate permissions
Real AWS policy simulator unavailable -> falling back to the reference evaluator (labeled)
Blast radius analysis complete
Waiting for human approval
```

If asked for more than 90 days of history, an extra line appears here plainly stating the cap and why (AWS CloudTrail's own Event History doesn't retain further back than that by default) — worth pointing out if a judge asks "what if I want a year of history?": the honest answer, stated by the tool itself, not a silent shortfall.

### 2:30–3:15 — The results table
Show the safe-vs-flagged table:
- `s3:DeleteObject`, `s3:ListBucket`, `dynamodb:DeleteTable` — **safe**, zero historical evidence, ever.
- `sns:Publish` — **flagged, excluded**: used once, 160 days ago, to publish an incident alert. Nothing else grants it. The replay proves that exact call would now be denied. "A tool that only looks at recency would have proposed removing this too. We don't."

### 3:15–3:45 — Stop
"The analysis is done, but nothing has changed in AWS IAM yet." Show the Approve / Reject panel.

### 3:45–4:15 — Approve
Click **Approve & Revoke in AWS IAM**.

### 4:15–4:45 — Show IAM updated
Re-read the role's policy — the three safe actions are gone; `sns:Publish`, `iam:PassRole`, and everything actually in use are untouched.

### 4:45–5:00 — Verification
Show the verification panel: roles updated, IAM re-read, permissions confirmed removed.

**Close:**
"The LLM understands the request and explains the result. A deterministic replay — run twice, by two independently-written evaluators — decides what's actually safe. A human approves the one consequential action. Only then does the agent touch the real account."

## Live-AWS variant

With a real AWS account and enough CloudTrail history (`USE_DEMO_CLOUDTRAIL=false`), the same flow runs against `iam:SimulateCustomPolicy` instead of the reference evaluator — the "validated via" label in the header changes accordingly, and that's the only difference in the demo script.

## Optional: show it directly inside TrueForge, not just the dashboard

Our dashboard is a polished frontend on top of the same agent — worth proving that directly if there's time. Open TrueForge's own chat UI (`http://localhost:8790`), pick the `blast-radius` agent, and send the same demo request there. This shows the raw tool calls (`get_role_policies`, `get_cloudtrail_history`, `compute_blast_radius`) as TrueForge's own UI renders them, plus the real approval pause before `revoke_permissions` — the literal hackathon requirement ("agent reaches a real system, runs code safely in a sandbox, stops for approval") with nothing of ours in between. A good line here: "everything you just saw in our dashboard is really just a nicer window onto this."

**Sanity check before doing this live**: run it once yourself beforehand and confirm the agent actually calls tools rather than falling back to generic advice — if the MCP connection isn't live when a session starts, the agent behaves as if it has no tools at all rather than erroring loudly (see [docs/trueforge-setup.md](trueforge-setup.md#6-verify-its-actually-using-trueforge-not-the-fallback)). Not something you want to discover for the first time on stage.
