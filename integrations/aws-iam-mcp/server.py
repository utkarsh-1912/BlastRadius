"""
Blast Radius AWS IAM Tool Layer — the MCP server TrueForge actually talks to.

    TrueForge Agent
          |
          v
    Blast Radius AWS IAM Tool Layer     <-- this file
          |
          v
    AWS IAM + CloudTrail (boto3)
          |
          v
    Real AWS account (or a local moto_server for demos)

Deliberately narrow surface, mirroring BuildPlan's OpenProject tool layer:
read-mostly tools plus exactly one write tool (`revoke_permissions`), which
is registered in the agent manifest's `require_approval_for_tools` — so
TrueForge itself pauses for human approval before ever calling it,
independent of anything the agent's own instructions say.

Run: `python server.py` (reads AWS_REGION / AWS_ENDPOINT_URL / AWS_PROFILE /
IAM_MCP_PORT / IAM_MCP_TOKEN from the environment; see ../../.env.example).
"""
from __future__ import annotations

import json
import os
import sys
from typing import Optional

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

_SERVER_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "server")
sys.path.insert(0, os.path.abspath(_SERVER_DIR))

from env_utils import clean_blank_env  # noqa: E402
from agent.understand import MAX_LOOKBACK_DAYS  # noqa: E402
from aws_integration.client import AwsIamClient, IamError  # noqa: E402
from aws_integration.cloudtrail import CloudTrailSource, DemoCloudTrailSource  # noqa: E402
from aws_integration.simulate import AwsPolicySimulator  # noqa: E402
from blast_radius.candidates import find_candidates  # noqa: E402
from blast_radius.local_evaluator import remove_action  # noqa: E402
from blast_radius.reference_evaluator import ReferenceEvaluator  # noqa: E402
from blast_radius.simulator import run_local_replay  # noqa: E402
from blast_radius.validator import validate_candidate  # noqa: E402

load_dotenv()
clean_blank_env(["IAM_MCP_TOKEN"])

REGION = os.environ.get("AWS_REGION", "us-east-1")
ENDPOINT_URL = os.environ.get("AWS_ENDPOINT_URL")
MCP_PORT = int(os.environ.get("IAM_MCP_PORT", "8792"))

mcp = FastMCP("blast-radius-aws-iam", port=MCP_PORT)
_iam = AwsIamClient(region=REGION, endpoint_url=ENDPOINT_URL)
_simulator = AwsPolicySimulator(region=REGION, endpoint_url=ENDPOINT_URL)


def _demo_events() -> dict:
    path = os.path.join(_SERVER_DIR, "data", "demo_cloudtrail_events.json")
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


_cloudtrail = (
    CloudTrailSource(region=REGION) if os.environ.get("USE_DEMO_CLOUDTRAIL", "true").lower() != "true" else DemoCloudTrailSource(_demo_events())
)


@mcp.tool()
def list_roles(name_prefix: Optional[str] = None) -> list[dict]:
    """List IAM role names (optionally filtered by prefix)."""
    return [{"role_name": r["RoleName"], "arn": r["Arn"]} for r in _iam.list_roles(name_prefix=name_prefix)]


@mcp.tool()
def get_role_policies(role_name: str) -> dict:
    """Fetch a role's attached managed + inline policy statements."""
    role = _iam.get_role(role_name)
    return {
        "role_name": role.name,
        "arn": role.arn,
        "policies": [
            {
                "kind": p.kind,
                "name": p.name,
                "arn": p.arn,
                "statements": [
                    {"effect": s.effect, "actions": s.actions, "resources": s.resources, "has_condition": s.has_condition}
                    for s in p.statements
                ],
            }
            for p in role.policies
        ],
    }


@mcp.tool()
def get_cloudtrail_history(role_name: str, lookback_days: int = MAX_LOOKBACK_DAYS) -> list[dict]:
    """Fetch this role's real historical API calls (CloudTrail), or a labeled
    demo export if CloudTrail history isn't configured for this account.
    lookback_days is capped at 90 — AWS CloudTrail's default Event History
    only retains the last 90 days of management events without a dedicated
    Trail or CloudTrail Lake configured; asking for more cannot be honored
    against real AWS, so a request beyond that is silently capped here."""
    role = _iam.get_role(role_name)
    capped = min(lookback_days, MAX_LOOKBACK_DAYS)
    events = _cloudtrail.lookup_events_for_principal(role.arn, lookback_days=capped)
    return [{"event_time": e.event_time.isoformat(), "action": e.action, "resource_arns": e.resource_arns} for e in events]


@mcp.tool()
def find_unused_permissions(role_name: str, lookback_days: int = MAX_LOOKBACK_DAYS, exclude_actions: Optional[list[str]] = None) -> list[dict]:
    """Identify literal (non-wildcard) permissions granted to a role that do
    not appear in its CloudTrail history within the lookback window.
    lookback_days is capped at 90 for the same reason as get_cloudtrail_history."""
    lookback_days = min(lookback_days, MAX_LOOKBACK_DAYS)
    role = _iam.get_role(role_name)
    events = _cloudtrail.lookup_events_for_principal(role.arn, lookback_days=max(lookback_days, MAX_LOOKBACK_DAYS))
    candidates = find_candidates(role, events, lookback_days, set(exclude_actions or []))
    return [
        {"action": c.action, "source_policy": c.source_policy.name, "reason": c.reason, "last_accessed": c.last_accessed.isoformat() if c.last_accessed else None}
        for c in candidates
    ]


@mcp.tool()
def compute_blast_radius(role_name: str, action: str, lookback_days: int = 90) -> dict:
    """
    THE CORE SAFETY CHECK. Replays every historical call this role actually
    made against a hypothetical policy with `action` removed, using TWO
    independently-implemented evaluators (a local one and, when available,
    the real AWS iam:SimulateCustomPolicy API) — both must agree the
    permission is unused before it's reported safe. This never modifies
    anything; it is pure computation.
    """
    role = _iam.get_role(role_name)
    events = _cloudtrail.lookup_events_for_principal(role.arn, lookback_days=max(lookback_days, 365))
    all_stmts = [s for p in role.policies for s in p.statements]
    from blast_radius.model import AttachedPolicy, CandidatePermission

    source_policy = next((p for p in role.policies for s in p.statements if action in s.actions), role.policies[0] if role.policies else AttachedPolicy("inline", "?", None, []))
    candidate = CandidatePermission(role_name=role_name, action=action, source_policy=source_policy, last_accessed=None, reason="explicit check")
    hypothetical = remove_action(all_stmts, action)
    local_verdicts = run_local_replay(candidate, all_stmts, events)
    try:
        result = validate_candidate(candidate, hypothetical, events, local_verdicts, _simulator)
        validator_used = "aws"
    except Exception:
        result = validate_candidate(candidate, hypothetical, events, local_verdicts, ReferenceEvaluator())
        validator_used = "reference (AWS SimulateCustomPolicy unavailable)"
    d = result.to_dict()
    d["validator_used"] = validator_used
    return d


@mcp.tool()
def revoke_permissions(role_name: str, policy_name: str, policy_kind: str, policy_arn: Optional[str], actions: list[str]) -> dict:
    """
    THE ONLY WRITE TOOL. Surgically removes the given literal actions from
    one named policy (inline or customer-managed) attached to a role. Never
    touches any other policy, statement, or field, and never deletes a role,
    a user, or a whole policy. TrueForge is configured
    (agent/blast-radius.agent.json: require_approval_for_tools) to pause and
    require an explicit human approval before this tool is ever invoked.
    """
    try:
        return _iam.revoke_actions(role_name, policy_name, policy_kind, policy_arn, actions)
    except IamError as e:
        return {"status": "error", "error": str(e)}


@mcp.tool()
def verify_role_state(role_name: str, expected_removed_actions: list[str]) -> dict:
    """Re-read a role's policies after a commit and confirm the removed
    actions are actually gone. Read-only; never writes."""
    role = _iam.get_role(role_name)
    current_actions = {a for p in role.policies for s in p.statements for a in s.actions}
    still_present = [a for a in expected_removed_actions if a in current_actions]
    return {"role_name": role_name, "still_present": still_present, "verified": len(still_present) == 0}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
