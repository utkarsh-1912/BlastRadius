# TrueForge on Windows: the WSL Networking Gap

TrueForge doesn't run natively on Windows — the standard path is `npx @truefoundry/trueforge@latest` inside **WSL Ubuntu**. That introduces a networking gap this project hit live and is worth documenting precisely, because the error it produces (`ECONNREFUSED 127.0.0.1:<port>`) looks identical to "the server isn't running" even when it very much is.

## The problem

`127.0.0.1` inside WSL2 is **not automatically the same loopback address as Windows'** `127.0.0.1`, unless mirrored networking is enabled. In WSL2's default NAT networking mode:

- A server bound to `127.0.0.1` **on Windows** (e.g. running `integrations/aws-iam-mcp/server.py` from PowerShell) is reachable from Windows, and from a browser on Windows — but **not** from inside WSL.
- TrueForge, running inside WSL, trying to reach `http://localhost:8792` (the MCP server) then gets `ECONNREFUSED`, because from WSL's point of view, nothing is listening on ITS `127.0.0.1:8792` — the real server is on the other side of the boundary.

**How to recognize this specifically:** look at the file paths in TrueForge's own error stack trace. If they start with `/home/<you>/.npm/_npx/...` (a Linux home directory), TrueForge is running inside WSL. If your MCP server's own terminal shows a Windows path (`PS C:\Users\...>`), it's running on Windows. Different sides of the boundary — that mismatch is the whole bug.

```
McpConnectionError: Failed to connect to remote MCP server 'blast-radius-aws-iam':
  failed to connect (tried streamable-http, sse):
  [{"transport":"streamable-http","error":"fetch failed"},
   {"transport":"sse","error":"SSE error: TypeError: fetch failed: connect ECONNREFUSED 127.0.0.1:8792"}]
```

## Fix, option A — mirrored networking (recommended, least disruptive)

Windows 11 22H2+ supports sharing `localhost` between Windows and WSL2 directly.

1. Create or edit `C:\Users\<you>\.wslconfig`:
   ```ini
   [wsl2]
   networkingMode=mirrored
   ```
2. In PowerShell: `wsl --shutdown`
3. Restart WSL, restart TrueForge inside it, and restart the MCP server on whichever side you prefer (Windows PowerShell is fine now).
4. Retest.

If this doesn't take effect, check `wsl --version` — mirrored networking needs a sufficiently recent WSL2 kernel. Fall back to option B.

## Fix, option B — run the MCP server inside WSL too (always works)

```bash
# inside the SAME WSL Ubuntu terminal TrueForge runs in
cd /mnt/c/Users/<you>/Downloads/TP/BlastRadius
python3 -m venv .venv && source .venv/bin/activate
pip install -r server/requirements.txt
python integrations/aws-iam-mcp/server.py
```

The FastAPI backend (`uvicorn`) and the Next.js dashboard can stay on Windows either way — TrueForge only ever talks to the MCP server directly, never to those.

## Don't forget the other localhost restriction

Fixing the WSL/Windows boundary is necessary but not sufficient — TrueForge's own outbound SSRF guard *also* blocks `localhost` by default, independent of this issue entirely. If you see `Outbound URL blocked for host "localhost"` (rather than `ECONNREFUSED`), that's the different, unrelated fix in [trueforge-setup.md](trueforge-setup.md#1-start-trueforge): restart TrueForge with `OUTBOUND_URL_ALLOWED_HOSTS='["localhost","127.0.0.1"]'` set. It's easy to fix one and not realize the other is still blocking you — check the exact error text (`ECONNREFUSED` vs `Outbound URL blocked`) to know which one you're looking at.
