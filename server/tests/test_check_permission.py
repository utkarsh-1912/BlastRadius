"""
Tests for the standalone permission check (Orchestrator.check_permission) —
a read-only, no-approval-needed blast-radius lookup for a single
(role, action) pair, used by POST /api/check and the "Check a permission"
panel in the UI.
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
    {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": ["s3:GetObject", "s3:DeleteBucket"], "Resource": "*"}]}
)


@pytest.fixture
def moto_role():
    with mock_aws():
        iam = boto3.client("iam", region_name="us-east-1")
        iam.create_role(RoleName="checker-role", AssumeRolePolicyDocument=TRUST_POLICY)
        iam.put_role_policy(RoleName="checker-role", PolicyName="perms", PolicyDocument=INLINE_POLICY)
        yield


def _orchestrator(events=None):
    iam_client = AwsIamClient(region="us-east-1")
    cloudtrail = DemoCloudTrailSource(events or {})
    simulator = AwsPolicySimulator(region="us-east-1")
    return Orchestrator(iam=iam_client, cloudtrail=cloudtrail, simulator=simulator, trueforge=None)


def test_check_permission_never_used_is_safe(moto_role):
    orch = _orchestrator()
    result = orch.check_permission("checker-role", "s3:DeleteBucket")
    assert result["granted"] is True
    assert result["safe_to_remove"] is True
    assert result["events_checked"] == 0


def test_check_permission_currently_used_is_not_safe(moto_role):
    events = {
        "checker-role": [
            {"event_time": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(), "action": "s3:DeleteBucket", "resource_arns": []}
        ]
    }
    orch = _orchestrator(events)
    result = orch.check_permission("checker-role", "s3:DeleteBucket")
    assert result["safe_to_remove"] is False
    assert result["broken_event_count"] == 1


def test_check_permission_not_granted():
    with mock_aws():
        iam = boto3.client("iam", region_name="us-east-1")
        iam.create_role(RoleName="empty-role", AssumeRolePolicyDocument=TRUST_POLICY)
        orch = _orchestrator()
        result = orch.check_permission("empty-role", "s3:DeleteBucket")
        assert result["granted"] is False


def test_check_permission_never_writes_anything(moto_role):
    """A standalone check must never call the write path."""
    orch = _orchestrator()
    orch.check_permission("checker-role", "s3:DeleteBucket")
    # Confirm the policy is completely untouched.
    iam = boto3.client("iam", region_name="us-east-1")
    doc = iam.get_role_policy(RoleName="checker-role", PolicyName="perms")["PolicyDocument"]
    actions = doc["Statement"][0]["Action"]
    assert "s3:DeleteBucket" in actions
    assert "s3:GetObject" in actions
