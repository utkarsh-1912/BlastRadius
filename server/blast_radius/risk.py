"""
Risk tiering for candidate permissions.

Purely a prioritization signal for humans reviewing the report — it never
affects safe_to_remove (that's decided only by the two-evaluator blast
radius replay). A "critical"-tier permission that replay proves harmless is
still proposed for removal; a "low"-tier one that replay flags is still
excluded. This only changes what a human sees first.
"""
from __future__ import annotations

import re

# Ordered highest to lowest; first pattern that matches (case-insensitive,
# IAM wildcard `*`/`?`) wins.
_TIERS: list[tuple[str, list[str]]] = [
    ("critical", ["iam:*", "sts:AssumeRole*", "organizations:*", "*:*Policy", "kms:Decrypt", "kms:*"]),
    ("high", ["*:Delete*", "*:Terminate*", "*:Put*Policy", "*:Attach*", "*:Detach*", "*:Disable*"]),
    ("medium", ["*:Put*", "*:Create*", "*:Update*", "*:Modify*", "*:Publish", "*:Invoke*"]),
    ("low", ["*:Get*", "*:List*", "*:Describe*"]),
]

_SEVERITY_RANK = {"critical": 3, "high": 2, "medium": 1, "low": 0}


def _wildcard_match(pattern: str, value: str) -> bool:
    regex = re.escape(pattern).replace(r"\*", ".*").replace(r"\?", ".")
    return re.fullmatch(regex, value, flags=re.IGNORECASE) is not None


def severity_for_action(action: str) -> str:
    """Returns "critical" | "high" | "medium" | "low" | "unknown"."""
    for tier, patterns in _TIERS:
        if any(_wildcard_match(p, action) for p in patterns):
            return tier
    return "medium"  # unrecognized verb shape — treat as medium, not silently low


def severity_rank(severity: str) -> int:
    return _SEVERITY_RANK.get(severity, 1)
