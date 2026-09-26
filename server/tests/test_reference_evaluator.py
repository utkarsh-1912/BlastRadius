"""The reference evaluator (demo-mode stand-in for real AWS) must agree with
the sandbox's local evaluator on ordinary cases, despite being written with
a different algorithm — otherwise every demo-mode simulation would report
'disagreement' and nothing would ever be called safe."""
from __future__ import annotations

from blast_radius import local_evaluator, reference_evaluator
from blast_radius.local_evaluator import SimpleStatement


def _stmt(effect="Allow", actions=None, resources=None, has_condition=False):
    return SimpleStatement(effect=effect, actions=actions or [], not_actions=[], resources=resources or ["*"], not_resources=[], has_condition=has_condition)


CASES = [
    ([_stmt(actions=["s3:GetObject"])], "s3:GetObject", ["arn:aws:s3:::b/k"], "allow"),
    ([], "s3:GetObject", ["arn:aws:s3:::b/k"], "deny"),
    ([_stmt(effect="Allow", actions=["s3:GetObject"]), _stmt(effect="Deny", actions=["s3:GetObject"])], "s3:GetObject", ["arn:aws:s3:::b/k"], "deny"),
    ([_stmt(actions=["s3:*"])], "s3:GetObject", ["arn:aws:s3:::b/k"], "allow"),
    ([_stmt(actions=["s3:GetObject"], resources=["arn:aws:s3:::my-bucket/*"])], "s3:GetObject", ["arn:aws:s3:::other/k"], "deny"),
    ([_stmt(actions=["s3:GetObject"], has_condition=True)], "s3:GetObject", ["arn:aws:s3:::b/k"], "deny"),
]


def test_reference_and_local_evaluators_agree_on_all_cases():
    for statements, action, resources, expected in CASES:
        local = local_evaluator.evaluate(statements, action, resources)
        ref = reference_evaluator.evaluate(statements, action, resources)
        assert local == expected, f"local evaluator diverged from expectation for {action}"
        assert ref == expected, f"reference evaluator diverged from expectation for {action}"
        assert local == ref
