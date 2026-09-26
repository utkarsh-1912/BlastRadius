"""
A customer-managed policy attached to multiple roles must be proven safe
across EVERY attached role's own history before it's proposed for removal —
revoking it rewrites the policy's default version, which affects every
attachment, not just the one role a review happened to start from.
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

SHARED_POLICY_DOC = json.dumps(
    {
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Action": ["s3:GetObject", "s3:DeleteObject"], "Resource": "*"}],
    }
)


@pytest.fixture
def moto_two_roles_one_shared_policy():
    with mock_aws():
        iam = boto3.client("iam", region_name="us-east-1")
        iam.create_role(RoleName="worker-a", AssumeRolePolicyDocument=TRUST_POLICY)
        iam.create_role(RoleName="worker-b", AssumeRolePolicyDocument=TRUST_POLICY)
        policy = iam.create_policy(PolicyName="shared-s3-access", PolicyDocument=SHARED_POLICY_DOC)["Policy"]
        iam.attach_role_policy(RoleName="worker-a", PolicyArn=policy["Arn"])
        iam.attach_role_policy(RoleName="worker-b", PolicyArn=policy["Arn"])
        yield policy["Arn"]


def _orchestrator(events_by_role: dict):
    iam_client = AwsIamClient(region="us-east-1")
    cloudtrail = DemoCloudTrailSource(events_by_role)
    simulator = AwsPolicySimulator(region="us-east-1")  # falls back to reference evaluator under moto
    return Orchestrator(iam=iam_client, cloudtrail=cloudtrail, simulator=simulator, trueforge=None)


def test_shared_policy_excluded_when_other_role_still_uses_it(moto_two_roles_one_shared_policy):
    """s3:DeleteObject looks unused on worker-a, but worker-b (which shares the
    same managed policy) actually used it recently — the shared check must
    catch this and exclude it, even though reviewing worker-a alone would not."""
    events = {
        "worker-a": [{"event_time": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(), "action": "s3:GetObject", "resource_arns": []}],
        "worker-b": [
            {"event_time": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(), "action": "s3:GetObject", "resource_arns": []},
            {"event_time": (datetime.now(timezone.utc) - timedelta(days=200)).isoformat(), "action": "s3:DeleteObject", "resource_arns": []},
        ],
    }
    orch = _orchestrator(events)
    run = orch.run("Review IAM access for the worker-a role over the last 90 days.")
    assert run.status == "awaiting_approval", run.error

    delete_result = next(r for r in run.results if r.candidate.action == "s3:DeleteObject")
    assert delete_result.candidate.shared_with_roles == ["worker-b"]
    assert delete_result.safe_to_remove is False, "must not propose removing a permission another attached role actually used"


def test_shared_policy_safe_when_no_other_role_uses_it(moto_two_roles_one_shared_policy):
    """If neither attached role has ever used s3:DeleteObject, it's genuinely safe."""
    events = {
        "worker-a": [{"event_time": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(), "action": "s3:GetObject", "resource_arns": []}],
        "worker-b": [{"event_time": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(), "action": "s3:GetObject", "resource_arns": []}],
    }
    orch = _orchestrator(events)
    run = orch.run("Review IAM access for the worker-a role over the last 90 days.")
    assert run.status == "awaiting_approval", run.error

    delete_result = next(r for r in run.results if r.candidate.action == "s3:DeleteObject")
    assert delete_result.safe_to_remove is True
    assert set(delete_result.candidate.shared_with_roles) == {"worker-b"}


def test_commit_on_shared_managed_policy_is_written_once_and_verified_on_both_roles(moto_two_roles_one_shared_policy):
    events = {
        "worker-a": [{"event_time": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(), "action": "s3:GetObject", "resource_arns": []}],
        "worker-b": [{"event_time": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(), "action": "s3:GetObject", "resource_arns": []}],
    }
    orch = _orchestrator(events)
    run = orch.run("Review IAM access for the worker-a role over the last 90 days.")
    assert run.status == "awaiting_approval"

    orch.commit_and_verify(run)
    assert run.status == "verified", run.error
    assert run.verify_result["roles_updated"] == 2  # both attached roles verified

    iam = boto3.client("iam", region_name="us-east-1")
    policy_arn = moto_two_roles_one_shared_policy
    version_id = iam.get_policy(PolicyArn=policy_arn)["Policy"]["DefaultVersionId"]
    doc = iam.get_policy_version(PolicyArn=policy_arn, VersionId=version_id)["PolicyVersion"]["Document"]
    actions = doc["Statement"][0]["Action"]
    actions = [actions] if isinstance(actions, str) else actions
    assert "s3:DeleteObject" not in actions
    assert "s3:GetObject" in actions
    # Confirm it was written exactly once (only one non-default-superseding version created).
    versions = iam.list_policy_versions(PolicyArn=policy_arn)["Versions"]
    assert len(versions) == 2  # v1 (original) + v2 (the one write)
