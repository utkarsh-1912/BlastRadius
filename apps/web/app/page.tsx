"use client";

import { useState } from "react";
import ProjectHeader from "@/components/ProjectHeader";
import ChatPanel from "@/components/ChatPanel";
import AgentTimeline from "@/components/AgentTimeline";
import ScheduleDiff from "@/components/ScheduleDiff";
import ConstraintPanel from "@/components/ConstraintPanel";
import ValidationPanel from "@/components/ValidationPanel";
import ApprovalPanel from "@/components/ApprovalPanel";
import { approveReview, createReview, rejectReview } from "@/lib/api";
import { ReviewRun } from "@/lib/types";

const DEMO_REQUEST = "Review IAM access for the data-pipeline-role role over the last 90 days.";

export default function Home() {
  const [run, setRun] = useState<ReviewRun | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);

  const handleSubmit = async (text: string) => {
    setLoading(true);
    setRun(null);
    try {
      setRun(await createReview(text));
    } finally {
      setLoading(false);
    }
  };

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

  return (
    <main className="mx-auto flex min-h-screen max-w-6xl flex-col">
      <ProjectHeader roleName={run?.understood?.role_name} validatorSource={run?.validator_source} />
      <ChatPanel onSubmit={handleSubmit} disabled={loading} defaultValue={DEMO_REQUEST} />

      {run && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-[320px_1fr]">
            <AgentTimeline events={run.timeline} />
            <div className="bg-gray-50 p-6">
              {run.understood && <ConstraintPanel understood={run.understood} />}
            </div>
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
        </>
      )}
    </main>
  );
}
