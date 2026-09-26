#!/usr/bin/env python
"""
Idempotent registration of everything the Blast Radius agent needs in
TrueForge: model provider, sandbox provider, the blast-radius-aws-iam MCP
server, and the `blast-radius` agent itself. Mirrors the reference
`dress-rehearsal` hackathon project's `npm run setup` (scripts/setup.ts),
translated to Python since this project's runtime is Python-first.

Safe to re-run: every step is create-or-replace.

Usage:
    python scripts/setup_trueforge.py
"""
from __future__ import annotations

import json
import os
import re
import sys

from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))

from agent.trueforge_client import TrueForgeClient, TrueForgeError, TrueForgeUnavailable  # noqa: E402

load_dotenv()

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def ok(msg):
    print(f"✓ {msg}")


def warn(msg):
    print(f"! {msg}")


def fail(msg):
    print(f"✗ {msg}")


def env(name, default=None):
    v = os.environ.get(name, default)
    return v.strip() if isinstance(v, str) and v.strip() else (v if not isinstance(v, str) else None) or default


def resource_slug(raw: str) -> str:
    s = re.sub(r"-+", "-", re.sub(r"[^a-z0-9-]+", "-", raw.lower())).strip("-")
    if not re.match(r"^[a-z]", s):
        s = f"m-{s}"
    return s[:64].rstrip("-") or "model"


def main() -> int:
    base_url = os.environ.get("TRUEFORGE_BASE_URL", "http://localhost:8790")
    tf = TrueForgeClient(base_url=base_url)

    if not tf.reachable():
        fail(f"TrueForge unreachable at {base_url}")
        print("  Start it first: npx @truefoundry/trueforge@latest")
        return 1
    ok(f"TrueForge reachable at {base_url}")

    had_failure = False

    # ---------- 1. model provider ----------
    fqn = None
    if os.environ.get("ANTHROPIC_API_KEY"):
        model_id = os.environ.get("MODEL_ID", "claude-sonnet-5")
        slug = resource_slug(model_id)
        try:
            tf.put_model_provider(
                {
                    "type": "anthropic",
                    "auth": {"api_key": os.environ["ANTHROPIC_API_KEY"]},
                    "models": [{"name": slug, "model_id": model_id, "properties": {}}],
                }
            )
            fqn = f"anthropic/{slug}"
            ok(f"model provider: anthropic -> {fqn}")
        except (TrueForgeError, TrueForgeUnavailable) as e:
            fail(f"model provider: {e}")
            had_failure = True
    elif os.environ.get("OPENAI_API_KEY"):
        model_id = os.environ.get("MODEL_ID", "gpt-5.5")
        slug = resource_slug(model_id)
        try:
            tf.put_model_provider(
                {
                    "type": "openai",
                    "auth": {"api_key": os.environ["OPENAI_API_KEY"]},
                    "models": [{"name": slug, "model_id": model_id, "properties": {}}],
                }
            )
            fqn = f"openai/{slug}"
            ok(f"model provider: openai -> {fqn}")
        except (TrueForgeError, TrueForgeUnavailable) as e:
            fail(f"model provider: {e}")
            had_failure = True
    else:
        fqn = os.environ.get("MODEL_FQN")
        if fqn:
            warn(f"no model API key in .env; using existing MODEL_FQN={fqn}")
        else:
            fail("no ANTHROPIC_API_KEY / OPENAI_API_KEY / MODEL_FQN set")
            had_failure = True

    # ---------- 2. sandbox provider (Daytona) ----------
    daytona_key = os.environ.get("DAYTONA_API_KEY")
    if daytona_key:
        try:
            tf.put_sandbox_provider(
                {
                    "type": "daytona",
                    "auth": {"api_key": daytona_key},
                    "exec_timeout_ms": 120000,
                    "auto_stop_interval_in_minutes": 5,
                    "auto_archive_interval_in_minutes": 60,
                    "auto_delete_interval_in_minutes": int(os.environ.get("DAYTONA_AUTO_DELETE_MINUTES", "30")),
                }
            )
            ok("sandbox (Daytona) configured")
        except (TrueForgeError, TrueForgeUnavailable) as e:
            fail(f"sandbox (Daytona): {e}")
            had_failure = True
    else:
        warn("DAYTONA_API_KEY not set; assuming sandbox already configured in the TrueForge UI")

    # ---------- 3. blast-radius-aws-iam MCP (remote, header auth) ----------
    mcp_token = os.environ.get("IAM_MCP_TOKEN")
    mcp_port = os.environ.get("IAM_MCP_PORT", "8792")
    if mcp_token:
        try:
            tf.put_mcp_server(
                {
                    "type": "remote",
                    "name": "blast-radius-aws-iam",
                    "url": f"http://localhost:{mcp_port}/mcp",
                    "description": "Blast Radius's controlled AWS IAM tool layer (read + blast-radius replay + one gated write).",
                    "auth": {"type": "header", "headers": {"Authorization": f"Bearer {mcp_token}"}},
                }
            )
            ok(f"mcp: blast-radius-aws-iam registered at localhost:{mcp_port}")
        except (TrueForgeError, TrueForgeUnavailable) as e:
            fail(f"mcp: blast-radius-aws-iam: {e}")
            had_failure = True
    else:
        fail("IAM_MCP_TOKEN not set")
        had_failure = True

    # ---------- 4. agent ----------
    if fqn:
        agent_path = os.path.join(REPO_ROOT, "agent", "blast-radius.agent.json")
        with open(agent_path, "r", encoding="utf-8") as f:
            raw = f.read().replace("${MODEL_FQN}", fqn)
        spec = json.loads(raw)
        try:
            tf.create_or_update_agent(spec["name"], spec["description"], spec["manifest"])
            ok(f"agent: {spec['name']} registered (model {fqn})")
        except (TrueForgeError, TrueForgeUnavailable) as e:
            fail(f"agent: {e}")
            had_failure = True
    else:
        fail("agent: skipped (no model configured)")
        had_failure = True

    print()
    if had_failure:
        print("Some steps failed — fix the items above and re-run.")
        return 1
    print("Blast Radius is fully registered in TrueForge.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
