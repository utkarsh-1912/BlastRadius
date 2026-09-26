"""
The AUTHORITATIVE half of the independent-validator pair: calls AWS's own
policy evaluation engine (`iam:SimulateCustomPolicy`) — a real, read-only,
side-effect-free AWS API — against the same hypothetical policy (role's
statements with the candidate action removed) that the sandbox's local
evaluator already scored. blast_radius/validator.py cross-checks the two
verdicts per event and only calls a permission "safe to remove" when every
single event agrees.

We deliberately use SimulateCustomPolicy (evaluate an arbitrary policy
document) rather than SimulatePrincipalPolicy (evaluate a real principal's
actual attached policies) — Blast Radius needs to ask AWS "what would THIS
hypothetical policy allow", not "what does the role's current policy allow",
and SimulateCustomPolicy is the API built for exactly that.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from blast_radius.local_evaluator import SimpleStatement
from blast_radius.model import HistoricalEvent


def statements_to_policy_document(statements: list[SimpleStatement]) -> dict:
    stmts = []
    for s in statements:
        d: dict = {"Effect": s.effect}
        if s.actions:
            d["Action"] = s.actions
        if s.not_actions:
            d["NotAction"] = s.not_actions
        if s.resources:
            d["Resource"] = s.resources
        if s.not_resources:
            d["NotResource"] = s.not_resources
        stmts.append(d)
    return {"Version": "2012-10-17", "Statement": stmts}


@dataclass
class AwsPolicySimulator:
    region: str = "us-east-1"
    profile: Optional[str] = None
    endpoint_url: Optional[str] = None

    def __post_init__(self):
        session = boto3.Session(profile_name=self.profile) if self.profile else boto3.Session()
        self._iam = session.client("iam", region_name=self.region, endpoint_url=self.endpoint_url)

    def simulate(self, hypothetical_statements: list[SimpleStatement], action: str, resource_arns: list[str]) -> str:
        """Returns "allow" or "deny" from AWS's own evaluator for one action+resource."""
        doc = statements_to_policy_document(hypothetical_statements)
        kwargs = {"PolicyInputList": [json.dumps(doc)], "ActionNames": [action]}
        if resource_arns:
            kwargs["ResourceArns"] = list(resource_arns)
        try:
            resp = self._iam.simulate_custom_policy(**kwargs)
        except ClientError as e:
            raise RuntimeError(f"simulate_custom_policy failed: {e}") from e

        results = resp.get("EvaluationResults", [])
        if not results:
            return "deny"
        # If evaluated per-resource, ANY denial across the resource set counts as a
        # break (fail-closed: a candidate is only "safe" if it's safe for everything observed).
        for r in results:
            if r.get("EvalDecision") != "allowed":
                return "deny"
        return "allow"

    def simulate_batch(
        self, hypothetical_statements: list[SimpleStatement], events: list[HistoricalEvent], event_indices: list[int]
    ) -> dict[int, str]:
        """Simulate a batch of events (by index into the caller's event list) in as
        few API calls as possible, grouping by identical (action, resources) pairs."""
        doc = statements_to_policy_document(hypothetical_statements)
        out: dict[int, str] = {}
        # Group by (action, tuple(sorted(resource_arns))) to minimize API calls.
        groups: dict[tuple, list[int]] = {}
        for i in event_indices:
            e = events[i]
            key = (e.action, tuple(sorted(e.resource_arns)))
            groups.setdefault(key, []).append(i)

        for (action, resources), indices in groups.items():
            kwargs = {"PolicyInputList": [json.dumps(doc)], "ActionNames": [action]}
            if resources:
                kwargs["ResourceArns"] = list(resources)
            try:
                resp = self._iam.simulate_custom_policy(**kwargs)
            except ClientError as e:
                raise RuntimeError(f"simulate_custom_policy failed: {e}") from e
            results = resp.get("EvaluationResults", [])
            verdict = "allow" if results and all(r.get("EvalDecision") == "allowed" for r in results) else "deny"
            for i in indices:
                out[i] = verdict
        return out
