"""
A small, controlled AWS IAM client — the ONLY place in Blast Radius that
speaks the IAM API. Mirrors the earlier BuildPlan project's
integrations/openproject/client.py philosophy: a narrow, typed surface, one
gated write path, no arbitrary API access handed to the agent.

Works against a real AWS account or a moto-mocked one interchangeably — both
go through the same boto3 client, so the exact same code path is exercised
either way (see server/tests, which run against moto).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from blast_radius.local_evaluator import SimpleStatement, statements_from_json
from blast_radius.model import AttachedPolicy, Role


class IamError(Exception):
    pass


class IamUnavailable(IamError):
    pass


class IamNotFound(IamError):
    pass


@dataclass
class AwsIamClient:
    region: str = "us-east-1"
    profile: Optional[str] = None
    endpoint_url: Optional[str] = None  # set to point at a moto_server / LocalStack demo endpoint

    def __post_init__(self):
        session = boto3.Session(profile_name=self.profile) if self.profile else boto3.Session()
        self._iam = session.client("iam", region_name=self.region, endpoint_url=self.endpoint_url)

    # ---------------- reads ----------------

    def list_roles(self, name_prefix: Optional[str] = None) -> list[dict]:
        try:
            roles = []
            paginator = self._iam.get_paginator("list_roles")
            for page in paginator.paginate():
                roles.extend(page["Roles"])
        except ClientError as e:
            raise IamUnavailable(str(e)) from e
        if name_prefix:
            roles = [r for r in roles if r["RoleName"].startswith(name_prefix)]
        return roles

    def get_role(self, role_name: str) -> Role:
        try:
            raw = self._iam.get_role(RoleName=role_name)["Role"]
        except self._iam.exceptions.NoSuchEntityException as e:
            raise IamNotFound(f"Role not found: {role_name}") from e
        except ClientError as e:
            raise IamUnavailable(str(e)) from e

        policies = self._get_attached_managed_policies(role_name) + self._get_inline_policies(role_name)
        return Role(name=role_name, arn=raw["Arn"], create_date=raw.get("CreateDate"), policies=policies)

    def _get_attached_managed_policies(self, role_name: str) -> list[AttachedPolicy]:
        out = []
        attached = self._iam.list_attached_role_policies(RoleName=role_name)["AttachedPolicies"]
        for p in attached:
            version_id = self._iam.get_policy(PolicyArn=p["PolicyArn"])["Policy"]["DefaultVersionId"]
            doc = self._iam.get_policy_version(PolicyArn=p["PolicyArn"], VersionId=version_id)["PolicyVersion"]["Document"]
            doc = doc if isinstance(doc, dict) else json.loads(doc)
            stmts = doc["Statement"]
            stmts = stmts if isinstance(stmts, list) else [stmts]
            out.append(AttachedPolicy(kind="managed", name=p["PolicyName"], arn=p["PolicyArn"], statements=_to_model_statements(stmts)))
        return out

    def _get_inline_policies(self, role_name: str) -> list[AttachedPolicy]:
        out = []
        names = self._iam.list_role_policies(RoleName=role_name)["PolicyNames"]
        for name in names:
            doc = self._iam.get_role_policy(RoleName=role_name, PolicyName=name)["PolicyDocument"]
            doc = doc if isinstance(doc, dict) else json.loads(doc)
            stmts = doc["Statement"]
            stmts = stmts if isinstance(stmts, list) else [stmts]
            out.append(AttachedPolicy(kind="inline", name=name, arn=None, statements=_to_model_statements(stmts)))
        return out

    # ---------------- the ONE write path ----------------

    def revoke_actions(self, role_name: str, policy_name: str, policy_kind: str, policy_arn: Optional[str], actions_to_remove: list[str]) -> dict:
        """
        Rewrites exactly one policy (inline or customer-managed) to drop the
        given literal actions from whichever Allow statements grant them.
        Never touches any other policy, statement, or field.
        """
        if policy_kind == "inline":
            doc = self._iam.get_role_policy(RoleName=role_name, PolicyName=policy_name)["PolicyDocument"]
            doc = doc if isinstance(doc, dict) else json.loads(doc)
            new_doc = _remove_actions_from_document(doc, actions_to_remove)
            self._iam.put_role_policy(RoleName=role_name, PolicyName=policy_name, PolicyDocument=json.dumps(new_doc))
            return {"status": "committed", "policy_kind": "inline", "policy_name": policy_name, "new_document": new_doc}
        else:
            version_id = self._iam.get_policy(PolicyArn=policy_arn)["Policy"]["DefaultVersionId"]
            doc = self._iam.get_policy_version(PolicyArn=policy_arn, VersionId=version_id)["PolicyVersion"]["Document"]
            doc = doc if isinstance(doc, dict) else json.loads(doc)
            new_doc = _remove_actions_from_document(doc, actions_to_remove)
            # Prune old non-default versions first — IAM allows at most 5 versions per policy.
            versions = self._iam.list_policy_versions(PolicyArn=policy_arn)["Versions"]
            non_default = sorted([v for v in versions if not v["IsDefaultVersion"]], key=lambda v: v["CreateDate"])
            while len(versions) - len(non_default) + len(non_default) >= 5 and non_default:
                self._iam.delete_policy_version(PolicyArn=policy_arn, VersionId=non_default.pop(0)["VersionId"])
            self._iam.create_policy_version(PolicyArn=policy_arn, PolicyDocument=json.dumps(new_doc), SetAsDefault=True)
            return {"status": "committed", "policy_kind": "managed", "policy_arn": policy_arn, "new_document": new_doc}

    def last_accessed_details(self, role_arn: str) -> Optional[dict]:
        """Best-effort: kick off + poll a generate-service-last-accessed-details
        job. Returns None if unsupported (e.g. under moto) rather than failing
        the whole review — this is a supplementary signal, not load-bearing."""
        try:
            job_id = self._iam.generate_service_last_accessed_details(Arn=role_arn)["JobId"]
            return self._iam.get_service_last_accessed_details(JobId=job_id)
        except Exception:
            return None


def _to_model_statements(raw_statements: list[dict]) -> list:
    parsed = statements_from_json(raw_statements)
    return parsed


def _remove_actions_from_document(doc: dict, actions_to_remove: list[str]) -> dict:
    to_remove = set(actions_to_remove)
    new_statements = []
    for stmt in doc.get("Statement", []) if isinstance(doc.get("Statement"), list) else [doc.get("Statement")]:
        if stmt.get("Effect") != "Allow":
            new_statements.append(stmt)
            continue
        action = stmt.get("Action")
        actions = [action] if isinstance(action, str) else list(action or [])
        remaining = [a for a in actions if a not in to_remove]
        if not remaining:
            continue  # statement fully removed
        new_stmt = dict(stmt)
        new_stmt["Action"] = remaining if len(remaining) > 1 or not isinstance(action, str) else remaining[0]
        new_statements.append(new_stmt)
    return {**doc, "Statement": new_statements}
