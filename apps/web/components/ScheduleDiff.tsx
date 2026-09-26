"use client";

import { BlastRadiusChange } from "@/lib/types";

const SEVERITY_STYLES: Record<string, string> = {
  critical: "bg-red-100 text-red-800",
  high: "bg-orange-100 text-orange-800",
  medium: "bg-amber-100 text-amber-800",
  low: "bg-gray-100 text-gray-600",
};

function SeverityBadge({ severity }: { severity: string }) {
  return (
    <span className={`rounded px-1.5 py-0.5 text-xs font-medium uppercase ${SEVERITY_STYLES[severity] ?? SEVERITY_STYLES.medium}`}>
      {severity}
    </span>
  );
}

function Row({ c, safe }: { c: BlastRadiusChange; safe: boolean }) {
  return (
    <tr>
      <td className="px-4 py-2">
        <div className="font-medium text-gray-800">{c.action}</div>
        {c.shared_with_roles.length > 0 && (
          <div className="text-xs text-gray-400">shared with {c.shared_with_roles.join(", ")}</div>
        )}
      </td>
      <td className="px-4 py-2">
        <SeverityBadge severity={c.severity} />
      </td>
      <td className="px-4 py-2 text-gray-500">
        {c.source_policy} <span className="text-gray-300">({c.policy_kind})</span>
      </td>
      <td className="px-4 py-2 text-gray-500">{c.last_accessed ? c.last_accessed.slice(0, 10) : "never"}</td>
      <td className="px-4 py-2 text-gray-500">
        {c.events_checked} replayed{c.broken_event_count > 0 ? `, ${c.broken_event_count} would break` : ""}
      </td>
      <td className={`px-4 py-2 font-medium ${safe ? "text-emerald-700" : "text-accent"}`}>
        {safe ? "Safe — proven by replay" : "Flagged — not auto-proposed"}
      </td>
    </tr>
  );
}

function toCsv(rows: BlastRadiusChange[]): string {
  const header = ["role_name", "action", "severity", "policy", "policy_kind", "last_accessed", "events_checked", "broken_event_count", "safe_to_remove", "shared_with_roles"];
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
    <section className="border-t border-gray-200 bg-white px-6 py-5">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-500">Blast Radius Results</h2>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-400">
            {safe.length} safe to remove &middot; {unsafe.length} flagged
          </span>
          {(safe.length > 0 || unsafe.length > 0) && (
            <button
              className="rounded border border-gray-300 px-2 py-1 text-xs font-medium text-gray-600 hover:bg-gray-50"
              onClick={() => downloadCsv([...safe, ...unsafe])}
            >
              Export CSV
            </button>
          )}
        </div>
      </div>
      {safe.length === 0 && unsafe.length === 0 ? (
        <p className="text-sm text-gray-500">No unused permissions found — nothing to propose.</p>
      ) : (
        <div className="overflow-hidden rounded-md border border-gray-200">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-4 py-2 text-left">Action</th>
                <th className="px-4 py-2 text-left">Severity</th>
                <th className="px-4 py-2 text-left">Policy</th>
                <th className="px-4 py-2 text-left">Last used</th>
                <th className="px-4 py-2 text-left">Replay</th>
                <th className="px-4 py-2 text-left">Verdict</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
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
      {unsafe.length > 0 && (
        <p className="mt-3 text-xs text-gray-500">
          Flagged permissions had real historical evidence of use with no redundant grant elsewhere — a naive
          "unused for 90 days" check would have proposed removing these too. Blast Radius excludes them from the
          auto-approved list instead.
        </p>
      )}
    </section>
  );
}
