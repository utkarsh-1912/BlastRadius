"""Risk-tier classification is a display/prioritization signal only — it
must never be confused with safe_to_remove, which is decided purely by the
blast-radius replay."""
from __future__ import annotations

from blast_radius.risk import severity_for_action, severity_rank


def test_critical_actions():
    assert severity_for_action("iam:CreateUser") == "critical"
    assert severity_for_action("iam:AttachRolePolicy") == "critical"
    assert severity_for_action("kms:Decrypt") == "critical"


def test_high_actions():
    assert severity_for_action("s3:DeleteBucket") == "high"
    assert severity_for_action("ec2:TerminateInstances") == "high"


def test_medium_actions():
    assert severity_for_action("s3:PutObject") == "medium"
    assert severity_for_action("dynamodb:CreateTable") == "medium"


def test_low_actions():
    assert severity_for_action("s3:GetObject") == "low"
    assert severity_for_action("dynamodb:ListTables") == "low"


def test_rank_orders_critical_above_low():
    assert severity_rank("critical") > severity_rank("high") > severity_rank("medium") > severity_rank("low")


def test_candidates_are_sorted_highest_severity_first():
    from datetime import datetime, timezone

    from blast_radius.candidates import find_candidates
    from blast_radius.local_evaluator import SimpleStatement
    from blast_radius.model import AttachedPolicy, Role

    policy = AttachedPolicy(
        kind="inline",
        name="p1",
        arn=None,
        statements=[
            SimpleStatement(effect="Allow", actions=["s3:GetObject", "iam:AttachRolePolicy", "s3:DeleteBucket"], not_actions=[], resources=["*"], not_resources=[])
        ],
    )
    role = Role(name="r", arn="arn:aws:iam::123456789012:role/r", create_date=None, policies=[policy])
    candidates = find_candidates(role, [], lookback_days=90, exclude_actions=set())
    severities = [c.severity for c in candidates]
    assert severities == sorted(severities, key=lambda s: -severity_rank(s))
    assert candidates[0].action == "iam:AttachRolePolicy"  # critical, listed first
