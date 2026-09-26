"""
IDENTIFY CANDIDATES: which (role, action, source policy) triples are
plausibly safe to remove.

A candidate is any literal (non-wildcard) action granted by an Allow
statement that does NOT appear anywhere in the role's historical CloudTrail
events within the lookback window. Wildcard grants ("s3:*", "*") are never
proposed for removal directly — narrowing a wildcard is a bigger, riskier
edit than removing one literal action, and out of scope for this tool by
design (BuildPlan's spec-equivalent: "only ever touch exactly what was
asked, nothing broader").

Candidates are sorted highest-severity first (blast_radius/risk.py) so a
human scanning the report sees the biggest wins — a dead `iam:*` grant, say
— before a dead `s3:GetObject`. Severity never affects whether something is
proposed; it only affects display order.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from blast_radius.model import CandidatePermission, HistoricalEvent, Role
from blast_radius.risk import severity_for_action, severity_rank


def find_candidates(
    role: Role, events: list[HistoricalEvent], lookback_days: int, exclude_actions: set[str]
) -> list[CandidatePermission]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    observed_actions = {e.action for e in events if e.event_time >= cutoff}

    candidates: list[CandidatePermission] = []
    seen: set[tuple[str, str]] = set()
    for policy in role.policies:
        for stmt in policy.statements:
            if stmt.effect != "Allow":
                continue
            for action in stmt.actions:
                if "*" in action or "?" in action:
                    continue  # wildcard grant; not a removal candidate
                if action in exclude_actions:
                    continue
                if action in observed_actions:
                    continue
                key = (action, policy.name)
                if key in seen:
                    continue
                seen.add(key)
                last_used = max((e.event_time for e in events if e.action == action), default=None)
                reason = (
                    f"Not observed in {lookback_days} days of CloudTrail history"
                    if last_used is None
                    else f"Last observed {last_used.date().isoformat()}, outside the {lookback_days}-day window"
                )
                candidates.append(
                    CandidatePermission(
                        role_name=role.name,
                        action=action,
                        source_policy=policy,
                        last_accessed=last_used,
                        reason=reason,
                        severity=severity_for_action(action),
                    )
                )
    candidates.sort(key=lambda c: -severity_rank(c.severity))
    return candidates
