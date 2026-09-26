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
        # Per-instance caches (a fresh Orchestrator is built per API request —
        # see server/main.py — so this never leaks state across requests).
        # Avoids re-fetching the same role/CloudTrail history twice when a
        # managed policy shared by several roles is checked more than once.
        self._role_cache: dict[str, Role] = {}
        self._events_cache: dict[tuple[str, int], list[HistoricalEvent]] = {}
        self._trueforge_broken = False

    def _get_role_cached(self, role_name: str) -> Role:
        if role_name not in self._role_cache:
            self._role_cache[role_name] = self.iam.get_role(role_name)
        return self._role_cache[role_name]

    def _get_events_cached(self, run: ReviewRun, role: Role, lookback_days: int) -> list[HistoricalEvent]:
        key = (role.name, lookback_days)
        if key not in self._events_cache:
            self._events_cache[key] = self.retrieve_events(run, role, lookback_days)
        return self._events_cache[key]

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
        if u.lookback_capped:
            run.log(
                f"Requested {u.requested_lookback_days} days, capped to {u.lookback_days}",
                "AWS CloudTrail's default Event History only retains the last 90 days of management "
                "events without a dedicated Trail or CloudTrail Lake configured — the lookback window "
                "can't honestly go further back than that against real AWS.",
                kind="warn",
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

        # Service-linked roles are managed by AWS itself and are always
        # excluded, regardless of what the user asked for — Blast Radius
        # never touches them, the same way it never touches iam:PassRole.
        always_excluded_patterns = ["aws-service-role/*", "AWSServiceRoleFor*"]

        def excluded(name: str, path: str) -> bool:
            patterns = understood.exclude_role_patterns + always_excluded_patterns
            return path.startswith("/aws-service-role/") or any(fnmatch.fnmatch(name.lower(), p.lower()) for p in patterns)

        roles: list[Role] = []
        skipped_service_linked = 0
        for raw in raw_roles:
            name = raw["RoleName"]
            if excluded(name, raw.get("Path", "/")):
                if raw.get("Path", "/").startswith("/aws-service-role/"):
                    skipped_service_linked += 1
                continue
            roles.append(self.iam.get_role(name))
        if skipped_service_linked:
            run.log(
                "Skipped AWS service-linked roles",
                f"{skipped_service_linked} role(s) excluded — always excluded by design",
                kind="info",
            )
        run.log("Retrieved role policies", f"{len(roles)} role(s) after exclusions", kind="success")
        for role in roles:
            run.role_snapshot[role.name] = role
            self._role_cache[role.name] = role
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
            result = self._extend_across_shared_attachments(run, candidate, result, understood)
            results.append(result)
        return results

    def _extend_across_shared_attachments(
        self, run: ReviewRun, candidate, primary_result: BlastRadiusResult, understood: UnderstoodRequest
    ) -> BlastRadiusResult:
        """
        A customer-managed policy's `revoke_actions()` rewrites the policy's
        default VERSION — which changes what EVERY role/user/group it's
        attached to can do, not just the role currently being reviewed. Before
        ever calling such a permission safe, replay it against every OTHER
        attached role's own CloudTrail history too, using each role's own full
        statement set (not just the shared policy's). A permission is only
        safe across the board if it's independently safe for every attachment.
        """
        policy = candidate.source_policy
        if policy.kind != "managed" or not policy.arn or self.iam is None:
            return primary_result

        try:
            attachments = self.iam.list_policy_attachments(policy.arn)
        except IamError as e:
            run.log(f"Could not list attachments for shared policy '{policy.name}'", str(e), kind="warn")
            return primary_result

        other_roles = [r for r in attachments.get("roles", []) if r != candidate.role_name]
        if not other_roles:
            return primary_result

        candidate.shared_with_roles = other_roles
        run.log(
            f"Policy '{policy.name}' is shared",
            f"Also attached to {', '.join(other_roles)} — checking blast radius against all of them.",
            kind="info",
        )

        combined_checked = primary_result.events_checked
        combined_agreement = primary_result.validator_agreement
        combined_safe = primary_result.safe_to_remove
        combined_broken = list(primary_result.broken_events)

        for other_name in other_roles:
            try:
                other_role = self._get_role_cached(other_name)
                other_events = self._get_events_cached(run, other_role, understood.lookback_days)
            except IamError as e:
                run.log(f"Could not check shared attachment '{other_name}'", str(e), kind="error")
                combined_safe = False  # fail closed: an attachment we couldn't verify is never "safe"
                continue
            other_stmts = _all_statements(other_role)
            other_local = self._sandbox_replay(run, candidate, other_stmts, other_events)
            other_hyp = remove_action(other_stmts, candidate.action)
            other_result = self._validate(run, candidate, other_hyp, other_events, other_local)
            combined_checked += other_result.events_checked
            combined_agreement = combined_agreement and other_result.validator_agreement
            combined_safe = combined_safe and other_result.safe_to_remove
            combined_broken += other_result.broken_events

        return BlastRadiusResult(
            candidate=candidate,
            events_checked=combined_checked,
            verdicts=primary_result.verdicts,
            validator_agreement=combined_agreement,
            safe_to_remove=combined_safe,
            broken_events=combined_broken,
        )

    def _sandbox_replay(self, run: ReviewRun, candidate, all_stmts, events) -> list[dict]:
        # Once TrueForge has failed once in this run (e.g. the agent isn't
        # registered yet, or no sandbox provider is configured), stop retrying
        # it for every subsequent candidate — that turns an O(1) failure into
        # an O(candidates) one, adding several seconds per candidate for no
        # benefit. A fresh Orchestrator is built per API request (see
        # server/main.py), so this never suppresses a retry across requests.
        if self.trueforge is not None and not self._trueforge_broken:
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
                self._trueforge_broken = True
                run.log(
                    "TrueForge sandbox unavailable",
                    f"{e} — replaying locally instead for the rest of this review.",
                    kind="warn",
                )
        return run_local_replay(candidate, all_stmts, events)

    def _validate(self, run: ReviewRun, candidate, hypothetical, events, local_verdicts) -> BlastRadiusResult:
        simulator = self.simulator
        # A candidate with zero matching historical events never actually calls
        # the AWS API (nothing to simulate_batch) — its trivial success must not
        # be allowed to overwrite an earlier candidate's real fallback flag with
        # a claim that real AWS validated this run, when it didn't for at least
        # one candidate. Once "reference (demo mode)" is set, it stays set.
        would_call_real_aws = bool(local_verdicts) and simulator is not None
        if simulator is not None:
            try:
                result = validate_candidate(candidate, hypothetical, events, local_verdicts, simulator)
                if would_call_real_aws and run.validator_source != "reference (demo mode)":
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
                events = self._get_events_cached(run, role, understood.lookback_days)
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

    # ---------------- standalone check (read-only, no ReviewRun needed) ----------------

    def check_permission(self, role_name: str, action: str, lookback_days: int = 90) -> dict:
        """
        Answer "what would removing this ONE permission do?" directly,
        without running a full review or requiring approval — this never
        writes anything, so there is nothing to gate. Reuses the exact same
        replay + independent-validation + shared-policy logic as a full
        review. Useful for a quick sanity check before deciding whether to
        even run a full account sweep, or for spot-checking a permission a
        human is already suspicious of.
        """
        if self.iam is None:
            raise IamUnavailable("AWS IAM is not configured.")

        scratch = ReviewRun(id="scratch", request_text=f"check {action} on {role_name}")
        role = self.iam.get_role(role_name)
        self._role_cache[role.name] = role
        events = self._get_events_cached(scratch, role, lookback_days)

        all_stmts = _all_statements(role)
        source_policy = next((p for p in role.policies for s in p.statements if action in s.actions), None)
        if source_policy is None:
            return {
                "role_name": role_name,
                "action": action,
                "granted": False,
                "message": f"'{action}' is not granted to '{role_name}' by any literal statement (it may only be reachable via a wildcard grant, which this tool never proposes removing).",
            }

        from blast_radius.model import CandidatePermission
        from blast_radius.risk import severity_for_action

        last_used = max((e.event_time for e in events if e.action == action), default=None)
        candidate = CandidatePermission(
            role_name=role_name,
            action=action,
            source_policy=source_policy,
            last_accessed=last_used,
            reason="explicit check" if last_used else "explicit check — no historical use found",
            severity=severity_for_action(action),
        )
        hypothetical = remove_action(all_stmts, action)
        local_verdicts = self._sandbox_replay(scratch, candidate, all_stmts, events)
        result = self._validate(scratch, candidate, hypothetical, events, local_verdicts)
        result = self._extend_across_shared_attachments(
            scratch, candidate, result, UnderstoodRequest(role_name=role_name, role_prefix=None, lookback_days=lookback_days)
        )
        d = result.to_dict()
        d["granted"] = True
        d["validator_source"] = scratch.validator_source
        d["timeline"] = [e.to_dict() for e in scratch.timeline]
        return d

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
        # Group by policy, not by (role, policy): a managed policy shared
        # across roles must be rewritten exactly ONCE (its ARN identifies it
        # regardless of which role's review found the candidate) — calling
        # revoke_actions twice for the same managed policy would needlessly
        # burn one of IAM's 5 policy-version slots and could race with itself.
        # Inline policies are still keyed per (role, policy name), since each
        # role's inline policy is a distinct document.
        groups: dict[tuple, list[str]] = {}
        policy_refs: dict[tuple, AttachedPolicy] = {}
        affected_roles: dict[tuple, set[str]] = {}
        for r in safe:
            policy = r.candidate.source_policy
            key = ("managed", policy.arn) if policy.kind == "managed" else ("inline", r.candidate.role_name, policy.name)
            groups.setdefault(key, []).append(r.candidate.action)
            policy_refs[key] = policy
            affected_roles.setdefault(key, set()).add(r.candidate.role_name)
            for shared in r.candidate.shared_with_roles:
                affected_roles[key].add(shared)

        committed_roles: set[str] = set()
        try:
            for key, actions in groups.items():
                policy = policy_refs[key]
                # role_name is only meaningful for inline policies (see
                # AwsIamClient.revoke_actions — the managed-policy branch keys
                # entirely off policy_arn); pass any one affected role for the
                # inline case, since exactly one owns that inline policy.
                any_role = next(iter(affected_roles[key]))
                self.iam.revoke_actions(
                    role_name=any_role,
                    policy_name=policy.name,
                    policy_kind=policy.kind,
                    policy_arn=policy.arn,
                    actions_to_remove=list(dict.fromkeys(actions)),  # dedupe, keep order
                )
                committed_roles |= affected_roles[key]
                run.log(
                    f"Updated policy '{policy.name}'"
                    + (f" (shared by {len(affected_roles[key])} roles)" if len(affected_roles[key]) > 1 else f" on role {any_role}"),
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
        self._verify(run, committed_roles, groups, affected_roles)

    def _verify(
        self, run: ReviewRun, committed_roles: set[str], groups: dict[tuple, list[str]], affected_roles: dict[tuple, set[str]]
    ) -> None:
        mismatches = []
        for key, actions in groups.items():
            for role_name in affected_roles[key]:
                fresh = self.iam.get_role(role_name)
                all_current_actions = {a for p in fresh.policies for s in p.statements for a in s.actions}
                for action in actions:
                    if action in all_current_actions:
                        mismatches.append({"role": role_name, "action": action, "issue": "still present after revoke"})

        run.verify_result = {
            "roles_updated": len(committed_roles),
            "permissions_removed": sum(len(set(a)) for a in groups.values()),
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
