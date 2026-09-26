"""
The single most important test in this repo (mirrors BuildPlan's
test_no_write_before_approval.py): Blast Radius must never revoke an AWS IAM
permission before a human has explicitly approved the proposed change, and a
successful approve -> commit -> verify sequence must actually mutate and
re-read real IAM state (via moto, so no live AWS account is needed to run
this).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import boto3
import pytest
from moto import mock_aws

from agent.orchestrator import Orchestrator
from aws_integration.client import AwsIamClient
from aws_integration.cloudtrail import DemoCloudTrailSource
from aws_integration.simulate import AwsPolicySimulator

TRUST_POLICY = json.dumps(
    {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}]}
)

INLINE_POLICY = json.dumps(
    {
        "Version": "2012-10-17",
        "Statement": [
            {"Effect": "Allow", "Action": ["s3:GetObject", "s3:DeleteBucket", "s3:PutObject"], "Resource": "*"},
        ],
    }
)

REQUEST = "Review IAM access for the data-pipeline role over the last 90 days."


def _now_events():
    return {
        "data-pipeline": [
            {
                "event_time": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(),
                "action": "s3:GetObject",
                "resource_arns": [],
            },
            {
                # Used once, long ago -> a candidate WITH a real historical event to
                # replay, so the AWS-vs-reference cross-check actually gets exercised
                # (unlike s3:DeleteBucket below, which has zero matching events at all).
                "event_time": (datetime.now(timezone.utc) - timedelta(days=200)).isoformat(),
                "action": "s3:PutObject",
                "resource_arns": [],
            },
            # s3:DeleteBucket never appears -> candidate for removal, no events to replay
        ]
    }


@pytest.fixture
def moto_setup():
    with mock_aws():
        iam = boto3.client("iam", region_name="us-east-1")
        iam.create_role(RoleName="data-pipeline", AssumeRolePolicyDocument=TRUST_POLICY)
        iam.put_role_policy(RoleName="data-pipeline", PolicyName="inline-perms", PolicyDocument=INLINE_POLICY)
        yield


def _orchestrator():
    iam_client = AwsIamClient(region="us-east-1")
    cloudtrail = DemoCloudTrailSource(_now_events())
    simulator = AwsPolicySimulator(region="us-east-1")  # will hit moto's NotImplementedError -> falls back
    return Orchestrator(iam=iam_client, cloudtrail=cloudtrail, simulator=simulator, trueforge=None)


def test_no_revoke_before_approval(moto_setup):
    orch = _orchestrator()
    run = orch.run(REQUEST)
    assert run.status == "awaiting_approval", run.error

    safe_actions = {r.candidate.action for r in run.results if r.safe_to_remove}
    unsafe_actions = {r.candidate.action for r in run.results if not r.safe_to_remove}
    assert "s3:GetObject" not in safe_actions and "s3:GetObject" not in unsafe_actions  # used -> not a candidate at all
    # s3:DeleteBucket has ZERO evidence of ever being called -> confidently safe.
    assert "s3:DeleteBucket" in safe_actions
    # s3:PutObject WAS actually called once (200 days ago) and nothing else grants
    # it -> replay proves that exact historical call would now be denied, so it's
    # excluded from the auto-approved list even though it also passes the "quiet
    # for 90 days" heuristic AWS Access Analyzer alone would use to flag it.
    assert "s3:PutObject" in unsafe_actions
    put_result = next(r for r in run.results if r.candidate.action == "s3:PutObject")
    assert len(put_result.broken_events) == 1

    # Confirm IAM was NOT touched yet.
    iam = boto3.client("iam", region_name="us-east-1")
    doc = iam.get_role_policy(RoleName="data-pipeline", PolicyName="inline-perms")["PolicyDocument"]
    assert "s3:DeleteBucket" in doc["Statement"][0]["Action"]

    orch.reject(run)
    assert run.status == "rejected"
    doc_after_reject = iam.get_role_policy(RoleName="data-pipeline", PolicyName="inline-perms")["PolicyDocument"]
    assert "s3:DeleteBucket" in doc_after_reject["Statement"][0]["Action"]


def test_cannot_commit_a_run_that_was_never_approved(moto_setup):
    orch = _orchestrator()
    run = orch.run(REQUEST)
    orch.reject(run)
    with pytest.raises(ValueError):
        orch.commit_and_verify(run)


def test_successful_approve_commit_and_verify(moto_setup):
    orch = _orchestrator()
    run = orch.run(REQUEST)
    assert run.status == "awaiting_approval"
    assert run.validator_source == "reference (demo mode)"

    orch.commit_and_verify(run)

    assert run.status == "verified"
    assert run.verify_result["verified"] is True
    # Only s3:DeleteBucket is auto-approved; s3:PutObject was flagged (real
    # historical use, no redundant grant) and left for a separate manual decision.
    assert run.verify_result["permissions_removed"] == 1

    iam = boto3.client("iam", region_name="us-east-1")
    doc = iam.get_role_policy(RoleName="data-pipeline", PolicyName="inline-perms")["PolicyDocument"]
    actions = doc["Statement"][0]["Action"]
    actions = [actions] if isinstance(actions, str) else actions
    assert "s3:DeleteBucket" not in actions
    assert "s3:PutObject" in actions  # left alone — flagged, not auto-removed
    assert "s3:GetObject" in actions  # untouched — it was actually used
