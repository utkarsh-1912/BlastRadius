"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { History } from "lucide-react";
import { listReviews } from "@/lib/api";
import { ReviewSummary } from "@/lib/types";
import PageHeader from "@/components/ui/PageHeader";
import { Card, CardBody } from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import EmptyState from "@/components/ui/EmptyState";
import Button from "@/components/ui/Button";

const STATUS_TONE: Record<string, "success" | "warning" | "slate" | "danger"> = {
  verified: "success",
  awaiting_approval: "warning",
  rejected: "slate",
  failed: "danger",
  no_candidates: "slate",
};

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

function shortId(id: string): string {
  return id.split("-")[0]; // first segment of the UUID — enough to distinguish rows, not the full 36 chars
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
    <main className="flex flex-col pb-10">
      <PageHeader title="Review History" description="Every past review, audited — including ones no longer live in memory." />

      <div className="px-8">
        <Card>
          <CardBody className="!p-0">
            {error && <p className="p-5 text-sm text-accent">{error}</p>}
            {!error && runs === null && <p className="p-5 text-sm text-slate-400">Loading…</p>}
            {!error && runs !== null && runs.length === 0 && (
              <EmptyState
                icon={History}
                title="No reviews yet"
                description="Run your first review to see it show up here."
                action={
                  <Link href="/">
                    <Button size="sm" className="mt-2">
                      Start a review
                    </Button>
                  </Link>
                }
              />
            )}
            {!error && runs !== null && runs.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[880px] text-sm">
                  <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                    <tr>
                      <th className="px-5 py-2.5 text-left">ID</th>
                      <th className="px-5 py-2.5 text-left">Role</th>
                      <th className="px-5 py-2.5 text-left">Request</th>
                      <th className="px-5 py-2.5 text-left">Status</th>
                      <th className="px-5 py-2.5 text-left">Results</th>
                      <th className="px-5 py-2.5 text-left">Created</th>
                      <th className="px-5 py-2.5 text-left">Updated</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {runs.map((r) => (
                      <tr key={r.id} className="hover:bg-slate-50/60">
                        <td className="whitespace-nowrap px-5 py-3.5">
                          <Link href={`/reviews/${r.id}`} className="font-mono text-xs text-slate-400 hover:text-brand-600 hover:underline" title={r.id}>
                            {shortId(r.id)}
                          </Link>
                        </td>
                        <td className="whitespace-nowrap px-5 py-3.5">
                          <Link href={`/reviews/${r.id}`} className="font-medium text-slate-800 hover:text-brand-600 hover:underline">
                            {r.role_name ?? "all roles"}
                          </Link>
                        </td>
                        <td className="max-w-xs truncate px-5 py-3.5 text-slate-500">{r.request_text}</td>
                        <td className="whitespace-nowrap px-5 py-3.5">
                          <Badge tone={STATUS_TONE[r.status] ?? "slate"}>{r.status.replace(/_/g, " ")}</Badge>
                        </td>
                        <td className="whitespace-nowrap px-5 py-3.5 text-slate-500">
                          {r.safe_count} safe · {r.unsafe_count} flagged
                        </td>
                        <td className="whitespace-nowrap px-5 py-3.5 text-slate-400">{formatTime(r.created_at)}</td>
                        <td className="whitespace-nowrap px-5 py-3.5 text-slate-400">{formatTime(r.updated_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardBody>
        </Card>
      </div>
    </main>
  );
}
