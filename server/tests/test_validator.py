"""
Tests for the independent validator (blast_radius/validator.py): a
permission is only ever "safe to remove" when the local sandbox evaluator
and a (faked, here) AWS evaluator both agree it breaks nothing. Disagreement
must fail closed, never fail open.
"""
from __future__ import annotations

from datetime import datetime, timezone

from blast_radius.local_evaluator import SimpleStatement
from blast_radius.model import AttachedPolicy, CandidatePermission, HistoricalEvent
from blast_radius.simulator import run_local_replay
from blast_radius.validator import validate_candidate


class FakeAwsSimulator:
    """Stands in for AwsPolicySimulator: returns pre-scripted verdicts keyed
    by event index, so tests can force agreement/disagreement scenarios."""

    def __init__(self, verdict_by_index: dict[int, str]):
        self._verdicts = verdict_by_index

    def simulate_batch(self, hypothetical_statements, events, event_indices):
        return {i: self._verdicts.get(i, "deny") for i in event_indices}


def _candidate(action="s3:PutObject"):
    policy = AttachedPolicy(kind="inline", name="p1", arn=None, statements=[])
    return CandidatePermission(role_name="test-role", action=action, source_policy=policy, last_accessed=None, reason="unused")


def _statements(actions):
    return [SimpleStatement(effect="Allow", actions=actions, not_actions=[], resources=["*"], not_resources=[])]


def test_agreement_and_no_breakage_is_safe():
    candidate = _candidate()
    events = [HistoricalEvent(event_time=datetime.now(timezone.utc), action="s3:GetObject", resource_arns=[])]
    all_stmts = _statements(["s3:GetObject", "s3:PutObject"])
    local_verdicts = run_local_replay(candidate, all_stmts, events)  # no s3:PutObject events -> empty
    result = validate_candidate(candidate, all_stmts, events, local_verdicts, FakeAwsSimulator({}))
    assert result.safe_to_remove is True
    assert result.validator_agreement is True
    assert result.events_checked == 0


def test_agreeing_denial_is_not_safe():
    candidate = _candidate()
    events = [HistoricalEvent(event_time=datetime.now(timezone.utc), action="s3:PutObject", resource_arns=[])]
    all_stmts = _statements(["s3:PutObject"])
    local_verdicts = run_local_replay(candidate, all_stmts, events)
    assert local_verdicts[0]["local_verdict"] == "deny"  # only grant removed -> would break
    result = validate_candidate(candidate, all_stmts, events, local_verdicts, FakeAwsSimulator({0: "deny"}))
    assert result.safe_to_remove is False
    assert result.validator_agreement is True
    assert len(result.broken_events) == 1


def test_disagreement_between_evaluators_fails_closed():
    """Local evaluator says allow (e.g. a wildcard elsewhere still covers it),
    but the (faked) AWS evaluator says deny for some reason -- disagreement
    must never be reported as safe, even though neither side alone flagged breakage."""
    candidate = _candidate()
    events = [HistoricalEvent(event_time=datetime.now(timezone.utc), action="s3:PutObject", resource_arns=[])]
    all_stmts = _statements(["s3:PutObject", "s3:*"])  # wildcard elsewhere still grants it
    local_verdicts = run_local_replay(candidate, all_stmts, events)
    assert local_verdicts[0]["local_verdict"] == "allow"
    result = validate_candidate(candidate, all_stmts, events, local_verdicts, FakeAwsSimulator({0: "deny"}))
    assert result.validator_agreement is False
    assert result.safe_to_remove is False, "disagreement must fail closed, not open"


def test_events_for_other_actions_are_irrelevant():
    candidate = _candidate("s3:PutObject")
    events = [
        HistoricalEvent(event_time=datetime.now(timezone.utc), action="s3:GetObject", resource_arns=[]),
        HistoricalEvent(event_time=datetime.now(timezone.utc), action="dynamodb:Scan", resource_arns=[]),
    ]
    all_stmts = _statements(["s3:GetObject", "s3:PutObject", "dynamodb:Scan"])
    local_verdicts = run_local_replay(candidate, all_stmts, events)
    assert local_verdicts == []
    result = validate_candidate(candidate, all_stmts, events, local_verdicts, FakeAwsSimulator({}))
    assert result.safe_to_remove is True
    assert result.events_checked == 0
