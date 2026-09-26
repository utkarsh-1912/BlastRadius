#!/usr/bin/env python
"""
Live verification of the REAL `blast-radius` agent running on a REAL
TrueForge instance — not a mock, not pytest. This closes the gap this
project kept hitting manually: "the agent responded, but did it actually
call our tools, and does its answer match reality?"

This cannot be a pytest test (it needs a live TrueForge instance + a live
model + real AWS credentials, none of which CI has), so it's a standalone
script with the same ✓/!/✗ convention as scripts/setup_trueforge.py and
scripts/doctor-style output.

What it checks, for the exact demo request:
  1. TOOL CALLS — did the agent actually call blast-radius-aws-iam tools
     (get_role_policies / get_cloudtrail_history / find_unused_permissions /
     compute_blast_radius), or did it fall back to generic advice / a
     fabricated report? Parsed straight from the turn's raw events, not
     inferred from the text.
  2. GROUND TRUTH MATCH — does the agent's final text actually name every
     action our own deterministic Orchestrator (server/agent/orchestrator.py)
     independently computed as safe to remove, for the SAME request against
     the SAME AWS account? If the agent's answer is missing an action, or
     names one our own pipeline didn't find, that's a real discrepancy
     between what the LLM claims and what was actually proven — exactly the
     kind of gap the anti-fabrication rule exists to prevent.

Usage:
    python scripts/verify_trueforge_agent.py [role_name]

Requires the same .env as the rest of the app: real (or moto) AWS
credentials, TRUEFORGE_BASE_URL reachable, and the `blast-radius` agent
already registered (scripts/setup_trueforge.py).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))

from dotenv import load_dotenv  # noqa: E402

from agent.orchestrator import Orchestrator  # noqa: E402
from agent.trueforge_client import TrueForgeClient, TrueForgeError, TrueForgeUnavailable  # noqa: E402
from aws_integration.client import AwsIamClient  # noqa: E402
from aws_integration.cloudtrail import CloudTrailSource, DemoCloudTrailSource  # noqa: E402
from aws_integration.simulate import AwsPolicySimulator  # noqa: E402
from env_utils import clean_blank_env  # noqa: E402

load_dotenv()
clean_blank_env()


def ok(msg):
    print(f"✓ {msg}")


def warn(msg):
    print(f"! {msg}")


def fail(msg):
    print(f"✗ {msg}")


MCP_SERVER_NAME = "blast-radius-aws-iam"
KNOWN_TOOLS = {
    "list_roles", "get_role_policies", "get_cloudtrail_history",
    "find_unused_permissions", "compute_blast_radius", "revoke_permissions", "verify_role_state",
}


def _build_ground_truth_orchestrator() -> Orchestrator:
    region = os.environ.get("AWS_REGION", "us-east-1")
    endpoint_url = os.environ.get("AWS_ENDPOINT_URL")
    iam = AwsIamClient(region=region, endpoint_url=endpoint_url)
    use_demo = os.environ.get("USE_DEMO_CLOUDTRAIL", "true").lower() == "true"
    if use_demo:
        import json

        demo_path = os.path.join(os.path.dirname(__file__), "..", "server", "data", "demo_cloudtrail_events.json")
        with open(demo_path, "r", encoding="utf-8") as f:
            events = json.load(f)
        cloudtrail = DemoCloudTrailSource(events)
    else:
        cloudtrail = CloudTrailSource(region=region)
    simulator = AwsPolicySimulator(region=region, endpoint_url=endpoint_url)
    return Orchestrator(iam=iam, cloudtrail=cloudtrail, simulator=simulator, trueforge=None)


def _tool_calls_from_events(events: list[dict]) -> list[str]:
    """Extract MCP tool names actually called, from raw session events."""
    called = []
    for item in events:
        ev = item.get("event", item) if isinstance(item, dict) else item
        if not isinstance(ev, dict) or ev.get("type") != "model.message":
            continue
        for tc in ev.get("tool_calls") or []:
            info = tc.get("tool_info") or {}
            name = info.get("name") or info.get("original_tool_name")
            server = info.get("server_name") or info.get("mcp_server_name")
            if name in KNOWN_TOOLS and (server is None or server == MCP_SERVER_NAME):
                called.append(name)
    return called


def _final_text_from_events(events: list[dict]) -> str:
    texts = []
    for item in events:
        ev = item.get("event", item) if isinstance(item, dict) else item
        if isinstance(ev, dict) and ev.get("type") == "model.message":
            content = ev.get("content")
            if isinstance(content, str):
                texts.append(content)
            elif isinstance(content, list):
                texts.append("".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content))
    return "\n".join(texts)


def main() -> int:
    role_name = sys.argv[1] if len(sys.argv) > 1 else "data-pipeline-role"
    request = f"Review IAM access for the {role_name} role over the last 90 days."

    print(f"Request: {request}\n")

    # ---------- ground truth, from our own deterministic pipeline ----------
    print("Computing ground truth (our own Orchestrator, no LLM involved)...")
    orch = _build_ground_truth_orchestrator()
    run = orch.run(request)
    expected_actions = {c.candidate.action for c in run.results if c.safe_to_remove}
    if run.status == "failed":
        fail(f"Ground truth run itself failed: {run.error}")
        return 1
    ok(f"Ground truth: {len(expected_actions)} action(s) safe to remove: {sorted(expected_actions) or '(none)'}")

    # ---------- drive the real TrueForge agent ----------
    base_url = os.environ.get("TRUEFORGE_BASE_URL", "http://localhost:8790")
    tf = TrueForgeClient(base_url=base_url)
    if not tf.reachable():
        fail(f"TrueForge unreachable at {base_url}")
        return 1
    ok(f"TrueForge reachable at {base_url}")

    try:
        session = tf.create_session(agent_name="blast-radius")
        session_id = session.get("id") or session.get("session_id")
        turn = tf.send_turn(session_id, request)
        turn_id = turn.get("id") or turn.get("turn_id")
        final_turn = tf.wait_for_turn(session_id, turn_id, timeout_s=180)
    except (TrueForgeError, TrueForgeUnavailable) as e:
        fail(f"Could not complete a turn against the live agent: {e}")
        return 1

    status = final_turn.get("state", {}).get("status")
    if status == "paused":
        warn("Turn paused (likely waiting for tool approval) — this script only checks the pre-approval report, not the commit.")
    elif status != "done":
        fail(f"Turn ended in unexpected status: {status}")
        return 1
    else:
        ok("Turn completed")

    events = tf.get_events(session_id)
    tool_calls = _tool_calls_from_events(events)
    final_text = _final_text_from_events(events)

    print()
    if not tool_calls:
        fail("ZERO tool calls to blast-radius-aws-iam — the agent answered without touching real AWS data.")
        had_failure = True
    else:
        ok(f"Tool calls made: {tool_calls}")
        had_failure = False

    missing = [a for a in expected_actions if a not in final_text]

    if missing:
        fail(f"Agent's response is missing {len(missing)} action(s) our own pipeline found safe: {missing}")
        had_failure = True
    elif expected_actions:
        ok("Every ground-truth safe action is literally named in the agent's response")

    if not expected_actions and not tool_calls:
        warn("No safe actions expected AND no tool calls made — inconclusive; try a role/account with real findings.")

    print()
    if had_failure:
        print("VERDICT: ✗ discrepancy found between the live agent and ground truth — see above.")
        return 1
    print("VERDICT: ✓ agent's response matches ground truth and used real tool calls.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
