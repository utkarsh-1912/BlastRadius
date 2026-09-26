"""Tests for candidate-permission identification (blast_radius/candidates.py)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from blast_radius.candidates import find_candidates
from blast_radius.local_evaluator import SimpleStatement
from blast_radius.model import AttachedPolicy, HistoricalEvent, Role


def _policy(name, actions):
    return AttachedPolicy(
        kind="inline",
        name=name,
        arn=None,
        statements=[SimpleStatement(effect="Allow", actions=actions, not_actions=[], resources=["*"], not_resources=[])],
    )


def _role(policies):
    return Role(name="test-role", arn="arn:aws:iam::123456789012:role/test-role", create_date=None, policies=policies)


def test_unused_action_is_flagged_as_candidate():
    role = _role([_policy("p1", ["s3:GetObject", "s3:PutObject"])])
    events = [HistoricalEvent(event_time=datetime.now(timezone.utc), action="s3:GetObject", resource_arns=[])]
    candidates = find_candidates(role, events, lookback_days=90, exclude_actions=set())
    actions = {c.action for c in candidates}
    assert actions == {"s3:PutObject"}


def test_recently_used_action_is_not_a_candidate():
    role = _role([_policy("p1", ["s3:GetObject"])])
    events = [HistoricalEvent(event_time=datetime.now(timezone.utc), action="s3:GetObject", resource_arns=[])]
    candidates = find_candidates(role, events, lookback_days=90, exclude_actions=set())
    assert candidates == []


def test_action_used_outside_lookback_window_is_a_candidate():
    role = _role([_policy("p1", ["s3:GetObject"])])
    old_event = HistoricalEvent(event_time=datetime.now(timezone.utc) - timedelta(days=200), action="s3:GetObject", resource_arns=[])
    candidates = find_candidates(role, [old_event], lookback_days=90, exclude_actions=set())
    assert len(candidates) == 1
    assert candidates[0].last_accessed == old_event.event_time


def test_wildcard_grants_are_never_candidates():
    role = _role([_policy("p1", ["s3:*"])])
    candidates = find_candidates(role, [], lookback_days=90, exclude_actions=set())
    assert candidates == []


def test_excluded_actions_are_never_candidates():
    role = _role([_policy("p1", ["iam:PassRole"])])
    candidates = find_candidates(role, [], lookback_days=90, exclude_actions={"iam:PassRole"})
    assert candidates == []


def test_never_used_action_has_no_last_accessed():
    role = _role([_policy("p1", ["s3:DeleteBucket"])])
    candidates = find_candidates(role, [], lookback_days=90, exclude_actions=set())
    assert len(candidates) == 1
    assert candidates[0].last_accessed is None
    assert "Not observed" in candidates[0].reason
