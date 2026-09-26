"""
UNDERSTAND: turn a natural-language access-review request into structured
parameters. Same philosophy as BuildPlan's agent/understand.py: the LLM (or,
here, a deterministic heuristic parser) only extracts structured intent — it
never decides whether a permission is actually safe to remove. That's
OR-Tools-equivalent work done by blast_radius/simulator.py +
blast_radius/validator.py.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# AWS CloudTrail's `LookupEvents` API (aws_integration/cloudtrail.py:CloudTrailSource)
# only returns management events from the last 90 days without a configured
# Trail/CloudTrail Lake — asking for more than that cannot actually be honored
# against real AWS, so a request is capped here rather than silently returning
# a shorter history than the user thinks they asked for.
MAX_LOOKBACK_DAYS = 90


@dataclass
class UnderstoodRequest:
    role_name: Optional[str]
    role_prefix: Optional[str]
    lookback_days: int = 90
    requested_lookback_days: Optional[int] = None  # set only when the user asked for more than the cap
    exclude_actions: set[str] = field(default_factory=set)
    exclude_role_patterns: list[str] = field(default_factory=list)
    raw_request: str = ""

    @property
    def lookback_capped(self) -> bool:
        return self.requested_lookback_days is not None and self.requested_lookback_days > self.lookback_days

    def to_dict(self) -> dict:
        return {
            "role_name": self.role_name,
            "role_prefix": self.role_prefix,
            "lookback_days": self.lookback_days,
            "requested_lookback_days": self.requested_lookback_days,
            "lookback_capped": self.lookback_capped,
            "exclude_actions": sorted(self.exclude_actions),
            "exclude_role_patterns": self.exclude_role_patterns,
        }


_DEFAULT_EXCLUDED_ACTIONS = {
    # Actions whose absence from CloudTrail is expected and not a meaningful
    # "unused" signal (e.g. break-glass/emergency-only actions), or that are
    # dangerous to auto-flag without a human explicitly asking.
    "iam:PassRole",
}


def understand_heuristic(request: str) -> UnderstoodRequest:
    text = request.strip()
    lower = text.lower()

    role_name = None
    m = re.search(r"(?:for|review)\s+(?:the\s+)?['\"]?([a-zA-Z0-9_\-./]+)['\"]?\s+role", lower)
    if m:
        role_name = m.group(1)
    else:
        m2 = re.search(r"role\s+['\"]?([a-zA-Z0-9_\-./]+)['\"]?", lower)
        if m2:
            role_name = m2.group(1)

    role_prefix = None
    m3 = re.search(r"roles?\s+(?:starting with|prefixed with|matching)\s+['\"]?([a-zA-Z0-9_\-./]+)['\"]?", lower)
    if m3:
        role_prefix = m3.group(1)

    lookback_days = MAX_LOOKBACK_DAYS
    requested_lookback_days = None
    m4 = re.search(r"(\d+)\s*-?\s*days?", lower)
    if m4:
        requested = int(m4.group(1))
        if requested > MAX_LOOKBACK_DAYS:
            requested_lookback_days = requested
            lookback_days = MAX_LOOKBACK_DAYS
        elif requested > 0:
            lookback_days = requested

    exclude_actions = set(_DEFAULT_EXCLUDED_ACTIONS)

    exclude_role_patterns = []
    if re.search(r"break-?glass", lower):
        exclude_role_patterns.append("*break-glass*")
        exclude_role_patterns.append("*breakglass*")
    for m5 in re.finditer(r"exclude(?:\s+the)?\s+['\"]?([a-zA-Z0-9_\-./*]+)['\"]?\s+role", lower):
        exclude_role_patterns.append(m5.group(1))

    return UnderstoodRequest(
        role_name=role_name,
        role_prefix=role_prefix,
        lookback_days=lookback_days,
        requested_lookback_days=requested_lookback_days,
        exclude_actions=exclude_actions,
        exclude_role_patterns=exclude_role_patterns,
        raw_request=request,
    )
