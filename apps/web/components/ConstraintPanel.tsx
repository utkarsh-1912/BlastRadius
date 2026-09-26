import { Understood } from "@/lib/types";

export default function ConstraintPanel({ understood }: { understood: Understood }) {
  return (
    <section className="border-b border-gray-200 bg-white px-6 py-5 text-sm">
      <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-gray-500">Formalized Request</h2>
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <div className="text-xs text-gray-400">Role</div>
          <div className="font-medium text-gray-800">{understood.role_name ?? understood.role_prefix ?? "all roles"}</div>
        </div>
        <div>
          <div className="text-xs text-gray-400">Lookback window</div>
          <div className="font-medium text-gray-800">{understood.lookback_days} days</div>
        </div>
        <div>
          <div className="text-xs text-gray-400">Excluded actions</div>
          <div className="font-medium text-gray-800">
            {understood.exclude_actions.length ? understood.exclude_actions.join(", ") : "none"}
          </div>
        </div>
        <div>
          <div className="text-xs text-gray-400">Excluded roles</div>
          <div className="font-medium text-gray-800">
            {understood.exclude_role_patterns.length ? understood.exclude_role_patterns.join(", ") : "none"}
          </div>
        </div>
      </div>
      <div className="mt-3 text-xs text-gray-400">
        Only literal, unused actions are ever proposed — wildcard grants (e.g. "s3:*") are never touched.
      </div>
    </section>
  );
}
