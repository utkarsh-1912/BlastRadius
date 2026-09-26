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
Point at the Agent Activity timeline:
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
