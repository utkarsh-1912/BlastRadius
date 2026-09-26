"""
SANDBOX SIMULATE: replay every historical event that could possibly be
affected by removing one candidate permission, using ONLY the local,
credential-less evaluator (blast_radius/local_evaluator.py).

This module's `run_local_replay` is exactly what gets executed inside the
TrueForge sandbox — see sandbox_code.py, which renders it as a self-contained
script with no imports back into this repo and no AWS credentials, mirroring
the earlier BuildPlan project's scheduler/sandbox_code.py pattern.

The output is a per-event "local_verdict" only. It is NOT trusted on its own
— blast_radius/validator.py independently re-checks every one of these
events against the real AWS `iam:SimulatePrincipalPolicy` API (host-side,
with read-only credentials the sandbox never sees) and only calls a
permission "safe to remove" when both evaluators agree on every event.
"""
from __future__ import annotations

from blast_radius.local_evaluator import (
    SimpleStatement,
    evaluate,
    remove_action,
    statements_from_json,
)
from blast_radius.model import CandidatePermission, HistoricalEvent


def run_local_replay(
    candidate: CandidatePermission, all_role_statements: list[SimpleStatement], events: list[HistoricalEvent]
) -> list[dict]:
    """
    Returns one dict per historical event whose action matches the
    candidate's (only those could possibly be affected by removing it):
        {"event_index": i, "local_verdict": "allow" | "deny"}
    `all_role_statements` must be the UNION of every policy statement
    attached to the role (not just the candidate's source policy), so a
    grant duplicated elsewhere (e.g. a broader wildcard statement) is
    correctly still honored by the hypothetical policy.
    """
    hypothetical = remove_action(all_role_statements, candidate.action)
    results = []
    for i, event in enumerate(events):
        if event.action != candidate.action:
            continue
        verdict = evaluate(hypothetical, event.action, event.resource_arns)
        results.append({"event_index": i, "local_verdict": verdict})
    return results


def role_statements_to_plain(statements: list[SimpleStatement]) -> list[dict]:
    """Serialize SimpleStatement list to plain JSON for handing to the sandbox script."""
    return [
        {
            "effect": s.effect,
            "actions": s.actions,
            "not_actions": s.not_actions,
            "resources": s.resources,
            "not_resources": s.not_resources,
            "has_condition": s.has_condition,
        }
        for s in statements
    ]


def plain_to_role_statements(raw: list[dict]) -> list[SimpleStatement]:
    return [
        SimpleStatement(
            effect=r["effect"],
            actions=r["actions"],
            not_actions=r["not_actions"],
            resources=r["resources"],
            not_resources=r["not_resources"],
            has_condition=r["has_condition"],
        )
        for r in raw
    ]
