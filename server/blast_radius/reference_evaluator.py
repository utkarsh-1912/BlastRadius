"""
A SECOND, independently-written IAM policy evaluator, used as the
authoritative cross-check in demo mode when a real AWS account (with
`iam:SimulateCustomPolicy`) isn't available — moto's IAM mock does not
implement policy simulation at all (`NotImplementedError`), so a moto-backed
demo can't call real AWS for the validate step the way a real AWS account
can (see aws_integration/simulate.py, which calls the real API whenever one
is configured).

This module is deliberately written differently from
blast_radius/local_evaluator.py so that a bug in one is unlikely to also be
in the other:
  - wildcard matching uses `fnmatch.translate` (stdlib) instead of a
    hand-rolled regex escape,
  - evaluation collects the full set of matching Deny and Allow statements
    up front and combines them with set logic, instead of a single
    short-circuiting left-to-right scan.

In a live deployment against real AWS, `AwsPolicySimulator` (backed by the
genuine `iam:SimulateCustomPolicy` API) is always used instead — this module
exists only so Blast Radius's core "two evaluators must agree" guarantee
still holds when demoing against a mocked account. Which one ran is always
recorded on the result and shown in the UI; it is never presented as a live
AWS call when it wasn't one.
"""
from __future__ import annotations

import fnmatch
from typing import Optional

from blast_radius.local_evaluator import SimpleStatement
from blast_radius.model import HistoricalEvent


def _matches(pattern: str, value: str) -> bool:
    return fnmatch.fnmatchcase(value, pattern)


def _statement_covers(stmt: SimpleStatement, action: str, resource_arns: list[str]) -> bool:
    action_ok = (
        any(_matches(p, action) for p in stmt.actions)
        if stmt.actions
        else (not any(_matches(p, action) for p in stmt.not_actions) if stmt.not_actions else False)
    )
    if not action_ok:
        return False

    if not resource_arns:
        return "*" in stmt.resources

    if stmt.resources:
        return all(any(_matches(p, r) for p in stmt.resources) for r in resource_arns)
    if stmt.not_resources:
        return all(not any(_matches(p, r) for p in stmt.not_resources) for r in resource_arns)
    return False


def evaluate(statements: list[SimpleStatement], action: str, resource_arns: list[str]) -> str:
    """Set-based evaluation: gather every applicable statement first (skipping
    ones with a Condition, same fail-closed rule as local_evaluator), then a
    single Deny anywhere beats any number of Allows."""
    applicable = [s for s in statements if not s.has_condition and _statement_covers(s, action, resource_arns)]
    if any(s.effect == "Deny" for s in applicable):
        return "deny"
    if any(s.effect == "Allow" for s in applicable):
        return "allow"
    return "deny"


class ReferenceEvaluator:
    """Adapter with the same `simulate_batch` shape as AwsPolicySimulator, so
    blast_radius/validator.py can use either interchangeably."""

    def simulate_batch(
        self, hypothetical_statements: list[SimpleStatement], events: list[HistoricalEvent], event_indices: list[int]
    ) -> dict[int, str]:
        return {i: evaluate(hypothetical_statements, events[i].action, events[i].resource_arns) for i in event_indices}
