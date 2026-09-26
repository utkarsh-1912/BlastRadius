#!/usr/bin/env python
"""
Creates the demo IAM role + inline policy (server/data/demo_role_policy.json)
via real boto3 IAM calls — against a real AWS account if AWS credentials are
configured, or against a local `moto_server` if AWS_ENDPOINT_URL is set (see
README's "no AWS account yet" path). Either way this exercises the exact
same code as the live app; only the historical usage log
(server/data/demo_cloudtrail_events.json) is a static export, not IAM state
itself.

Usage:
    python scripts/seed_demo_iam.py
"""
from __future__ import annotations

import json
import os
import sys

import boto3
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))

load_dotenv()
from env_utils import clean_blank_env  # noqa: E402

clean_blank_env()

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def main() -> int:
    with open(os.path.join(REPO_ROOT, "server", "data", "demo_role_policy.json"), "r", encoding="utf-8") as f:
        spec = json.load(f)

    region = os.environ.get("AWS_REGION", "us-east-1")
    endpoint_url = os.environ.get("AWS_ENDPOINT_URL")
    profile = os.environ.get("AWS_PROFILE")
    session = boto3.Session(profile_name=profile) if profile else boto3.Session()
    iam = session.client("iam", region_name=region, endpoint_url=endpoint_url)

    role_name = spec["role_name"]
    try:
        iam.get_role(RoleName=role_name)
        print(f"Role '{role_name}' already exists — updating its inline policy only.")
    except iam.exceptions.NoSuchEntityException:
        iam.create_role(RoleName=role_name, AssumeRolePolicyDocument=json.dumps(spec["trust_policy"]))
        print(f"Created role '{role_name}'.")

    iam.put_role_policy(
        RoleName=role_name,
        PolicyName=spec["inline_policy_name"],
        PolicyDocument=json.dumps(spec["inline_policy_document"]),
    )
    print(f"Put inline policy '{spec['inline_policy_name']}' on '{role_name}'.")

    role = iam.get_role(RoleName=role_name)["Role"]
    print(f"\nRole ARN: {role['Arn']}")
    print("Demo role is ready. Run the app and try:")
    print('  "Review IAM access for the data-pipeline-role role over the last 90 days."')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
