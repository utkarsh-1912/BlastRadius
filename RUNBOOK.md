# Runbook: zero to demo-ready

One exact sequence, no detours. Five terminals total (labeled **[W]** = Windows PowerShell, **[L]** = WSL Ubuntu bash). Run each block in the terminal it's labeled for, in order. Do not skip a step even if it looks done already — re-running everything here is safe (idempotent) and cheap.

---

## 0. One-time environment setup — **[W]**

```powershell
cd C:\Users\utkar\Downloads\TP\BlastRadius
Copy-Item .env.example .env -ErrorAction SilentlyContinue
pip install -r server\requirements.txt
cd apps\web
npm install
cd ..\..
```

Open `.env` in an editor and confirm these are filled in (fill any that are blank):
```
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=<your real key, or leave blank if using AWS_PROFILE>
AWS_SECRET_ACCESS_KEY=<matching secret>
# AWS_ENDPOINT_URL=          <- leave blank/commented for real AWS
TRUEFORGE_BASE_URL=http://localhost:8790
IAM_MCP_TOKEN=<any random 32+ char string, e.g. run: -join ((48..57)+(97..122)|Get-Random -Count 40|%{[char]$_})>
IAM_MCP_PORT=8792
ANTHROPIC_API_KEY=<your key>          # OR OPENAI_API_KEY, not both
MODEL_ID=claude-sonnet-5              # must match whichever key you set above
DAYTONA_API_KEY=<your key, scopes: write:sandboxes, write:snapshots, delete:snapshots>
```

Don't have AWS credentials yet? See [docs/aws-setup.md](docs/aws-setup.md) — do that first, then come back here.

---

## 1. Seed the demo role — **[W]**

```powershell
python scripts\seed_demo_iam.py
```

Confirm it prints `Role ARN: arn:aws:iam::...` with no error. This must show a **real** account ID (12 digits), not `123456789012` (that's moto's fake account — if you see that, `AWS_ENDPOINT_URL` is still set in `.env`; blank it out and re-run this step).

---

## 2. Start TrueForge — **[L]** (WSL Ubuntu terminal)

```bash
cd /mnt/c/Users/utkar/Downloads/TP/BlastRadius
OUTBOUND_URL_ALLOWED_HOSTS='["localhost","127.0.0.1"]' npx @truefoundry/trueforge@latest
```

Leave this running. Wait for it to print it's listening on `:8790` before continuing.

If you've never enabled mirrored networking (see [docs/wsl-networking.md](docs/wsl-networking.md)), do that now, in a **separate** Windows PowerShell terminal, then restart this step:
```powershell
notepad $env:USERPROFILE\.wslconfig
```
Add:
```ini
[wsl2]
networkingMode=mirrored
```
Save, then: `wsl --shutdown`, wait 10 seconds, reopen your WSL terminal, and redo this step.

---

## 3. Start the MCP tool layer — **[L]** (second WSL terminal, or **[W]** if mirrored networking is confirmed working)

```bash
cd /mnt/c/Users/utkar/Downloads/TP/BlastRadius
python3 -m venv .venv 2>/dev/null; source .venv/bin/activate 2>/dev/null || true
pip install -r server/requirements.txt -q
python integrations/aws-iam-mcp/server.py
```

Leave this running. Wait for `Uvicorn running on http://127.0.0.1:8792` before continuing.

---

## 4. Register everything in TrueForge — **[W]** or **[L]**, doesn't matter (only talks to TrueForge's HTTP API)

```powershell
python scripts\setup_trueforge.py
```

**Every line must show ✓.** If any line shows `✗` or `!`, stop and fix that specific thing before continuing — see the troubleshooting table in [docs/trueforge-setup.md](docs/trueforge-setup.md). Common ones at this point:
- `✗ sandbox (Daytona)` with a scopes error → the Daytona key is missing a scope, see step 0.
- `✗ mcp: blast-radius-aws-iam` with `Outbound URL blocked` → step 2 wasn't started with the env var; go back and fix it.
- `✗ mcp: blast-radius-aws-iam` with `ECONNREFUSED` → step 3 isn't actually running, or you're on the wrong side of the WSL/Windows boundary; see [docs/wsl-networking.md](docs/wsl-networking.md).

Re-run this command after every fix. Do not proceed until it's all ✓.

---

## 5. Verify the agent actually works — before touching the dashboard — **[W]**

```powershell
python scripts\verify_trueforge_agent.py
```

This drives the **real** TrueForge agent and cross-checks its answer against ground truth computed independently. Expect:
```
VERDICT: ✓ agent's response matches ground truth and used real tool calls.
```

If it instead reports zero tool calls or a mismatch, **stop here** — do not proceed to the dashboard, the same failure will show up there. Go back to step 4's output and re-check every line is ✓, then re-run this step. This script is the fastest way to know if the whole chain actually works, without clicking through the UI each time.

---

## 6. Start the backend — **[W]** (third terminal)

```powershell
cd C:\Users\utkar\Downloads\TP\BlastRadius\server
uvicorn main:app --port 8010
```

Leave this running. Wait for `Uvicorn running on http://127.0.0.1:8010`.

---

## 7. Start the dashboard — **[W]** (fourth terminal)

```powershell
cd C:\Users\utkar\Downloads\TP\BlastRadius\apps\web
npm run dev
```

Open `http://localhost:3000`.

---

## 8. Run the actual demo request

Submit exactly:
> Review IAM access for the data-pipeline-role role over the last 90 days.

Expect **3 safe, 1 flagged** (if you see 0 safe, the demo role's already had its safe permissions removed from a previous approved run — re-run step 1 to reset it, per [this earlier explanation](#) in chat).

---

## Quick reference: which terminal is which

| # | Runs in | Command | Leave running? |
|---|---|---|---|
| 2 | WSL | `npx @truefoundry/trueforge@latest` (with env var) | Yes |
| 3 | WSL or Windows | `python integrations/aws-iam-mcp/server.py` | Yes |
| 6 | Windows | `uvicorn main:app --port 8010` | Yes |
| 7 | Windows | `npm run dev` | Yes |

Steps 0, 1, 4, 5 run once and exit — no terminal to keep open for those.
