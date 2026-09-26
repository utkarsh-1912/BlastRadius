"""
CloudTrail's default Event History only retains 90 days of management
events without a dedicated Trail/Lake configured, so a request for a longer
lookback window can't honestly be honored against real AWS. UNDERSTAND must
cap it rather than silently pretending to search further back than it can.
"""
from __future__ import annotations

from agent.understand import MAX_LOOKBACK_DAYS, understand_heuristic


def test_default_lookback_is_the_max():
    u = understand_heuristic("Review IAM access for the data-pipeline-role role.")
    assert u.lookback_days == MAX_LOOKBACK_DAYS
    assert u.requested_lookback_days is None
    assert u.lookback_capped is False


def test_within_cap_is_honored_exactly():
    u = understand_heuristic("Review IAM access for the data-pipeline-role role over the last 30 days.")
    assert u.lookback_days == 30
    assert u.requested_lookback_days is None
    assert u.lookback_capped is False


def test_at_exactly_the_cap_is_not_flagged_as_capped():
    u = understand_heuristic("Review IAM access for the data-pipeline-role role over the last 90 days.")
    assert u.lookback_days == 90
    assert u.lookback_capped is False


def test_beyond_cap_is_capped_and_flagged():
    u = understand_heuristic("Review IAM access for the data-pipeline-role role over the last 365 days.")
    assert u.lookback_days == MAX_LOOKBACK_DAYS
    assert u.requested_lookback_days == 365
    assert u.lookback_capped is True


def test_to_dict_reports_the_cap():
    u = understand_heuristic("Review IAM access for the data-pipeline-role role over the last 180 days.")
    d = u.to_dict()
    assert d["lookback_days"] == 90
    assert d["requested_lookback_days"] == 180
    assert d["lookback_capped"] is True


def test_zero_days_falls_back_to_default_rather_than_an_empty_window():
    u = understand_heuristic("Review IAM access for the data-pipeline-role role over the last 0 days.")
    assert u.lookback_days == MAX_LOOKBACK_DAYS
