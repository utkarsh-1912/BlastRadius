"use client";

import { useEffect, useState } from "react";
import { Search } from "lucide-react";
import { checkPermission, listRoleActions, listRoles } from "@/lib/api";
import { PermissionCheckResult } from "@/lib/types";
import { Card, CardBody } from "@/components/ui/Card";
import Button from "@/components/ui/Button";
import Badge from "@/components/ui/Badge";
import Spinner from "@/components/ui/Spinner";

const SEVERITY_TONE: Record<string, "danger" | "warning" | "slate"> = {
  critical: "danger",
  high: "warning",
  medium: "slate",
  low: "slate",
};

function formatEventTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
  } catch {
    return iso;
  }
}

export default function PermissionCheckPanel() {
  const [roleName, setRoleName] = useState("");
  const [action, setAction] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<PermissionCheckResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [roleOptions, setRoleOptions] = useState<string[]>([]);
  const [actionOptions, setActionOptions] = useState<string[]>([]);

  // Populate real role names once, for the role field's autocomplete.
  useEffect(() => {
    listRoles().then((roles) => setRoleOptions(roles.map((r) => r.role_name)));
  }, []);

  // Once a real role is picked, populate ITS real granted actions — so the
  // action field suggests something that actually exists, not a guess.
  useEffect(() => {
    if (!roleOptions.includes(roleName)) {
      setActionOptions([]);
      return;
    }
    listRoleActions(roleName).then(setActionOptions);
  }, [roleName, roleOptions]);

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
    <Card>
      <CardBody>
        <form
          className="flex flex-wrap gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            handleCheck();
          }}
        >
          <input
            list="check-role-options"
            className="min-w-[160px] flex-1 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm focus:border-brand-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-brand-100"
            placeholder="Role name, e.g. data-pipeline-role"
            value={roleName}
            onChange={(e) => setRoleName(e.target.value)}
          />
          <datalist id="check-role-options">
            {roleOptions.map((r) => (
              <option key={r} value={r} />
            ))}
          </datalist>

          <input
            list="check-action-options"
            className="min-w-[160px] flex-1 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-mono focus:border-brand-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-brand-100"
            placeholder="Action, e.g. s3:DeleteObject"
            value={action}
            onChange={(e) => setAction(e.target.value)}
          />
          <datalist id="check-action-options">
            {actionOptions.map((a) => (
              <option key={a} value={a} />
            ))}
          </datalist>

          <Button type="submit" disabled={loading || !roleName.trim() || !action.trim()}>
            {loading ? <Spinner className="h-4 w-4" /> : <Search className="h-4 w-4" />}
            {loading ? "Checking…" : "Check"}
          </Button>
        </form>

        {roleOptions.length > 0 && !result && !error && (
          <p className="mt-2 text-xs text-slate-400">
            {roleOptions.length} real role(s) in this account &middot; pick one to see its actual granted actions
          </p>
        )}

        {error && <p className="mt-3 text-sm text-accent">{error}</p>}

        {result && !result.granted && <p className="mt-3 text-sm text-slate-500">{result.message}</p>}

        {result && result.granted && (
          <div className="mt-4 rounded-lg border border-slate-100 bg-slate-50/60 p-4 text-sm">
            <div className="flex items-center justify-between gap-2">
              <span className="font-mono font-medium text-slate-800">{result.action}</span>
              <div className="flex items-center gap-2">
                <Badge tone={SEVERITY_TONE[result.severity] ?? "slate"}>{result.severity}</Badge>
                <Badge tone={result.safe_to_remove ? "success" : "danger"}>
                  {result.safe_to_remove ? "Safe to remove" : "Flagged — do not remove"}
                </Badge>
              </div>
            </div>

            <div className="mt-2 text-xs text-slate-500">{result.reason}</div>

            <div className="mt-2 text-xs text-slate-500">
              {result.events_checked} historical event(s) replayed
              {result.broken_event_count > 0 ? `, ${result.broken_event_count} would now be denied` : ""} · via{" "}
              {result.validator_source === "aws" ? "real AWS policy simulator" : result.validator_source}
            </div>

            {result.shared_with_roles.length > 0 && (
              <div className="mt-1 text-xs text-slate-500">Also attached to: {result.shared_with_roles.join(", ")}</div>
            )}

            {result.broken_events_sample.length > 0 && (
              <div className="mt-3 border-t border-slate-200 pt-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Why it's flagged</p>
                <ul className="mt-2 space-y-1.5">
                  {result.broken_events_sample.map((ev, i) => (
                    <li key={i} className="text-xs text-slate-600">
                      <span className="font-mono">{ev.action}</span> &middot; {formatEventTime(ev.event_time)}
                      {ev.resource_arns.length > 0 && (
                        <span className="text-slate-400"> &middot; {ev.resource_arns.join(", ")}</span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </CardBody>
    </Card>
  );
}
