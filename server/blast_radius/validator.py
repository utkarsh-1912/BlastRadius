"""
VALIDATE: the independent check. Takes the sandbox's local-evaluator
verdicts for one candidate permission, gets the AWS-authoritative verdicts
for the same events from AwsPolicySimulator (host-side, read-only
credentials, real `iam:SimulateCustomPolicy` calls), and merges them.

A permission is only ever reported "safe to remove" when:
  1. every single historical event that used it still evaluates to "allow"
     under the hypothetical policy (no blast radius), AND
  2. the local evaluator and the real AWS evaluator agree on every one of
     those events (no validator disagreement).

This module must not import anything from blast_radius/sandbox_code.py or
otherwise reuse the sandbox's own reasoning — it re-derives its own AWS
verdicts independently, exactly as scheduler/validator.py in BuildPlan never
imported solver.py's CP-SAT model.
"""
from __future__ import annotations

from blast_radius.local_evaluator import SimpleStatement
from blast_radius.model import BlastRadiusResult, CandidatePermission, EventVerdict, HistoricalEvent
from aws_integration.simulate import AwsPolicySimulator


def validate_candidate(
    candidate: CandidatePermission,
    hypothetical_statements: list[SimpleStatement],
    events: list[HistoricalEvent],
    local_verdicts: list[dict],  # from simulator.run_local_replay / sandbox output
    simulator: AwsPolicySimulator,
) -> BlastRadiusResult:
    relevant_indices = [v["event_index"] for v in local_verdicts]
    aws_verdicts = simulator.simulate_batch(hypothetical_statements, events, relevant_indices) if relevant_indices else {}

    verdicts: list[EventVerdict] = []
    for v in local_verdicts:
        idx = v["event_index"]
        local = v["local_verdict"]
        aws = aws_verdicts.get(idx, "deny")  # fail closed if AWS didn't return a verdict
        verdicts.append(
            EventVerdict(event=events[idx], local_verdict=local, aws_verdict=aws, agree=(local == aws))
        )

    validator_agreement = all(v.agree for v in verdicts)
    broken = [v for v in verdicts if v.would_break]
    safe = validator_agreement and not broken

    return BlastRadiusResult(
        candidate=candidate,
        events_checked=len(verdicts),
        verdicts=verdicts,
        validator_agreement=validator_agreement,
        safe_to_remove=safe,
        broken_events=broken,
    )
