"""
Tests for GET /api/roles and GET /api/roles/{role}/actions — the endpoints
backing the /check page's autocomplete, so it suggests real roles and real
granted actions instead of the user having to guess or mistype either.
"""
from __future__ import annotations

import json

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

TRUST_POLICY = json.dumps(
    {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}]}
)
INLINE_POLICY = json.dumps(
    {
        "Version": "2012-10-17",
        "Statement": [
            {"Effect": "Allow", "Action": ["s3:GetObject", "s3:DeleteObject"], "Resource": "*"},
            {"Effect": "Allow", "Action": "s3:*", "Resource": "*"},  # wildcard -- must never appear in autocomplete
        ],
    }
)


@pytest.fixture
def app_client(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.delenv("AWS_ENDPOINT_URL", raising=False)
    monkeypatch.delenv("TRUEFORGE_BASE_URL", raising=False)

    with mock_aws():
        iam = boto3.client("iam", region_name="us-east-1")
        iam.create_role(RoleName="checker-role", AssumeRolePolicyDocument=TRUST_POLICY)
        iam.put_role_policy(RoleName="checker-role", PolicyName="perms", PolicyDocument=INLINE_POLICY)

        import importlib

        import main as main_module

        importlib.reload(main_module)  # pick up the monkeypatched env vars
        yield TestClient(main_module.app)


def test_list_roles_returns_real_roles(app_client):
    res = app_client.get("/api/roles")
    assert res.status_code == 200
    names = [r["role_name"] for r in res.json()]
    assert "checker-role" in names


def test_list_roles_prefix_filters(app_client):
    res = app_client.get("/api/roles", params={"prefix": "checker"})
    assert res.status_code == 200
    assert all(r["role_name"].startswith("checker") for r in res.json())

    res_none = app_client.get("/api/roles", params={"prefix": "nonexistent-prefix"})
    assert res_none.json() == []


def test_list_role_actions_excludes_wildcards(app_client):
    res = app_client.get("/api/roles/checker-role/actions")
    assert res.status_code == 200
    actions = res.json()
    assert set(actions) == {"s3:GetObject", "s3:DeleteObject"}
    assert "s3:*" not in actions


def test_list_role_actions_unknown_role_is_404(app_client):
    res = app_client.get("/api/roles/does-not-exist/actions")
    assert res.status_code == 404
