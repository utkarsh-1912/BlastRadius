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


@dataclass
class UnderstoodRequest:
    role_name: Optional[str]
    role_prefix: Optional[str]
    lookback_days: int = 90
    exclude_actions: set[str] = field(default_factory=set)
    exclude_role_patterns: list[str] = field(default_factory=list)
    raw_request: str = ""

    def to_dict(self) -> dict:
        return {
            "role_name": self.role_name,
            "role_prefix": self.role_prefix,
            "lookback_days": self.lookback_days,
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

    lookback_days = 90
    m4 = re.search(r"(\d+)\s*-?\s*days?", lower)
    if m4:
        lookback_days = int(m4.group(1))

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
        exclude_actions=exclude_actions,
        exclude_role_patterns=exclude_role_patterns,
        raw_request=request,
    )
