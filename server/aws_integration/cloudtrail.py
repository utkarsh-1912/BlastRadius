"""
Wraps CloudTrail's LookupEvents API and normalizes events into the
(IAM-action, resource ARNs) shape Blast Radius needs.

CloudTrail event names don't carry the IAM-style "service:Action" prefix
(e.g. "GetObject", not "s3:GetObject") — `event_source` ("s3.amazonaws.com")
supplies the service prefix, and we derive the IAM action name from it. This
mapping is exact for the overwhelming majority of AWS services (the service
prefix used in IAM policies matches the event source's first DNS label) —
edge cases documented inline.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from blast_radius.model import HistoricalEvent


def _iam_action_from_event(event_source: str, event_name: str) -> str:
    # "s3.amazonaws.com" -> "s3"; "monitoring.amazonaws.com" (CloudWatch) is a
    # known exception where the IAM prefix ("cloudwatch") differs from the
    # event source's first label — mapped explicitly below.
    prefix = event_source.split(".")[0]
    overrides = {"monitoring": "cloudwatch", "email": "ses", "logs": "logs"}
    prefix = overrides.get(prefix, prefix)
    return f"{prefix}:{event_name}"


@dataclass
class CloudTrailSource:
    region: str = "us-east-1"
    profile: Optional[str] = None

    def __post_init__(self):
        session = boto3.Session(profile_name=self.profile) if self.profile else boto3.Session()
        self._ct = session.client("cloudtrail", region_name=self.region)

    def lookup_events_for_principal(self, principal_arn: str, lookback_days: int, max_events: int = 5000) -> list[HistoricalEvent]:
        start_time = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        events: list[HistoricalEvent] = []
        try:
            paginator = self._ct.get_paginator("lookup_events")
            for page in paginator.paginate(
                LookupAttributes=[{"AttributeKey": "Username", "AttributeValue": principal_arn.split("/")[-1]}],
                StartTime=start_time,
            ):
                for raw in page["Events"]:
                    ct_event = raw.get("CloudTrailEvent")
                    import json as _json

                    detail = _json.loads(ct_event) if ct_event else {}
                    action = _iam_action_from_event(detail.get("eventSource", ""), raw.get("EventName", ""))
                    resources = [r.get("resourceName", "") for r in raw.get("Resources", []) if r.get("resourceName")]
                    events.append(
                        HistoricalEvent(
                            event_time=raw["EventTime"] if isinstance(raw["EventTime"], datetime) else datetime.fromisoformat(raw["EventTime"]),
                            action=action,
                            resource_arns=resources,
                            source_ip=detail.get("sourceIPAddress", ""),
                            event_id=raw.get("EventId", ""),
                        )
                    )
                    if len(events) >= max_events:
                        return events
        except ClientError as e:
            raise RuntimeError(f"CloudTrail lookup failed: {e}") from e
        return events


class DemoCloudTrailSource:
    """
    Fallback source for accounts too new to have rich CloudTrail history (or
    for offline development): reads a pre-exported event log instead of
    calling CloudTrail live. This is exactly the shape a real audit would
    use with a CloudTrail Lake export or an Athena query result — clearly
    labeled as a fallback in the agent timeline, never presented as live.
    """

    def __init__(self, events_by_role: dict[str, list[dict]]):
        self._events_by_role = events_by_role

    def lookup_events_for_principal(self, principal_arn: str, lookback_days: int, max_events: int = 5000) -> list[HistoricalEvent]:
        role_name = principal_arn.split("/")[-1]
        raw = self._events_by_role.get(role_name, [])
        return [
            HistoricalEvent(
                event_time=datetime.fromisoformat(e["event_time"]),
                action=e["action"],
                resource_arns=e.get("resource_arns", []),
                source_ip=e.get("source_ip", ""),
                event_id=e.get("event_id", ""),
            )
            for e in raw
        ][:max_events]
