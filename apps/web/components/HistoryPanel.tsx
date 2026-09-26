"use client";

import { useEffect, useState } from "react";
import { listReviews } from "@/lib/api";
import { ReviewSummary } from "@/lib/types";

const STATUS_STYLES: Record<string, string> = {
  verified: "text-emerald-700",
  awaiting_approval: "text-amber-700",
  rejected: "text-gray-500",
  failed: "text-accent",
  no_candidates: "text-gray-400",
};

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleString([], { dateStyle: "short", timeStyle: "short" });
}

export default function HistoryPanel({ refreshKey }: { refreshKey: number }) {
  const [runs, setRuns] = useState<ReviewSummary[] | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    listReviews()
      .then(setRuns)
      .catch(() => setRuns([]));
  }, [open, refreshKey]);

  return (
    <section className="rounded-md border border-gray-200 bg-white p-5">
      <button
        className="flex w-full items-center justify-between text-left"
        onClick={() => setOpen((o) => !o)}
      >
        <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-500">Review History</h2>
        <span className="text-xs text-gray-400">{open ? "hide" : "show"}</span>
      </button>
      {open && (
        <div className="mt-3">
          {runs === null ? (
            <p className="text-sm text-gray-400">Loading…</p>
          ) : runs.length === 0 ? (
            <p className="text-sm text-gray-400">No past reviews yet.</p>
          ) : (
            <div className="divide-y divide-gray-100">
              {runs.map((r) => (
                <div key={r.id} className="flex items-center justify-between py-2 text-sm">
                  <div>
                    <div className="font-medium text-gray-800">{r.role_name ?? "all roles"}</div>
                    <div className="text-xs text-gray-400">{formatTime(r.updated_at)}</div>
                  </div>
                  <div className="text-right">
                    <div className={`font-medium ${STATUS_STYLES[r.status] ?? "text-gray-600"}`}>{r.status.replace(/_/g, " ")}</div>
                    <div className="text-xs text-gray-400">
                      {r.safe_count} safe · {r.unsafe_count} flagged
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
