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
import Spinner from "@/components/ui/Spinner";
import { approveReview, getReview, rejectReview } from "@/lib/api";
import { ReviewRun } from "@/lib/types";

export default function ReviewDetailPage() {
  const params = useParams<{ id: string }>();
  const [run, setRun] = useState<ReviewRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    getReview(params.id)
      .then(setRun)
      .catch((e) => setLoadError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [params.id]);

  const handleApprove = async () => {
    if (!run) return;
    setBusy(true);
    setActionError(null);
    try {
      setRun(await approveReview(run.id));
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const handleReject = async () => {
    if (!run) return;
    setBusy(true);
    setActionError(null);
    try {
      setRun(await rejectReview(run.id));
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 p-8 text-sm text-slate-400">
        <Spinner className="h-4 w-4" />
        Loading review…
      </div>
    );
  }

  if (loadError || !run) {
    return (
      <div className="p-8">
        <p className="text-sm text-accent">{loadError ?? "Review not found."}</p>
        <Link href="/" className="mt-2 inline-block text-sm text-brand-600 underline">
          Start a new review
        </Link>
      </div>
    );
  }

  return (
    <main className="flex flex-col gap-5 pb-10">
      <ProjectHeader roleName={run.understood?.role_name} validatorSource={run.validator_source} />

      <div className="grid grid-cols-1 gap-5 px-8 md:grid-cols-[320px_1fr]">
        <div className="h-[420px] md:h-auto">
          <AgentTimeline events={run.timeline} />
        </div>
        <div className="flex flex-col gap-5">
          {run.understood && <ConstraintPanel understood={run.understood} />}
          {run.total_candidates > 0 && (
            <ValidationPanel
              totalCandidates={run.total_candidates}
              safeCount={run.safe_changes.length}
              unsafeCount={run.unsafe_candidates.length}
              validatorSource={run.validator_source}
              sandboxUsed={run.sandbox_used}
            />
          )}
        </div>
      </div>

      <div className="flex flex-col gap-5 px-8">
        {(run.safe_changes.length > 0 || run.unsafe_candidates.length > 0) && (
          <ScheduleDiff safe={run.safe_changes} unsafe={run.unsafe_candidates} />
        )}
        {actionError && <p className="text-sm text-accent">{actionError}</p>}
        <ApprovalPanel run={run} onApprove={handleApprove} onReject={handleReject} busy={busy} />
      </div>
    </main>
  );
}
