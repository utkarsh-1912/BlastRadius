"""
Data model for Blast Radius.

Core idea: AWS's IAM Access Analyzer can tell you a permission looks unused
("last accessed: never, or 118 days ago"). It cannot tell you, with proof,
what would actually have happened if you'd removed it. Blast Radius closes
that gap: for every candidate permission, it replays every real historical
API call that principal actually made against a hypothetical policy with the
permission removed, and reports exactly which calls (if any) would now be
denied.

Two independent evaluators produce that per-call verdict (see
blast_radius/local_evaluator.py and aws_integration/simulate.py) and must
agree before a permission is ever called "safe to remove" — the same
solver/validator independence pattern as this team's previous project,
applied to IAM instead of construction scheduling.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class PolicyStatement:
    """A single IAM policy statement, normalized to plain lists (no JSON quirks)."""

    effect: str  # "Allow" | "Deny"
    actions: list[str]
    not_actions: list[str]
    resources: list[str]
    not_resources: list[str]
    sid: Optional[str] = None


@dataclass
class AttachedPolicy:
    """A policy attached to a role: either a customer-managed policy (has an
    ARN + version) or an inline policy (identified by name only)."""

    kind: str  # "managed" | "inline"
    name: str
    arn: Optional[str]  # None for inline
    statements: list[PolicyStatement]


@dataclass
class Role:
    name: str
    arn: str
    create_date: Optional[datetime]
    policies: list[AttachedPolicy]


@dataclass
class HistoricalEvent:
    """One real API call the principal actually made, from CloudTrail."""

    event_time: datetime
    action: str  # "s3:GetObject"
    resource_arns: list[str]
    source_ip: str = ""
    event_id: str = ""


@dataclass
class CandidatePermission:
    """One (action, source policy) pair flagged as a candidate for removal —
    e.g. because IAM Access Analyzer or our own usage diff says it's unused."""

    role_name: str
    action: str
    source_policy: AttachedPolicy
    last_accessed: Optional[datetime]
    reason: str  # why it's a candidate (grounded, not invented)
    severity: str = "medium"  # "critical" | "high" | "medium" | "low" — prioritization only, never load-bearing
    shared_with_roles: list[str] = field(default_factory=list)  # other roles this managed policy is attached to


@dataclass
class EventVerdict:
    """Independent-vs-authoritative agreement for one historical event under
    the hypothetical policy-with-permission-removed."""

    event: HistoricalEvent
    local_verdict: str  # "allow" | "deny"
    aws_verdict: str  # "allow" | "deny" (from the real SimulatePrincipalPolicy)
    agree: bool

    @property
    def would_break(self) -> bool:
        return self.local_verdict == "deny" or self.aws_verdict == "deny"


@dataclass
class BlastRadiusResult:
    """The full simulation result for one candidate permission."""

    candidate: CandidatePermission
    events_checked: int
    verdicts: list[EventVerdict]
    validator_agreement: bool  # False if local and AWS ever disagreed
    safe_to_remove: bool
    broken_events: list[EventVerdict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "role_name": self.candidate.role_name,
            "action": self.candidate.action,
            "source_policy": self.candidate.source_policy.name,
            "policy_kind": self.candidate.source_policy.kind,
            "last_accessed": self.candidate.last_accessed.isoformat() if self.candidate.last_accessed else None,
            "reason": self.candidate.reason,
            "severity": self.candidate.severity,
            "shared_with_roles": self.candidate.shared_with_roles,
            "events_checked": self.events_checked,
            "validator_agreement": self.validator_agreement,
            "safe_to_remove": self.safe_to_remove,
            "broken_event_count": len(self.broken_events),
            "broken_events_sample": [
                {
                    "event_time": v.event.event_time.isoformat(),
                    "action": v.event.action,
                    "resource_arns": v.event.resource_arns,
                }
                for v in self.broken_events[:5]
            ],
        }
