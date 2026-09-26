"use client";

import { ReviewRun } from "@/lib/types";

interface Props {
  run: ReviewRun;
  onApprove: () => void;
  onReject: () => void;
  busy: boolean;
}

export default function ApprovalPanel({ run, onApprove, onReject, busy }: Props) {
  if (run.status === "awaiting_approval") {
    return (
      <section className="border-t border-gray-200 bg-white px-6 py-5">
        <p className="mb-4 text-sm text-gray-700">
          Blast radius analysis complete. <strong>{run.safe_changes.length}</strong> permission(s) proven safe to
          remove; <strong>{run.unsafe_candidates.length}</strong> flagged and excluded.
          <br />
          Nothing has been changed in AWS IAM yet. Approve the safe removals?
        </p>
        <div className="flex gap-3">
          <button
            className="rounded-md border border-gray-300 px-5 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-50 disabled:opacity-40"
            onClick={onReject}
            disabled={busy}
          >
            Reject
          </button>
          <button
            className="rounded-md bg-accent px-5 py-2 text-sm font-medium text-white transition hover:bg-accent-dark disabled:opacity-40"
            onClick={onApprove}
            disabled={busy || run.safe_changes.length === 0}
          >
            Approve &amp; Revoke in AWS IAM
          </button>
        </div>
      </section>
    );
  }

  if (run.status === "rejected") {
    return (
      <section className="border-t border-gray-200 bg-white px-6 py-5 text-sm text-gray-600">
        No changes were made to AWS IAM.
      </section>
    );
  }

  if (run.status === "no_candidates") {
    return (
      <section className="border-t border-gray-200 bg-white px-6 py-5 text-sm text-gray-600">
        No unused permissions found for this role. Nothing to propose.
      </section>
    );
  }

  if (run.status === "verified" && run.verify_result) {
    return (
      <section className="border-t border-gray-200 bg-white px-6 py-5 text-sm">
        <div className="space-y-1 text-emerald-700">
          <div>✓ {run.verify_result.roles_updated} role(s) updated</div>
          <div>✓ AWS IAM re-read</div>
          <div>✓ {run.verify_result.permissions_removed} permission(s) confirmed removed</div>
          <div>✓ Verification passed</div>
        </div>
      </section>
    );
  }

  if (run.status === "failed") {
    return <section className="border-t border-gray-200 bg-white px-6 py-5 text-sm text-accent">{run.error}</section>;
  }

  return null;
}
