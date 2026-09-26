"""
The Blast Radius agent workflow: UNDERSTAND -> RETRIEVE -> IDENTIFY
CANDIDATES -> SANDBOX SIMULATE -> VALIDATE -> EXPLAIN -> STOP -> APPROVE ->
COMMIT -> VERIFY.

Mirrors the separation-of-concerns discipline from this team's earlier
BuildPlan project, applied to IAM instead of construction scheduling:

    LLM / heuristic  = understand the request, explain the result
    Local evaluator  = deterministic sandbox computation (no AWS creds)
    AWS evaluator    = independent, authoritative cross-check (real AWS API)
    Human            = approval of the one consequential action (revoke)
    AWS IAM          = system of record

`commit_and_verify()` is the only method that ever calls
`AwsIamClient.revoke_actions()`, and it refuses to run unless the run's
status is `awaiting_approval` — see tests/test_no_revoke_before_approval.py.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from agent.understand import UnderstoodRequest, understand_heuristic
from agent.trueforge_client import TrueForgeClient, TrueForgeUnavailable
from aws_integration.client import AwsIamClient, IamError, IamNotFound, IamUnavailable
from aws_integration.cloudtrail import CloudTrailSource, DemoCloudTrailSource
from aws_integration.simulate import AwsPolicySimulator
from blast_radius.candidates import find_candidates
from blast_radius.local_evaluator import remove_action, statements_from_json
from blast_radius.model import AttachedPolicy, BlastRadiusResult, HistoricalEvent, Role
from blast_radius.reference_evaluator import ReferenceEvaluator
from blast_radius.sandbox_code import render_sandbox_script
from blast_radius.simulator import plain_to_role_statements, role_statements_to_plain, run_local_replay
from blast_radius.validator import validate_candidate


def _all_statements(role: Role) -> list:
    return [s for policy in role.policies for s in policy.statements]


@dataclass
class TimelineEvent:
    ts: float
    label: str
    detail: str = ""
    kind: str = "info"

    def to_dict(self) -> dict:
        return {"ts": self.ts, "label": self.label, "detail": self.detail, "kind": self.kind}


@dataclass
class ReviewRun:
    id: str
    request_text: str
    status: str = "running"  # running | no_candidates | awaiting_approval | approved | rejected | committed | verified | failed
    timeline: list[TimelineEvent] = field(default_factory=list)
    understood: Optional[dict] = None
    error: Optional[str] = None
    sandbox_used: bool = False
    validator_source: Optional[str] = None  # "aws" | "reference (demo mode)"
    results: list[BlastRadiusResult] = field(default_factory=list)
    role_snapshot: dict[str, Role] = field(default_factory=dict)  # role_name -> Role at RETRIEVE time
    verify_result: Optional[dict] = None

    def log(self, label: str, detail: str = "", kind: str = "info") -> None:
        self.timeline.append(TimelineEvent(ts=time.time(), label=label, detail=detail, kind=kind))

    def to_dict(self) -> dict:
        safe = [r for r in self.results if r.safe_to_remove]
        unsafe = [r for r in self.results if not r.safe_to_remove]
        return {
            "id": self.id,
            "request_text": self.request_text,
            "status": self.status,
            "timeline": [e.to_dict() for e in self.timeline],
            "understood": self.understood,
            "error": self.error,
            "sandbox_used": self.sandbox_used,
            "validator_source": self.validator_source,
            "safe_changes": [r.to_dict() for r in safe],
            "unsafe_candidates": [r.to_dict() for r in unsafe],
            "total_candidates": len(self.results),
            "verify_result": self.verify_result,
        }


class Orchestrator:
    def __init__(
        self,
        iam: Optional[AwsIamClient] = None,
        cloudtrail=None,
        simulator: Optional[AwsPolicySimulator] = None,
        trueforge: Optional[TrueForgeClient] = None,
    ):
        self.iam = iam
        self.cloudtrail = cloudtrail
        self.simulator = simulator
        self.trueforge = trueforge

    # ---------------- UNDERSTAND ----------------

    def understand(self, run: ReviewRun) -> UnderstoodRequest:
        run.log("Understanding request", run.request_text)
        u = understand_heuristic(run.request_text)
        run.understood = u.to_dict()
        run.log(
            "Extracted parameters",
            f"role={u.role_name or u.role_prefix or 'all roles'}, lookback={u.lookback_days}d, "
            f"{len(u.exclude_role_patterns)} role exclusion pattern(s)",
            kind="success",
        )
        return u

    # ---------------- RETRIEVE ----------------

    def retrieve(self, run: ReviewRun, understood: UnderstoodRequest) -> list[Role]:
        if self.iam is None:
            run.status = "failed"
            run.error = "AWS IAM is not configured. No changes were made."
            run.log("AWS not configured", run.error, kind="error")
            raise IamUnavailable(run.error)

        try:
            if understood.role_name:
                raw_roles = [r for r in self.iam.list_roles() if r["RoleName"].lower() == understood.role_name.lower()]
                if not raw_roles:
                    raw_roles = self.iam.list_roles(name_prefix=understood.role_name)
            else:
                raw_roles = self.iam.list_roles(name_prefix=understood.role_prefix)
            run.log("Connected to AWS IAM", f"{len(raw_roles)} role(s) matched", kind="success")
        except IamError as e:
            run.status = "failed"
            run.error = f"Unable to connect to AWS IAM. No changes were made. ({e})"
            run.log("Unable to connect to AWS IAM", str(e), kind="error")
            raise

        import fnmatch

        def excluded(name: str) -> bool:
            return any(fnmatch.fnmatch(name.lower(), p.lower()) for p in understood.exclude_role_patterns)

        roles: list[Role] = []
        for raw in raw_roles:
            name = raw["RoleName"]
            if excluded(name):
                continue
            roles.append(self.iam.get_role(name))
        run.log("Retrieved role policies", f"{len(roles)} role(s) after exclusions", kind="success")
        for role in roles:
            run.role_snapshot[role.name] = role
        return roles

    def retrieve_events(self, run: ReviewRun, role: Role, lookback_days: int) -> list[HistoricalEvent]:
        try:
            events = self.cloudtrail.lookup_events_for_principal(role.arn, lookback_days=max(lookback_days, 90))
            if isinstance(self.cloudtrail, DemoCloudTrailSource):
                run.log(
                    f"Using exported CloudTrail history for {role.name}",
                    f"{len(events)} events (demo export — see data/demo_cloudtrail_events.json)",
                    kind="warn",
                )
            else:
                run.log(f"Retrieved CloudTrail history for {role.name}", f"{len(events)} events", kind="success")
            return events
        except Exception as e:
            run.log(f"CloudTrail lookup failed for {role.name}", str(e), kind="error")
            return []

    # ---------------- IDENTIFY CANDIDATES + SIMULATE + VALIDATE ----------------

    def review_role(self, run: ReviewRun, role: Role, events: list[HistoricalEvent], understood: UnderstoodRequest) -> list[BlastRadiusResult]:
        candidates = find_candidates(role, events, understood.lookback_days, understood.exclude_actions)
        if not candidates:
            run.log(f"No unused permissions found for {role.name}", kind="info")
            return []
        run.log(f"Identified {len(candidates)} candidate permission(s) for {role.name}", kind="info")

        all_stmts = _all_statements(role)
        results = []
        for candidate in candidates:
            hypothetical = remove_action(all_stmts, candidate.action)
            local_verdicts = self._sandbox_replay(run, candidate, all_stmts, events)
            result = self._validate(run, candidate, hypothetical, events, local_verdicts)
            results.append(result)
        return results

    def _sandbox_replay(self, run: ReviewRun, candidate, all_stmts, events) -> list[dict]:
        if self.trueforge is not None:
            try:
                script = render_sandbox_script(candidate, all_stmts, events)
                stdout = self.trueforge.exec_python(script)  # type: ignore[attr-defined]
                run.sandbox_used = True
                import json
                import re

                m = re.search(r"RESULT_JSON:(\{.*\})", stdout)
                if m:
                    return json.loads(m.group(1))["verdicts"]
            except TrueForgeUnavailable as e:
                run.log("TrueForge sandbox unavailable", f"{e} — replaying locally instead.", kind="warn")
        return run_local_replay(candidate, all_stmts, events)

    def _validate(self, run: ReviewRun, candidate, hypothetical, events, local_verdicts) -> BlastRadiusResult:
        simulator = self.simulator
        if simulator is not None:
            try:
                result = validate_candidate(candidate, hypothetical, events, local_verdicts, simulator)
                run.validator_source = "aws"
                return result
            except Exception as e:
                # Covers moto's NotImplementedError (in-process mock_aws), moto_server's
                # HTTP 500 for the same unimplemented action (a parsing error, not a clean
                # exception type), and any other reason the real AWS call didn't come back
                # clean — in every case, fail over to the reference evaluator rather than
                # crash the run, and say plainly that this run did not use the real AWS API.
                if run.validator_source != "reference (demo mode)":
                    run.log(
                        "Real AWS policy simulator unavailable",
                        f"Falling back to the independent reference evaluator instead of the real AWS API. ({e})",
                        kind="warn",
                    )
                    run.validator_source = "reference (demo mode)"
        return validate_candidate(candidate, hypothetical, events, local_verdicts, ReferenceEvaluator())

    # ---------------- full run ----------------

    def run(self, request_text: str) -> ReviewRun:
        run = ReviewRun(id=str(uuid.uuid4()), request_text=request_text)
        try:
            understood = self.understand(run)
            roles = self.retrieve(run, understood)
            all_results: list[BlastRadiusResult] = []
            for role in roles:
                events = self.retrieve_events(run, role, understood.lookback_days)
                all_results.extend(self.review_role(run, role, events, understood))
            run.results = all_results

            safe = [r for r in all_results if r.safe_to_remove]
            unsafe = [r for r in all_results if not r.safe_to_remove]
            if not all_results:
                run.status = "no_candidates"
                run.log("No unused permissions found", "Nothing to propose. No changes were made.", kind="info")
                return run

            run.log(
                "Blast radius analysis complete",
                f"{len(safe)} permission(s) safe to remove (validated by two independent evaluators), "
                f"{len(unsafe)} flagged as risky or ambiguous and excluded from the proposal",
                kind="success",
            )
            run.log("Waiting for human approval", "No changes have been made to AWS IAM.", kind="waiting")
            run.status = "awaiting_approval"
        except (IamUnavailable, IamNotFound):
            pass
        except Exception as e:  # pragma: no cover - defensive catch-all for the demo
            run.status = "failed"
            run.error = str(e)
            run.log("Unexpected error", str(e), kind="error")
        return run

    # ---------------- APPROVAL / REJECTION ----------------

    def reject(self, run: ReviewRun) -> None:
        if run.status != "awaiting_approval":
            raise ValueError(f"Cannot reject a run in status '{run.status}'.")
        run.status = "rejected"
        run.log("Changes rejected", "No changes were made to AWS IAM.", kind="warn")

    # ---------------- COMMIT (only reachable after explicit approval) ----------------

    def commit_and_verify(self, run: ReviewRun) -> None:
        """THE ONLY PATH THAT WRITES TO AWS IAM. Must only be called after
        run.status == 'awaiting_approval' and a human clicked Approve."""
        if run.status != "awaiting_approval":
            raise ValueError(f"Cannot commit a run in status '{run.status}' (must be 'awaiting_approval').")
        run.status = "approved"
        run.log("Approved", "Updating AWS IAM...", kind="info")

        if self.iam is None:
            run.status = "failed"
            run.error = "AWS IAM is not configured; cannot commit. No changes were made."
            run.log("Commit skipped", run.error, kind="error")
            return

        safe = [r for r in run.results if r.safe_to_remove]
        # Group by (role, policy) so each policy is rewritten exactly once.
        groups: dict[tuple, list[str]] = {}
        policy_refs: dict[tuple, AttachedPolicy] = {}
        for r in safe:
            key = (r.candidate.role_name, r.candidate.source_policy.name)
            groups.setdefault(key, []).append(r.candidate.action)
            policy_refs[key] = r.candidate.source_policy

        committed_roles: set[str] = set()
        try:
            for (role_name, policy_name), actions in groups.items():
                policy = policy_refs[(role_name, policy_name)]
                self.iam.revoke_actions(
                    role_name=role_name,
                    policy_name=policy_name,
                    policy_kind=policy.kind,
                    policy_arn=policy.arn,
                    actions_to_remove=actions,
                )
                committed_roles.add(role_name)
                run.log(
                    f"Updated policy '{policy_name}' on role {role_name}",
                    f"Removed: {', '.join(actions)}",
                    kind="success",
                )
        except IamError as e:
            run.status = "failed"
            run.error = f"Blast radius analysis succeeded, but the AWS IAM update failed: {e}"
            run.log("AWS IAM update failed", str(e), kind="error")
            return

        run.status = "committed"
        run.log("Re-reading AWS IAM", "Verifying committed changes...", kind="info")
        self._verify(run, committed_roles, groups)

    def _verify(self, run: ReviewRun, committed_roles: set[str], groups: dict[tuple, list[str]]) -> None:
        mismatches = []
        for role_name in committed_roles:
            fresh = self.iam.get_role(role_name)
            all_current_actions = {a for p in fresh.policies for s in p.statements for a in s.actions}
            for (r_name, p_name), actions in groups.items():
                if r_name != role_name:
                    continue
                for action in actions:
                    if action in all_current_actions:
                        mismatches.append({"role": role_name, "action": action, "issue": "still present after revoke"})

        run.verify_result = {
            "roles_updated": len(committed_roles),
            "permissions_removed": sum(len(a) for a in groups.values()),
            "mismatches": mismatches,
            "verified": not mismatches,
        }
        if run.verify_result["verified"]:
            run.status = "verified"
            run.log(
                "Changes verified",
                f"{len(committed_roles)} role(s) updated, AWS IAM re-read, "
                f"{run.verify_result['permissions_removed']} permission(s) confirmed removed.",
                kind="success",
            )
        else:
            run.status = "failed"
            run.error = "The update could not be fully verified. Do not claim successful execution."
            run.log("Verification failed", run.error, kind="error")
