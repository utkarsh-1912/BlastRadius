"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import ProjectHeader from "@/components/ProjectHeader";
import AgentTimeline from "@/components/AgentTimeline";
import ConstraintPanel from "@/components/ConstraintPanel";
import ScheduleDiff from "@/components/ScheduleDiff";
import ValidationPanel from "@/components/ValidationPanel";
import ApprovalPanel from "@/components/ApprovalPanel";
import { approveReview, getReview, rejectReview } from "@/lib/api";
import { ReviewRun } from "@/lib/types";

export default function ReviewDetailPage() {
  const params = useParams<{ id: string }>();
  const [run, setRun] = useState<ReviewRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getReview(params.id)
      .then(setRun)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [params.id]);

  const handleApprove = async () => {
    if (!run) return;
    setBusy(true);
    try {
      setRun(await approveReview(run.id));
    } finally {
      setBusy(false);
    }
  };

  const handleReject = async () => {
    if (!run) return;
    setBusy(true);
    try {
      setRun(await rejectReview(run.id));
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return <p className="p-6 text-sm text-gray-400">Loading review…</p>;
  }

  if (error || !run) {
    return (
      <div className="p-6">
        <p className="text-sm text-accent">{error ?? "Review not found."}</p>
        <Link href="/" className="mt-2 inline-block text-sm text-gray-600 underline">
          Start a new review
        </Link>
      </div>
    );
  }

  return (
    <main className="flex flex-col">
      <ProjectHeader roleName={run.understood?.role_name} validatorSource={run.validator_source} />

      <div className="grid grid-cols-1 md:grid-cols-[320px_1fr]">
        <AgentTimeline events={run.timeline} />
        <div className="bg-gray-50 p-6">{run.understood && <ConstraintPanel understood={run.understood} />}</div>
      </div>

      {(run.safe_changes.length > 0 || run.unsafe_candidates.length > 0) && (
        <ScheduleDiff safe={run.safe_changes} unsafe={run.unsafe_candidates} />
      )}
      {run.total_candidates > 0 && (
        <ValidationPanel
          totalCandidates={run.total_candidates}
          safeCount={run.safe_changes.length}
          unsafeCount={run.unsafe_candidates.length}
          validatorSource={run.validator_source}
          sandboxUsed={run.sandbox_used}
        />
      )}
      <ApprovalPanel run={run} onApprove={handleApprove} onReject={handleReject} busy={busy} />
    </main>
  );
}
