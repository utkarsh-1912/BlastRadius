"""Tests for the from-scratch, credential-less IAM policy evaluator — the
code that runs inside the TrueForge sandbox with zero AWS access."""
from __future__ import annotations

from blast_radius.local_evaluator import SimpleStatement, evaluate, remove_action, statements_from_json


def _stmt(effect="Allow", actions=None, resources=None, has_condition=False):
    return SimpleStatement(
        effect=effect, actions=actions or [], not_actions=[], resources=resources or ["*"], not_resources=[], has_condition=has_condition
    )


def test_default_deny():
    """No matching statement -> deny."""
    assert evaluate([], "s3:GetObject", ["arn:aws:s3:::bucket/key"]) == "deny"


def test_explicit_allow():
    stmts = [_stmt(actions=["s3:GetObject"])]
    assert evaluate(stmts, "s3:GetObject", ["arn:aws:s3:::bucket/key"]) == "allow"


def test_explicit_deny_wins_over_allow():
    """An explicit Deny always wins, regardless of statement order."""
    stmts = [_stmt(effect="Allow", actions=["s3:GetObject"]), _stmt(effect="Deny", actions=["s3:GetObject"])]
    assert evaluate(stmts, "s3:GetObject", ["arn:aws:s3:::bucket/key"]) == "deny"


def test_wildcard_action_match():
    stmts = [_stmt(actions=["s3:*"])]
    assert evaluate(stmts, "s3:GetObject", ["arn:aws:s3:::bucket/key"]) == "allow"


def test_wildcard_resource_match():
    stmts = [_stmt(actions=["s3:GetObject"], resources=["arn:aws:s3:::my-bucket/*"])]
    assert evaluate(stmts, "s3:GetObject", ["arn:aws:s3:::my-bucket/deep/key.txt"]) == "allow"
    assert evaluate(stmts, "s3:GetObject", ["arn:aws:s3:::other-bucket/key.txt"]) == "deny"


def test_condition_statement_is_ambiguous_and_never_grants():
    """A statement with a Condition is skipped, not guessed at — fail closed."""
    stmts = [_stmt(actions=["s3:GetObject"], has_condition=True)]
    assert evaluate(stmts, "s3:GetObject", ["arn:aws:s3:::bucket/key"]) == "deny"


def test_no_resource_arns_on_event_requires_wildcard_resource():
    """An event with no resource ARN (e.g. a List call) only matches a
    resource="*" statement — anything more specific is treated as ambiguous."""
    stmts = [_stmt(actions=["s3:ListAllMyBuckets"], resources=["arn:aws:s3:::specific-bucket"])]
    assert evaluate(stmts, "s3:ListAllMyBuckets", []) == "deny"
    stmts_wildcard = [_stmt(actions=["s3:ListAllMyBuckets"], resources=["*"])]
    assert evaluate(stmts_wildcard, "s3:ListAllMyBuckets", []) == "allow"


def test_remove_action_drops_only_that_action():
    stmts = [_stmt(actions=["s3:GetObject", "s3:PutObject"])]
    reduced = remove_action(stmts, "s3:PutObject")
    assert reduced[0].actions == ["s3:GetObject"]
    assert evaluate(reduced, "s3:PutObject", ["arn:aws:s3:::bucket/key"]) == "deny"
    assert evaluate(reduced, "s3:GetObject", ["arn:aws:s3:::bucket/key"]) == "allow"


def test_remove_action_drops_statement_entirely_when_it_was_the_only_action():
    stmts = [_stmt(actions=["s3:PutObject"])]
    reduced = remove_action(stmts, "s3:PutObject")
    assert reduced == []


def test_remove_action_leaves_other_statements_granting_it_untouched():
    """If a broader wildcard statement elsewhere still grants the action,
    removing one literal grant must not break access — the evaluator must
    correctly report the union of everything remaining."""
    stmts = [_stmt(actions=["s3:PutObject"]), _stmt(actions=["s3:*"])]
    reduced = remove_action(stmts, "s3:PutObject")
    assert evaluate(reduced, "s3:PutObject", ["arn:aws:s3:::bucket/key"]) == "allow"


def test_statements_from_json_handles_single_string_fields():
    raw = [{"Effect": "Allow", "Action": "s3:GetObject", "Resource": "arn:aws:s3:::bucket/*"}]
    parsed = statements_from_json(raw)
    assert parsed[0].actions == ["s3:GetObject"]
    assert parsed[0].resources == ["arn:aws:s3:::bucket/*"]
