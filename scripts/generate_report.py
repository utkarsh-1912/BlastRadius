#!/usr/bin/env python
"""
Scans roles, runs a full Blast Radius review on each (the same deterministic
pipeline the app uses — no LLM involved), persists every run to the audit
history store (so they show up in the dashboard's /reviews page too), and
writes an aggregate Markdown report.

This is the "report generator" — and, run on a schedule (cron / Windows Task
Scheduler, see below), the "recurring review" roadmap item from the README,
implemented as a script rather than a long-running service: this project
deliberately doesn't run a background process, so scheduling is left to the
OS's own scheduler, which is simpler and more auditable than an in-app one.

Usage:
    python scripts/generate_report.py [--role-prefix PREFIX] [--output PATH] [--lookback-days N]

Examples:
    python scripts/generate_report.py
    python scripts/generate_report.py --role-prefix data-pipeline
    python scripts/generate_report.py --output reports/weekly.md

Nothing here ever writes to AWS IAM — this only ever calls orchestrator.run(),
never commit_and_verify(). A report is a read-only artifact; approving any of
its findings still requires a human, in the dashboard, exactly as usual.
"""
from __future__ import annotations

import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))

from dotenv import load_dotenv  # noqa: E402

from agent import store  # noqa: E402
from agent.orchestrator import Orchestrator  # noqa: E402
from aws_integration.client import AwsIamClient, IamError  # noqa: E402
from aws_integration.cloudtrail import CloudTrailSource, DemoCloudTrailSource  # noqa: E402
from aws_integration.simulate import AwsPolicySimulator  # noqa: E402
from env_utils import clean_blank_env  # noqa: E402

load_dotenv()
clean_blank_env()

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def ok(msg):
    print(f"✓ {msg}")


def warn(msg):
    print(f"! {msg}")


def fail(msg):
    print(f"✗ {msg}")


def _build_orchestrator() -> Orchestrator:
    region = os.environ.get("AWS_REGION", "us-east-1")
    profile = os.environ.get("AWS_PROFILE")
    endpoint_url = os.environ.get("AWS_ENDPOINT_URL")
    iam = AwsIamClient(region=region, profile=profile, endpoint_url=endpoint_url)

    use_demo = os.environ.get("USE_DEMO_CLOUDTRAIL", "true").lower() == "true"
    if use_demo:
        import json

        demo_path = os.path.join(REPO_ROOT, "server", "data", "demo_cloudtrail_events.json")
        with open(demo_path, "r", encoding="utf-8") as f:
            events = json.load(f)
        cloudtrail = DemoCloudTrailSource(events)
    else:
        cloudtrail = CloudTrailSource(region=region, profile=profile)

    simulator = AwsPolicySimulator(region=region, profile=profile, endpoint_url=endpoint_url)
    return Orchestrator(iam=iam, cloudtrail=cloudtrail, simulator=simulator, trueforge=None)


def _render_markdown(generated_at: str, role_prefix: str | None, results: list[dict]) -> str:
    lines = [
        "# Blast Radius Report",
        "",
        f"Generated: {generated_at}",
        f"Scope: {'all roles' if not role_prefix else f'roles matching `{role_prefix}*`'}",
        "",
        "Read-only. Nothing in this report has been applied to AWS IAM — every finding still requires "
        "a human to approve it in the dashboard before anything changes.",
        "",
        "| Role | Status | Safe to remove | Flagged | Validator |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['role_name']} | {r['status']} | {r['safe_count']} | {r['flagged_count']} | {r['validator_source'] or 'n/a'} |"
        )

    total_safe = sum(r["safe_count"] for r in results)
    total_flagged = sum(r["flagged_count"] for r in results)
    lines += ["", f"**Totals:** {len(results)} role(s) reviewed, {total_safe} permission(s) provably safe to remove, {total_flagged} flagged and excluded.", ""]

    for r in results:
        if not r["safe_actions"] and not r["flagged_actions"]:
            continue
        lines.append(f"## {r['role_name']}")
        lines.append("")
        if r["safe_actions"]:
            lines.append("**Safe to remove** (proven by replay, both evaluators agree):")
            for a in r["safe_actions"]:
                lines.append(f"- `{a['action']}` &mdash; {a['severity']} &mdash; {a['reason']}")
            lines.append("")
        if r["flagged_actions"]:
            lines.append("**Flagged, excluded** (real historical evidence, not auto-proposed):")
            for a in r["flagged_actions"]:
                lines.append(f"- `{a['action']}` &mdash; {a['severity']} &mdash; {a['reason']}")
            lines.append("")
        lines.append(f"[Full detail in the dashboard &rarr; /reviews/{r['run_id']}]")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role-prefix", default=None, help="Only review roles whose name starts with this prefix")
    parser.add_argument("--output", default=None, help="Markdown report path (default: reports/report-<timestamp>.md)")
    parser.add_argument("--lookback-days", type=int, default=90)
    args = parser.parse_args()

    orch = _build_orchestrator()
    try:
        roles = orch.iam.list_roles(name_prefix=args.role_prefix)
    except IamError as e:
        fail(f"Could not list roles: {e}")
        return 1

    if not roles:
        warn("No roles matched — nothing to report.")
        return 0
    ok(f"Reviewing {len(roles)} role(s)" + (f" matching '{args.role_prefix}'" if args.role_prefix else ""))

    results = []
    for raw_role in roles:
        role_name = raw_role["RoleName"]
        request = f"Review IAM access for the {role_name} role over the last {args.lookback_days} days."
        run = orch.run(request)
        store.save_run(run.to_dict())

        safe = [{"action": c.candidate.action, "severity": c.candidate.severity, "reason": c.candidate.reason} for c in run.results if c.safe_to_remove]
        flagged = [{"action": c.candidate.action, "severity": c.candidate.severity, "reason": c.candidate.reason} for c in run.results if not c.safe_to_remove]

        results.append(
            {
                "role_name": role_name,
                "run_id": run.id,
                "status": run.status,
                "safe_count": len(safe),
                "flagged_count": len(flagged),
                "safe_actions": safe,
                "flagged_actions": flagged,
                "validator_source": run.validator_source,
            }
        )
        mark = "✓" if run.status != "failed" else "✗"
        print(f"  {mark} {role_name}: {len(safe)} safe, {len(flagged)} flagged (status={run.status})")

    generated_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    report_md = _render_markdown(generated_at, args.role_prefix, results)

    output_path = args.output or os.path.join(REPO_ROOT, "reports", f"report-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}.md")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_md)

    print()
    ok(f"Report written to {output_path}")
    ok(f"{len(results)} run(s) saved to audit history — visible in the dashboard's /reviews page")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
