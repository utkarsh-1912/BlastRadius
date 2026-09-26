# Recording Script

Word-for-word narration, paired with exact on-screen actions. Read the **SAY** lines aloud as written (they're written to sound natural spoken, not written-for-reading) while doing the matching **SHOW** action. Total run time: about 4 minutes. Record your screen with audio; no editing required if you follow this straight through — pause and retake a scene if you flub it, rather than trying to do it in one perfect take.

Before you hit record: run through [RUNBOOK.md](../RUNBOOK.md) once so everything is actually live — TrueForge, the MCP server, the backend, the dashboard, and the demo role freshly seeded (so you get 3 safe + 1 flagged, not 0 safe). Close every browser tab except the AWS Console and the Blast Radius dashboard, side by side or easily alt-tabbed.

---

## Scene 1 — Cold open (0:00–0:20)

**SHOW:** Your face on camera, or the Blast Radius cover slide/README, whichever you're more comfortable opening on.

**SAY:**
> "Every AWS IAM cleanup stalls on the same fear: what if this permission that looks unused is actually needed by something that only runs once a quarter? AWS's own tools tell you a permission is *unused* — they never prove it's *safe to remove*. That's the gap Blast Radius closes."

---

## Scene 2 — The real project (0:20–0:45)

**SHOW:** Switch to the AWS Console, IAM → Roles → `data-pipeline-role` → Permissions tab, showing the real inline policy with its actions listed.

**SAY:**
> "This is a real IAM role in a real AWS account — `data-pipeline-role`. It has permissions for S3, DynamoDB, and SNS. Some of these are actually used. Some aren't. The question is: which ones, and how do we know for sure?"

---

## Scene 3 — Submit the request (0:45–1:05)

**SHOW:** Switch to the Blast Radius dashboard at `localhost:3000`, on the New Review page. Click into the request box (already pre-filled with the demo request), then click **Run Blast Radius Review**.

**SAY:**
> "I'll ask Blast Radius to review this role's access over the last 90 days."

---

## Scene 4 — Watch the agent work (1:05–1:50)

**SHOW:** You're now on the review detail page. Point your cursor at the Agent Activity timeline as it fills in line by line — pause on each new line for a beat before moving your cursor to the next.

**SAY:**
> "Watch the left panel. This isn't an animation — every line here is a real event. It's reading the role's actual policy, pulling real CloudTrail history, identifying which permissions look unused, and then — this is the important part — replaying every one of those permissions against real historical events, inside a sandbox with zero AWS credentials, and independently cross-checking that against AWS's own policy engine."

---

## Scene 5 — The results (1:50–2:40)

**SHOW:** Scroll down to the Blast Radius Results table. Point at the three rows marked "Safe," then point at the `sns:Publish` row marked "Flagged."

**SAY:**
> "Here's the result. Three permissions are proven safe to remove — zero historical evidence they've ever been used, confirmed by two independent evaluators. But this one, `sns:Publish`, looks identical at first glance — also quiet for 90 days. A tool that only checks recency would flag it for removal too. Blast Radius doesn't. It replayed this role's real history and found this exact permission was used once, five months ago, to send an incident alert. So it's excluded — flagged for a human to look at, not silently bundled in with the ones that are actually dead."

---

## Scene 6 — Stop, and approve (2:40–3:10)

**SHOW:** Scroll to the Approval panel. Read the line on screen, then click **Approve & Revoke in AWS IAM**.

**SAY:**
> "Nothing has touched AWS yet. The agent stopped here on purpose — this is the one consequential action, and it needs a human. I'll approve it."

---

## Scene 7 — Prove it happened (3:10–3:40)

**SHOW:** Switch back to the AWS Console tab, refresh the role's policy page. Point at the policy — the three approved actions are gone, `sns:Publish` and everything actually in use are still there.

**SAY:**
> "And there it is, in the real AWS account. The three proven-safe permissions are gone. The one we flagged is untouched. Nothing else changed."

---

## Scene 8 — Verification (3:40–3:55)

**SHOW:** Switch back to the dashboard, point at the verification panel (roles updated, IAM re-read, permissions confirmed removed).

**SAY:**
> "And Blast Radius doesn't just assume the write worked — it re-reads the role from AWS and confirms every removed permission is actually gone before it ever says success."

---

## Scene 9 — Close (3:55–4:10)

**SHOW:** Your face on camera again, or back to the cover slide.

**SAY:**
> "The LLM understands the request and explains the result. A deterministic replay — run twice, by two independently-written evaluators — decides what's actually safe. A human approves the one consequential action. Only then does the agent touch the real account. That's Blast Radius."

---

## Optional bonus scene — prove it's really TrueForge (add anywhere, +40s)

If you want to show the agent running natively in TrueForge (not just through the dashboard), insert this after Scene 4:

**SHOW:** Switch to TrueForge's own chat UI at `localhost:8790`, the `blast-radius` agent, a session already run with the same demo request. Scroll to show a real tool call (e.g. `get_role_policies`) expanded in the transcript.

**SAY:**
> "Our dashboard isn't a separate system — it's a thinner window onto the same TrueForge agent. Here it is running directly, inside TrueForge, calling the exact same tools."

---

## Recording tips

- **Zoom your browser to ~125%** before recording — small text reads badly in a demo video.
- **Slow down more than feels natural.** What feels like an awkward pause while recording plays back as normal pacing.
- **Do Scene 2 and Scene 7 (both AWS Console shots) in the same take if you can** — less tab-switching to edit around.
- If something breaks mid-recording (a flaky TrueForge connection, a stale session), stop, fix it per [RUNBOOK.md](../RUNBOOK.md), and restart from the last clean scene rather than pushing through — a visible error in a submission video reads worse than a slightly-longer editing pass.
- Export/trim in whatever's easiest (QuickTime, Clipchamp, even just cutting between OBS scene markers) — the script above is written so each scene is a clean cut point.
