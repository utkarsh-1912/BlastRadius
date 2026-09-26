"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
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
  return new Date(ts * 1000).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

export default function ReviewsHistoryPage() {
  const [runs, setRuns] = useState<ReviewSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listReviews()
      .then(setRuns)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  return (
    <main className="flex flex-col px-6 py-8">
      <h1 className="text-xl font-semibold text-gray-900">Review History</h1>
      <p className="mt-1 text-sm text-gray-500">Every past review, audited — including ones no longer live in memory.</p>

      <div className="mt-6 overflow-hidden rounded-md border border-gray-200 bg-white">
        {error && <p className="p-5 text-sm text-accent">{error}</p>}
        {!error && runs === null && <p className="p-5 text-sm text-gray-400">Loading…</p>}
        {!error && runs !== null && runs.length === 0 && (
          <p className="p-5 text-sm text-gray-400">
            No reviews yet.{" "}
            <Link href="/" className="underline">
              Start one
            </Link>
            .
          </p>
        )}
        {!error && runs !== null && runs.length > 0 && (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-5 py-2 text-left">Role</th>
                <th className="px-5 py-2 text-left">Request</th>
                <th className="px-5 py-2 text-left">Status</th>
                <th className="px-5 py-2 text-left">Results</th>
                <th className="px-5 py-2 text-left">Updated</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {runs.map((r) => (
                <tr key={r.id} className="hover:bg-gray-50">
                  <td className="px-5 py-3">
                    <Link href={`/reviews/${r.id}`} className="font-medium text-gray-800 hover:underline">
                      {r.role_name ?? "all roles"}
                    </Link>
                  </td>
                  <td className="max-w-xs truncate px-5 py-3 text-gray-500">{r.request_text}</td>
                  <td className={`px-5 py-3 font-medium ${STATUS_STYLES[r.status] ?? "text-gray-600"}`}>
                    {r.status.replace(/_/g, " ")}
                  </td>
                  <td className="px-5 py-3 text-gray-500">
                    {r.safe_count} safe · {r.unsafe_count} flagged
                  </td>
                  <td className="px-5 py-3 text-gray-400">{formatTime(r.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </main>
  );
}
