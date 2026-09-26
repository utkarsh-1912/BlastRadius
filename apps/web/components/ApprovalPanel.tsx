"use client";

import { CheckCircle2, ShieldAlert } from "lucide-react";
import { ReviewRun } from "@/lib/types";
import { Card, CardBody } from "@/components/ui/Card";
import Button from "@/components/ui/Button";
import Spinner from "@/components/ui/Spinner";

interface Props {
  run: ReviewRun;
  onApprove: () => void;
  onReject: () => void;
  busy: boolean;
}

export default function ApprovalPanel({ run, onApprove, onReject, busy }: Props) {
  if (run.status === "awaiting_approval") {
    return (
      <Card className="border-warning-500/30 bg-warning-50/40">
        <CardBody>
          <div className="flex items-start gap-3">
            <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-warning-500" strokeWidth={2} />
            <p className="text-sm text-slate-700">
              Blast radius analysis complete. <strong>{run.safe_changes.length}</strong> permission(s) proven safe to
              remove; <strong>{run.unsafe_candidates.length}</strong> flagged and excluded.
              <br />
              Nothing has been changed in AWS IAM yet. Approve the safe removals?
            </p>
          </div>
          <div className="mt-4 flex gap-3">
            <Button variant="secondary" onClick={onReject} disabled={busy}>
              Reject
            </Button>
            <Button variant="destructive" onClick={onApprove} disabled={busy || run.safe_changes.length === 0}>
              {busy && <Spinner className="h-4 w-4" />}
              Approve &amp; Revoke in AWS IAM
            </Button>
          </div>
        </CardBody>
      </Card>
    );
  }

  if (run.status === "rejected") {
    return (
      <Card>
        <CardBody className="text-sm text-slate-500">No changes were made to AWS IAM.</CardBody>
      </Card>
    );
  }

  if (run.status === "no_candidates") {
    return (
      <Card>
        <CardBody className="text-sm text-slate-500">No unused permissions found for this role. Nothing to propose.</CardBody>
      </Card>
    );
  }

  if (run.status === "verified" && run.verify_result) {
    return (
      <Card className="border-success-500/30 bg-success-50/40">
        <CardBody className="space-y-2 text-sm text-success-700">
          {[
            `${run.verify_result.roles_updated} role(s) updated`,
            "AWS IAM re-read",
            `${run.verify_result.permissions_removed} permission(s) confirmed removed`,
            "Verification passed",
          ].map((line) => (
            <div key={line} className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 shrink-0" strokeWidth={2} />
              {line}
            </div>
          ))}
        </CardBody>
      </Card>
    );
  }

  if (run.status === "failed") {
    return (
      <Card className="border-accent/30 bg-red-50/40">
        <CardBody className="text-sm text-accent-dark">{run.error}</CardBody>
      </Card>
    );
  }

  return null;
}
