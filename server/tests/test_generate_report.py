"""
Tests for scripts/generate_report.py — loaded by file path since scripts/ is
a sibling of server/, not a package under it. Runs against moto (no real AWS
needed) and a throwaway output directory.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys

import boto3
import pytest
from moto import mock_aws

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCRIPT_PATH = os.path.join(REPO_ROOT, "scripts", "generate_report.py")

TRUST_POLICY = json.dumps(
    {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}]}
)
INLINE_POLICY = json.dumps(
    {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": ["s3:GetObject", "s3:DeleteBucket"], "Resource": "*"}]}
)


def _load_module():
    spec = importlib.util.spec_from_file_location("generate_report", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def report_module(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.delenv("AWS_ENDPOINT_URL", raising=False)
    return _load_module()


@pytest.fixture
def moto_role():
    with mock_aws():
        iam = boto3.client("iam", region_name="us-east-1")
        iam.create_role(RoleName="report-test-role", AssumeRolePolicyDocument=TRUST_POLICY)
        iam.put_role_policy(RoleName="report-test-role", PolicyName="perms", PolicyDocument=INLINE_POLICY)
        yield


def test_generate_report_writes_markdown_and_persists_history(report_module, moto_role, tmp_path, monkeypatch):
    monkeypatch.setattr("agent.store.DB_PATH", str(tmp_path / "history.sqlite3"))
    output_path = str(tmp_path / "report.md")

    monkeypatch.setattr(sys, "argv", ["generate_report.py", "--role-prefix", "report-test", "--output", output_path])
    exit_code = report_module.main()

    assert exit_code == 0
    assert os.path.exists(output_path)
    content = open(output_path, encoding="utf-8").read()
    assert "report-test-role" in content
    assert "Blast Radius Report" in content
    assert "s3:DeleteBucket" in content  # never used -> safe -> should be named in the report

    from agent import store

    runs = store.list_runs()
    assert len(runs) == 1
    assert runs[0]["role_name"] == "report-test-role"


def test_generate_report_never_writes_to_iam(report_module, moto_role, tmp_path, monkeypatch):
    monkeypatch.setattr("agent.store.DB_PATH", str(tmp_path / "history.sqlite3"))
    monkeypatch.setattr(sys, "argv", ["generate_report.py", "--role-prefix", "report-test", "--output", str(tmp_path / "r.md")])
    report_module.main()

    iam = boto3.client("iam", region_name="us-east-1")
    doc = iam.get_role_policy(RoleName="report-test-role", PolicyName="perms")["PolicyDocument"]
    actions = doc["Statement"][0]["Action"]
    assert set(actions) == {"s3:GetObject", "s3:DeleteBucket"}  # untouched -- report-only, never commits


def test_generate_report_no_matching_roles_is_a_clean_noop(report_module, moto_role, tmp_path, monkeypatch):
    monkeypatch.setattr("agent.store.DB_PATH", str(tmp_path / "history.sqlite3"))
    monkeypatch.setattr(sys, "argv", ["generate_report.py", "--role-prefix", "no-such-prefix", "--output", str(tmp_path / "r.md")])
    exit_code = report_module.main()
    assert exit_code == 0
    assert not os.path.exists(str(tmp_path / "r.md"))
