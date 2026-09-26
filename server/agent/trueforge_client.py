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
    agent_name: str = "blast-radius"

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
        body: dict[str, Any] = {"agent": agent_name}
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

    # ---------------- sandbox code execution ----------------

    def exec_python(self, script: str, agent_name: Optional[str] = None, timeout_s: float = 20.0) -> str:
        """
        Best-effort: run `script` inside a REAL TrueForge sandbox, by driving
        a real session/turn against a registered agent (agent/blast-radius.agent.json,
        which has `sandbox.enabled: true`) and instructing it to execute the
        script verbatim via the sandbox `exec` tool, then extracting that
        tool call's stdout from the turn's events.

        This requires: the target agent already registered in TrueForge
        (scripts/setup_trueforge.py), and a sandbox provider (e.g. Daytona)
        configured. If either is missing, or the turn doesn't produce a
        parseable sandbox exec response within `timeout_s`, this raises
        TrueForgeUnavailable — the same exception type every other reason
        TrueForge can't be used raises — so callers (agent/orchestrator.py's
        _sandbox_replay) fall back to a local, in-process replay exactly the
        same way, with no special-casing needed for "sandbox exec specifically
        isn't wired up" vs. "TrueForge isn't reachable at all".
        """
        agent = agent_name or self.agent_name
        try:
            session = self.create_session(agent_name=agent)
            session_id = session.get("id") or session.get("session_id")
            if not session_id:
                raise TrueForgeUnavailable(f"create_session for agent '{agent}' returned no session id.")

            message = (
                "Run EXACTLY the following Python script using the sandbox exec tool, verbatim, "
                "with no modification. Do not explain or summarize it — just execute it and stop.\n\n"
                f"```python\n{script}\n```"
            )
            turn = self.send_turn(session_id, message)
            turn_id = turn.get("id") or turn.get("turn_id")
            if not turn_id:
                raise TrueForgeUnavailable("send_turn returned no turn id.")

            final_turn = self.wait_for_turn(session_id, turn_id, timeout_s=timeout_s)
            status = final_turn.get("state", {}).get("status")
            if status != "done":
                raise TrueForgeUnavailable(f"Sandbox turn ended in unexpected status '{status}' (expected 'done').")

            events = self.get_events(session_id)
            stdout = _extract_exec_stdout(events)
            if stdout is None:
                raise TrueForgeUnavailable("Turn completed but no sandbox exec tool response was found in its events.")
            return stdout
        except TrueForgeUnavailable:
            raise
        except TrueForgeError as e:
            raise TrueForgeUnavailable(f"Sandbox execution failed: {e}") from e
        except Exception as e:  # e.g. malformed response shape from an unexpected TrueForge version
            raise TrueForgeUnavailable(f"Sandbox execution failed unexpectedly: {e}") from e


def _extract_exec_stdout(events: list) -> Optional[str]:
    """
    Find the content of the LAST sandbox `exec` system-tool response in a raw
    session events list (GET /sessions/{id}/events). Mirrors the event shapes
    documented in the reference `dress-rehearsal` project's
    viewer/public/mapEvents.mjs: a `model.message` event's `tool_calls[i]` with
    `tool_info.type == "truefoundry-system"` and `tool_info.name == "exec"`,
    paired by `tool_call_id` with a later `tool.response` event.
    """
    exec_tool_call_ids: set[str] = set()
    for item in events:
        ev = item.get("event", item) if isinstance(item, dict) else item
        if not isinstance(ev, dict) or ev.get("type") != "model.message":
            continue
        for tc in ev.get("tool_calls") or []:
            info = tc.get("tool_info") or {}
            if info.get("type") == "truefoundry-system" and info.get("name") == "exec":
                exec_tool_call_ids.add(tc.get("id"))

    last_stdout: Optional[str] = None
    for item in events:
        ev = item.get("event", item) if isinstance(item, dict) else item
        if not isinstance(ev, dict) or ev.get("type") != "tool.response":
            continue
        if ev.get("tool_call_id") in exec_tool_call_ids:
            content = ev.get("content")
            last_stdout = content if isinstance(content, str) else str(content)
    return last_stdout
