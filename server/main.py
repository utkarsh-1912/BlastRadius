"""
Blast Radius API server (FastAPI). Thin HTTP layer over agent/orchestrator.py.

Endpoints (consumed by apps/web's Next.js API routes):
  POST /api/review              {"request": "<natural language request>"}  -> ReviewRun
  GET  /api/review/{id}         -> ReviewRun (poll this for the agent timeline; falls
                                   back to the persisted history store if the process
                                   restarted and it's no longer live in memory)
  POST /api/review/{id}/approve -> triggers commit_and_verify() (the only write path)
  POST /api/review/{id}/reject  -> marks the run rejected; no AWS IAM write
  GET  /api/reviews             -> list of past reviews (audit history)
  POST /api/check                {"role_name", "action", "lookback_days"?} -> a
                                   standalone, read-only blast-radius check for one
                                   permission, with no review/approval workflow
  GET  /api/roles                real IAM role names (?prefix=), for the /check page's
                                   role autocomplete
  GET  /api/roles/{role}/actions  that role's real granted literal actions, for the
                                   /check page's action autocomplete

Run: `uvicorn main:app --reload --port 8010` from the server/ directory.
"""
from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent import store
from agent.orchestrator import Orchestrator, ReviewRun
from agent.trueforge_client import TrueForgeClient
from aws_integration.client import AwsIamClient, IamError, IamNotFound
from aws_integration.cloudtrail import CloudTrailSource, DemoCloudTrailSource
from aws_integration.simulate import AwsPolicySimulator

load_dotenv()
from env_utils import clean_blank_env  # noqa: E402

clean_blank_env(["IAM_MCP_TOKEN", "TRUEFORGE_BASE_URL", "DAYTONA_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"])

app = FastAPI(title="Blast Radius API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # hackathon demo; tighten before any real deployment
    allow_methods=["*"],
    allow_headers=["*"],
)

_RUNS: dict[str, ReviewRun] = {}


def _load_demo_events() -> dict:
    import json

    path = os.path.join(os.path.dirname(__file__), "data", "demo_cloudtrail_events.json")
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _build_orchestrator() -> Orchestrator:
    region = os.environ.get("AWS_REGION", "us-east-1")
    profile = os.environ.get("AWS_PROFILE")
    endpoint_url = os.environ.get("AWS_ENDPOINT_URL")  # point at moto_server for a persistent local demo

    iam = None
    if os.environ.get("AWS_ACCESS_KEY_ID") or profile or endpoint_url:
        iam = AwsIamClient(region=region, profile=profile, endpoint_url=endpoint_url)

    use_demo_events = os.environ.get("USE_DEMO_CLOUDTRAIL", "true").lower() == "true"
    cloudtrail = DemoCloudTrailSource(_load_demo_events()) if use_demo_events else CloudTrailSource(region=region, profile=profile)

    simulator = AwsPolicySimulator(region=region, profile=profile, endpoint_url=endpoint_url) if iam else None

    tf_url = os.environ.get("TRUEFORGE_BASE_URL")
    tf_client = TrueForgeClient(base_url=tf_url) if tf_url else None
    if tf_client is not None and not tf_client.reachable():
        tf_client = None

    return Orchestrator(iam=iam, cloudtrail=cloudtrail, simulator=simulator, trueforge=tf_client)


class ReviewRequest(BaseModel):
    request: str


class CheckRequest(BaseModel):
    role_name: str
    action: str
    lookback_days: int = 90


@app.post("/api/review")
def create_review(body: ReviewRequest):
    orchestrator = _build_orchestrator()
    run = orchestrator.run(body.request)
    _RUNS[run.id] = run
    store.save_run(run.to_dict())
    return run.to_dict()


@app.get("/api/review/{run_id}")
def get_review(run_id: str):
    run = _RUNS.get(run_id)
    if run is not None:
        return run.to_dict()
    persisted = store.get_run(run_id)
    if persisted is not None:
        return persisted
    raise HTTPException(status_code=404, detail="Unknown review id")


@app.post("/api/review/{run_id}/approve")
def approve_review(run_id: str):
    run = _RUNS.get(run_id)
    if run is None:
        if store.get_run(run_id) is not None:
            raise HTTPException(
                status_code=409,
                detail="This review is no longer live (the server restarted since it ran). Run a fresh review to approve changes against current IAM/CloudTrail state.",
            )
        raise HTTPException(status_code=404, detail="Unknown review id")
    orchestrator = _build_orchestrator()
    try:
        orchestrator.commit_and_verify(run)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    store.save_run(run.to_dict())
    return run.to_dict()


@app.post("/api/review/{run_id}/reject")
def reject_review(run_id: str):
    run = _RUNS.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Unknown review id")
    orchestrator = _build_orchestrator()
    try:
        orchestrator.reject(run)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    store.save_run(run.to_dict())
    return run.to_dict()


@app.get("/api/reviews")
def list_reviews(limit: int = 50):
    """Audit history: past reviews, most recently updated first."""
    return store.list_runs(limit=limit)


@app.get("/api/roles")
def list_roles_endpoint(prefix: Optional[str] = None):
    """Real IAM role names, for the /check page's autocomplete — never a
    made-up list; if AWS isn't configured this fails loudly (502) rather
    than silently returning nothing."""
    orchestrator = _build_orchestrator()
    if orchestrator.iam is None:
        raise HTTPException(status_code=502, detail="AWS IAM is not configured.")
    try:
        raw = orchestrator.iam.list_roles(name_prefix=prefix)
    except IamError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return [{"role_name": r["RoleName"], "arn": r["Arn"]} for r in raw]


@app.get("/api/roles/{role_name}/actions")
def list_role_actions(role_name: str):
    """The role's real granted literal actions (no wildcards), for the
    /check page's action autocomplete — so a spot-check is against an
    action the role actually has, not a guess."""
    orchestrator = _build_orchestrator()
    if orchestrator.iam is None:
        raise HTTPException(status_code=502, detail="AWS IAM is not configured.")
    try:
        role = orchestrator.iam.get_role(role_name)
    except IamNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except IamError as e:
        raise HTTPException(status_code=502, detail=str(e))
    actions = sorted(
        {a for p in role.policies for s in p.statements if s.effect == "Allow" for a in s.actions if "*" not in a and "?" not in a}
    )
    return actions


@app.post("/api/check")
def check_permission(body: CheckRequest):
    """Standalone, read-only blast-radius check for one permission — no
    review workflow, no approval gate, because nothing is ever written."""
    orchestrator = _build_orchestrator()
    try:
        return orchestrator.check_permission(body.role_name, body.action, body.lookback_days)
    except IamError as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/health")
def health():
    return {"status": "ok"}
