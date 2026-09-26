"use client";

import { useState } from "react";
import { Search } from "lucide-react";
import { checkPermission } from "@/lib/api";
import { PermissionCheckResult } from "@/lib/types";
import { Card, CardBody } from "@/components/ui/Card";
import Button from "@/components/ui/Button";
import Badge from "@/components/ui/Badge";
import Spinner from "@/components/ui/Spinner";

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
    <Card>
      <CardBody>
        <div className="flex flex-wrap gap-2">
          <input
            className="min-w-[160px] flex-1 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm focus:border-brand-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-brand-100"
            placeholder="Role name, e.g. data-pipeline-role"
            value={roleName}
            onChange={(e) => setRoleName(e.target.value)}
          />
          <input
            className="min-w-[160px] flex-1 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm focus:border-brand-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-brand-100"
            placeholder="Action, e.g. s3:DeleteObject"
            value={action}
            onChange={(e) => setAction(e.target.value)}
          />
          <Button onClick={handleCheck} disabled={loading || !roleName.trim() || !action.trim()}>
            {loading ? <Spinner className="h-4 w-4" /> : <Search className="h-4 w-4" />}
            {loading ? "Checking…" : "Check"}
          </Button>
        </div>

        {error && <p className="mt-3 text-sm text-accent">{error}</p>}

        {result && !result.granted && <p className="mt-3 text-sm text-slate-500">{result.message}</p>}

        {result && result.granted && (
          <div className="mt-4 rounded-lg border border-slate-100 bg-slate-50/60 p-4 text-sm">
            <div className="flex items-center justify-between">
              <span className="font-mono font-medium text-slate-800">{result.action}</span>
              <Badge tone={result.safe_to_remove ? "success" : "danger"}>
                {result.safe_to_remove ? "Safe to remove" : "Flagged — do not remove"}
              </Badge>
            </div>
            <div className="mt-2 text-xs text-slate-500">
              {result.events_checked} historical event(s) replayed
              {result.broken_event_count > 0 ? `, ${result.broken_event_count} would now be denied` : ""} · via{" "}
              {result.validator_source === "aws" ? "real AWS policy simulator" : result.validator_source}
            </div>
            {result.shared_with_roles.length > 0 && (
              <div className="mt-1 text-xs text-slate-500">Also attached to: {result.shared_with_roles.join(", ")}</div>
            )}
          </div>
        )}
      </CardBody>
    </Card>
  );
}
