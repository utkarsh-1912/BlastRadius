import { Understood } from "@/lib/types";
import { Card, CardHeader, CardTitle, CardBody } from "@/components/ui/Card";

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs text-slate-400">{label}</div>
      <div className="mt-0.5 text-sm font-medium text-slate-800">{value}</div>
    </div>
  );
}

export default function ConstraintPanel({ understood }: { understood: Understood }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Formalized Request</CardTitle>
      </CardHeader>
      <CardBody>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Role" value={understood.role_name ?? understood.role_prefix ?? "all roles"} />
          <Field label="Lookback window" value={`${understood.lookback_days} days`} />
          <Field label="Excluded actions" value={understood.exclude_actions.length ? understood.exclude_actions.join(", ") : "none"} />
          <Field
            label="Excluded roles"
            value={understood.exclude_role_patterns.length ? understood.exclude_role_patterns.join(", ") : "none"}
          />
        </div>
        <p className="mt-4 border-t border-slate-100 pt-3 text-xs text-slate-400">
          Only literal, unused actions are ever proposed — wildcard grants (e.g. <code>s3:*</code>) are never touched.
        </p>
      </CardBody>
    </Card>
  );
}
