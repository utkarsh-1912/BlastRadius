"use client";

import { useState } from "react";
import { checkPermission } from "@/lib/api";
import { PermissionCheckResult } from "@/lib/types";

export default function PermissionCheckPanel() {
  const [roleName, setRoleName] = useState("");
  const [action, setAction] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<PermissionCheckResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleCheck = async () => {
    if (!roleName.trim() || !action.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await checkPermission(roleName.trim(), action.trim()));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="rounded-md border border-gray-200 bg-white p-5">
      <h2 className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">Check a Single Permission</h2>
      <p className="mb-3 text-xs text-gray-400">
        A quick, read-only spot-check — no review, no approval needed, because this never writes anything.
      </p>
      <div className="flex flex-wrap gap-2">
        <input
          className="min-w-[160px] flex-1 rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-gray-500 focus:outline-none"
          placeholder="Role name, e.g. data-pipeline-role"
          value={roleName}
          onChange={(e) => setRoleName(e.target.value)}
        />
        <input
          className="min-w-[160px] flex-1 rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-gray-500 focus:outline-none"
          placeholder="Action, e.g. s3:DeleteObject"
          value={action}
          onChange={(e) => setAction(e.target.value)}
        />
        <button
          className="rounded-md bg-gray-900 px-4 py-1.5 text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-40"
          onClick={handleCheck}
          disabled={loading || !roleName.trim() || !action.trim()}
        >
          {loading ? "Checking…" : "Check"}
        </button>
      </div>

      {error && <p className="mt-3 text-sm text-accent">{error}</p>}

      {result && !result.granted && <p className="mt-3 text-sm text-gray-600">{result.message}</p>}

      {result && result.granted && (
        <div className="mt-3 rounded-md border border-gray-200 p-3 text-sm">
          <div className="flex items-center justify-between">
            <span className="font-medium text-gray-800">{result.action}</span>
            <span className={result.safe_to_remove ? "font-medium text-emerald-700" : "font-medium text-accent"}>
              {result.safe_to_remove ? "Safe to remove" : "Flagged — do not remove"}
            </span>
          </div>
          <div className="mt-1 text-xs text-gray-500">
            {result.events_checked} historical event(s) replayed
            {result.broken_event_count > 0 ? `, ${result.broken_event_count} would now be denied` : ""} · via{" "}
            {result.validator_source === "aws" ? "real AWS policy simulator" : result.validator_source}
          </div>
          {result.shared_with_roles.length > 0 && (
            <div className="mt-1 text-xs text-gray-500">Also attached to: {result.shared_with_roles.join(", ")}</div>
          )}
        </div>
      )}
    </section>
  );
}
