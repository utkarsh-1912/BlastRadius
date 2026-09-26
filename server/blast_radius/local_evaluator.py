"""
A from-scratch, credential-less IAM policy evaluator.

This is THE code that runs inside the TrueForge sandbox (see
blast_radius/sandbox_code.py, which renders this logic as a self-contained
script). It never touches the network and never sees an AWS credential — it
takes a JSON export of policy documents and historical CloudTrail events
(already retrieved host-side) and answers, in plain Python, "would this
specific historical call still be allowed under this hypothetical policy?"

It is deliberately a SEPARATE implementation of IAM policy semantics from
anything AWS provides, re-implementing the parts of the evaluation model
Blast Radius needs (Effect / Action+NotAction / Resource+NotResource
wildcard matching, explicit-deny-wins, default-deny). It does not call
`iam:SimulatePrincipalPolicy` — that authoritative, real-AWS check lives in
aws_integration/simulate.py and is run independently, host-side, by the
validator. Two independently-coded evaluators must agree before a
permission is ever reported "safe to remove" (blast_radius/validator.py).

Supported subset: Effect, Action/NotAction, Resource/NotResource, with the
`*` and `?` IAM wildcard characters. Conditions are intentionally NOT
evaluated (unsupported condition keys make a statement's applicability
ambiguous) — a statement with a Condition block is treated as "ambiguous",
which fails the event to `deny` (fail-closed: an ambiguous statement never
makes a permission look safer to remove than it is).
"""
from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass


def _wildcard_match(pattern: str, value: str) -> bool:
    """IAM wildcard match: `*` = any chars (incl. none), `?` = exactly one char."""
    regex = re.escape(pattern).replace(r"\*", ".*").replace(r"\?", ".")
    return re.fullmatch(regex, value) is not None


def _matches_any(patterns: list[str], value: str) -> bool:
    return any(_wildcard_match(p, value) for p in patterns)


@dataclass
class SimpleStatement:
    effect: str
    actions: list[str]
    not_actions: list[str]
    resources: list[str]
    not_resources: list[str]
    has_condition: bool = False


def statement_applies_to_action(stmt: SimpleStatement, action: str) -> bool:
    if stmt.actions:
        return _matches_any(stmt.actions, action)
    if stmt.not_actions:
        return not _matches_any(stmt.not_actions, action)
    return False


def statement_applies_to_resource(stmt: SimpleStatement, resource_arns: list[str]) -> bool:
    if not resource_arns:
        # No resource ARNs on the event (e.g. a list-type call) — treat "*" as
        # the only unambiguous match; anything more specific is ambiguous
        # and fails closed (see module docstring).
        return "*" in stmt.resources
    if stmt.resources:
        return all(_matches_any(stmt.resources, r) for r in resource_arns)
    if stmt.not_resources:
        return all(not _matches_any(stmt.not_resources, r) for r in resource_arns)
    return False


def evaluate(statements: list[SimpleStatement], action: str, resource_arns: list[str]) -> str:
    """
    Returns "allow" or "deny" for a single action+resource pair under the
    given statement list, using IAM's actual evaluation logic: default deny,
    explicit Allow can grant, explicit Deny always wins regardless of order.
    A statement carrying a Condition block is skipped as ambiguous (neither
    grants nor blocks) rather than guessed at.
    """
    decision = "deny"  # default deny
    for stmt in statements:
        if stmt.has_condition:
            continue  # ambiguous; do not let it participate either way
        if not statement_applies_to_action(stmt, action):
            continue
        if not statement_applies_to_resource(stmt, resource_arns):
            continue
        if stmt.effect == "Deny":
            return "deny"  # explicit deny short-circuits immediately
        if stmt.effect == "Allow":
            decision = "allow"
    return decision


def statements_from_json(raw_statements: list[dict]) -> list[SimpleStatement]:
    """Parse a policy document's `Statement` list (already JSON-decoded) into
    SimpleStatement objects. Accepts both single-string and list forms for
    Action/NotAction/Resource/NotResource, as IAM does."""

    def as_list(v) -> list[str]:
        if v is None:
            return []
        return [v] if isinstance(v, str) else list(v)

    out = []
    for s in raw_statements:
        out.append(
            SimpleStatement(
                effect=s.get("Effect", "Deny"),
                actions=as_list(s.get("Action")),
                not_actions=as_list(s.get("NotAction")),
                resources=as_list(s.get("Resource")),
                not_resources=as_list(s.get("NotResource")),
                has_condition="Condition" in s and bool(s["Condition"]),
            )
        )
    return out


def remove_action(statements: list[SimpleStatement], action_to_remove: str) -> list[SimpleStatement]:
    """
    Returns a NEW statement list representing the policy with one action
    surgically removed from every Allow statement that grants it (used to
    build the "hypothetical policy" for replay). A statement that grants
    exactly [action_to_remove] is dropped entirely; a statement granting
    other actions too keeps those, minus the removed one. Wildcard action
    grants (e.g. "s3:*") that cover the target action are left untouched —
    Blast Radius only proposes removing permissions that appear as an exact,
    literal grant, never a wildcard collapse (see candidates.py).
    """
    out = []
    for stmt in statements:
        if stmt.effect == "Allow" and action_to_remove in stmt.actions:
            remaining = [a for a in stmt.actions if a != action_to_remove]
            if remaining:
                out.append(SimpleStatement(stmt.effect, remaining, stmt.not_actions, stmt.resources, stmt.not_resources, stmt.has_condition))
            # else: statement dropped entirely
        else:
            out.append(stmt)
    return out
