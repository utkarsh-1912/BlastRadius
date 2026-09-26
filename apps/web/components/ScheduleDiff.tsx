"use client";

import { Download } from "lucide-react";
import { BlastRadiusChange } from "@/lib/types";
import { Card, CardHeader, CardTitle, CardBody } from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";

const SEVERITY_TONE: Record<string, "danger" | "warning" | "slate"> = {
  critical: "danger",
  high: "warning",
  medium: "slate",
  low: "slate",
};

function Row({ c, safe }: { c: BlastRadiusChange; safe: boolean }) {
  return (
    <tr>
      <td className="px-4 py-3">
        <div className="font-mono text-[13px] font-medium text-slate-800">{c.action}</div>
        {c.shared_with_roles.length > 0 && <div className="mt-0.5 text-xs text-slate-400">shared with {c.shared_with_roles.join(", ")}</div>}
      </td>
      <td className="px-4 py-3">
        <Badge tone={SEVERITY_TONE[c.severity] ?? "slate"}>{c.severity}</Badge>
      </td>
      <td className="px-4 py-3 text-slate-500">
        {c.source_policy} <span className="text-slate-300">({c.policy_kind})</span>
      </td>
      <td className="px-4 py-3 text-slate-500">{c.last_accessed ? c.last_accessed.slice(0, 10) : "never"}</td>
      <td className="px-4 py-3 text-slate-500">
        {c.events_checked} replayed{c.broken_event_count > 0 ? `, ${c.broken_event_count} would break` : ""}
      </td>
      <td className="px-4 py-3">
        <Badge tone={safe ? "success" : "danger"}>{safe ? "Safe" : "Flagged"}</Badge>
      </td>
    </tr>
  );
}

function toCsv(rows: BlastRadiusChange[]): string {
  const header = [
    "role_name",
    "action",
    "severity",
    "policy",
    "policy_kind",
    "last_accessed",
    "events_checked",
    "broken_event_count",
    "safe_to_remove",
    "shared_with_roles",
  ];
  const lines = rows.map((c) =>
    [
      c.role_name,
      c.action,
      c.severity,
      c.source_policy,
      c.policy_kind,
      c.last_accessed ?? "never",
      c.events_checked,
      c.broken_event_count,
      c.safe_to_remove,
      c.shared_with_roles.join("|"),
    ]
      .map((v) => `"${String(v).replace(/"/g, '""')}"`)
      .join(",")
  );
  return [header.join(","), ...lines].join("\n");
}

function downloadCsv(rows: BlastRadiusChange[]) {
  const csv = toCsv(rows);
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `blast-radius-report-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export default function ScheduleDiff({ safe, unsafe }: { safe: BlastRadiusChange[]; unsafe: BlastRadiusChange[] }) {
  return (
    <Card>
      <CardHeader className="flex items-center justify-between">
        <CardTitle>Blast Radius Results</CardTitle>
        <div className="flex items-center gap-3">
          <span className="text-xs text-slate-400">
            {safe.length} safe &middot; {unsafe.length} flagged
          </span>
          {(safe.length > 0 || unsafe.length > 0) && (
            <Button variant="secondary" size="sm" onClick={() => downloadCsv([...safe, ...unsafe])}>
              <Download className="h-3.5 w-3.5" />
              Export CSV
            </Button>
          )}
        </div>
      </CardHeader>
      <CardBody className="!p-0">
        {safe.length === 0 && unsafe.length === 0 ? (
          <p className="p-5 text-sm text-slate-500">No unused permissions found — nothing to propose.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="whitespace-nowrap px-4 py-2 text-left">Action</th>
                  <th className="whitespace-nowrap px-4 py-2 text-left">Severity</th>
                  <th className="whitespace-nowrap px-4 py-2 text-left">Policy</th>
                  <th className="whitespace-nowrap px-4 py-2 text-left">Last used</th>
                  <th className="whitespace-nowrap px-4 py-2 text-left">Replay</th>
                  <th className="whitespace-nowrap px-4 py-2 text-left">Verdict</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {safe.map((c) => (
                  <Row key={`${c.role_name}-${c.action}`} c={c} safe={true} />
                ))}
                {unsafe.map((c) => (
                  <Row key={`${c.role_name}-${c.action}`} c={c} safe={false} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardBody>
      {unsafe.length > 0 && (
        <p className="border-t border-slate-100 px-5 py-3 text-xs text-slate-400">
          Flagged permissions had real historical evidence of use with no redundant grant elsewhere — a naive
          &ldquo;unused for 90 days&rdquo; check would have proposed removing these too.
        </p>
      )}
    </Card>
  );
}
