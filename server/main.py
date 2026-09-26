"""
Blast Radius API server (FastAPI). Thin HTTP layer over agent/orchestrator.py.

Endpoints (consumed by apps/web's Next.js API routes):
  POST /api/review              {"request": "<natural language request>"}  -> ReviewRun
  GET  /api/review/{id}         -> ReviewRun (poll this for the agent timeline)
  POST /api/review/{id}/approve -> triggers commit_and_verify() (the only write path)
  POST /api/review/{id}/reject  -> marks the run rejected; no AWS IAM write

Run: `uvicorn main:app --reload --port 8010` from the server/ directory.
"""
from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent.orchestrator import Orchestrator, ReviewRun
from agent.trueforge_client import TrueForgeClient
from aws_integration.client import AwsIamClient
from aws_integration.cloudtrail import CloudTrailSource, DemoCloudTrailSource
from aws_integration.simulate import AwsPolicySimulator

load_dotenv()

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


@app.post("/api/review")
def create_review(body: ReviewRequest):
    orchestrator = _build_orchestrator()
    run = orchestrator.run(body.request)
    _RUNS[run.id] = run
    return run.to_dict()


@app.get("/api/review/{run_id}")
def get_review(run_id: str):
    run = _RUNS.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Unknown review id")
    return run.to_dict()


@app.post("/api/review/{run_id}/approve")
def approve_review(run_id: str):
    run = _RUNS.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Unknown review id")
    orchestrator = _build_orchestrator()
    try:
        orchestrator.commit_and_verify(run)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
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
    return run.to_dict()


@app.get("/api/health")
def health():
    return {"status": "ok"}
