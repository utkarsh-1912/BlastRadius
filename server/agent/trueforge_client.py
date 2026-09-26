"""
Thin REST client for TrueForge (mirrors the pattern used by the reference
`dress-rehearsal` hackathon project's scripts/lib/trueforge.ts, translated to
Python since BuildPlan's orchestrator is Python).

Base URL + API: `${TRUEFORGE_BASE_URL}/api/v1/...`.

This client is used for two things:
  1. `ensure_agent_registered()` — idempotent setup (model provider, sandbox
     provider, MCP server, agent) — see scripts/setup_trueforge.py which
     calls this at startup, the same way dress-rehearsal's `npm run setup` does.
  2. `run_turn_and_collect()` — send one user message to the BuildPlan agent
     and poll GET /sessions/{id}/events until the turn finishes, returning
     the raw event list so the orchestrator (and the UI's timeline) can walk
     it exactly like the reference viewer's mapEvents.mjs does.

If TrueForge is not reachable, every method raises `TrueForgeUnavailable` and
the orchestrator falls back to running the scheduler locally (see
agent/orchestrator.py) so the demo still works without a live TrueForge
instance, clearly labeled as a fallback.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional

import requests


class TrueForgeUnavailable(Exception):
    pass


class TrueForgeError(Exception):
    pass


@dataclass
class TrueForgeClient:
    base_url: str = "http://localhost:8790"
    timeout_s: float = 20.0

    def __post_init__(self):
        self.base_url = self.base_url.rstrip("/")

    def _url(self, path: str) -> str:
        return f"{self.base_url}/api/v1{path}"

    def _request(self, method: str, path: str, json_body: Optional[dict] = None, timeout: Optional[float] = None) -> Any:
        try:
            resp = requests.request(
                method, self._url(path), json=json_body, timeout=timeout or self.timeout_s
            )
        except requests.RequestException as e:
            raise TrueForgeUnavailable(f"TrueForge unreachable at {self.base_url}: {e}") from e
        if not resp.ok:
            raise TrueForgeError(f"TrueForge {method} {path} failed: {resp.status_code} {resp.text[:500]}")
        if not resp.content:
            return None
        return resp.json()

    def reachable(self) -> bool:
        try:
            self._request("GET", "/capabilities", timeout=5)
            return True
        except Exception:
            return False

    # ---------------- settings / agents (setup-time, idempotent PUT) ----------------

    def put_model_provider(self, manifest: dict) -> dict:
        return self._request("PUT", "/settings/model-providers", {"manifest": manifest})

    def put_sandbox_provider(self, manifest: dict) -> dict:
        return self._request("PUT", "/settings/sandbox-providers", {"manifest": manifest}, timeout=60)

    def put_mcp_server(self, manifest: dict) -> dict:
        return self._request("PUT", "/settings/mcp-servers", {"manifest": manifest})

    def list_agents(self) -> list[dict]:
        data = self._request("GET", "/agents?limit=100")
        return data.get("data", [])

    def create_or_update_agent(self, name: str, description: str, manifest: dict) -> dict:
        existing = {a["name"]: a for a in self.list_agents()}
        if name in existing:
            return self._request(
                "PUT", f"/agents/{existing[name]['id']}", {"description": description, "manifest": manifest}
            )
        return self._request("POST", "/agents", {"name": name, "description": description, "manifest": manifest})

    # ---------------- sessions / turns / events (runtime) ----------------

    def create_session(self, agent_name: str, external_id: Optional[str] = None) -> dict:
        body: dict[str, Any] = {"agent_name": agent_name}
        if external_id:
            body["external_id"] = external_id
        return self._request("POST", "/sessions", body)

    def send_turn(self, session_id: str, message: str) -> dict:
        """Create a new turn with a user.message input item."""
        body = {"input": [{"type": "user.message", "content": message}]}
        return self._request("POST", f"/sessions/{session_id}/turns", body)

    def send_approval(self, session_id: str, tool_call_id: str, approve: bool, reason: str = "") -> dict:
        """Resume a paused turn with a human approval decision."""
        body = {
            "input": [
                {
                    "type": "user.tool_approval",
                    "tool_call_id": tool_call_id,
                    "approval": {"status": "allow" if approve else "deny", "reason": reason},
                }
            ]
        }
        return self._request("POST", f"/sessions/{session_id}/turns", body)

    def get_events(self, session_id: str, since: Optional[str] = None) -> list[dict]:
        path = f"/sessions/{session_id}/events?limit=500"
        if since:
            path += f"&after={since}"
        data = self._request("GET", path)
        return data.get("data", [])

    def get_turn(self, session_id: str, turn_id: str) -> dict:
        return self._request("GET", f"/sessions/{session_id}/turns/{turn_id}")

    def wait_for_turn(
        self, session_id: str, turn_id: str, poll_interval_s: float = 1.0, timeout_s: float = 180.0
    ) -> dict:
        """Poll until the turn reaches a terminal or paused state."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            turn = self.get_turn(session_id, turn_id)
            status = turn.get("state", {}).get("status")
            if status in ("done", "error", "cancelled", "paused"):
                return turn
            time.sleep(poll_interval_s)
        raise TrueForgeError(f"Timed out waiting for turn {turn_id} to complete.")
