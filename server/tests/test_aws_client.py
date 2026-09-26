"""
Tests for AwsIamClient against moto's mocked IAM — real boto3 calls, real
IAM API semantics, just no real AWS account. This proves revoke_actions()
actually mutates policy state and get_role() correctly re-reads it, without
needing real credentials for CI.
"""
from __future__ import annotations

import json

import boto3
import pytest
from moto import mock_aws

from aws_integration.client import AwsIamClient

TRUST_POLICY = json.dumps(
    {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}]}
)

INLINE_POLICY = json.dumps(
    {
        "Version": "2012-10-17",
        "Statement": [
            {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], "Resource": "*"},
            {"Effect": "Allow", "Action": "dynamodb:Scan", "Resource": "*"},
        ],
    }
)


@pytest.fixture
def moto_iam():
    with mock_aws():
        iam = boto3.client("iam", region_name="us-east-1")
        iam.create_role(RoleName="data-pipeline", AssumeRolePolicyDocument=TRUST_POLICY)
        iam.put_role_policy(RoleName="data-pipeline", PolicyName="inline-perms", PolicyDocument=INLINE_POLICY)
        yield


def test_get_role_parses_inline_policy(moto_iam):
    client = AwsIamClient(region="us-east-1")
    role = client.get_role("data-pipeline")
    assert role.name == "data-pipeline"
    inline = [p for p in role.policies if p.kind == "inline"]
    assert len(inline) == 1
    actions = {a for stmt in inline[0].statements for a in stmt.actions}
    assert actions == {"s3:GetObject", "s3:PutObject", "s3:DeleteObject", "dynamodb:Scan"}


def test_revoke_actions_removes_only_the_named_action(moto_iam):
    client = AwsIamClient(region="us-east-1")
    result = client.revoke_actions(
        role_name="data-pipeline", policy_name="inline-perms", policy_kind="inline", policy_arn=None, actions_to_remove=["s3:DeleteObject"]
    )
    assert result["status"] == "committed"

    role = client.get_role("data-pipeline")
    inline = [p for p in role.policies if p.kind == "inline"][0]
    actions = {a for stmt in inline.statements for a in stmt.actions}
    assert "s3:DeleteObject" not in actions
    assert {"s3:GetObject", "s3:PutObject", "dynamodb:Scan"}.issubset(actions)


def test_revoke_actions_drops_statement_entirely_if_it_becomes_empty(moto_iam):
    client = AwsIamClient(region="us-east-1")
    client.revoke_actions(
        role_name="data-pipeline", policy_name="inline-perms", policy_kind="inline", policy_arn=None, actions_to_remove=["dynamodb:Scan"]
    )
    role = client.get_role("data-pipeline")
    inline = [p for p in role.policies if p.kind == "inline"][0]
    all_actions = [a for stmt in inline.statements for a in stmt.actions]
    assert "dynamodb:Scan" not in all_actions
    # the s3 statement must be untouched
    assert {"s3:GetObject", "s3:PutObject", "s3:DeleteObject"}.issubset(set(all_actions))


def test_get_role_not_found_raises_typed_error(moto_iam):
    from aws_integration.client import IamNotFound

    client = AwsIamClient(region="us-east-1")
    with pytest.raises(IamNotFound):
        client.get_role("does-not-exist")
