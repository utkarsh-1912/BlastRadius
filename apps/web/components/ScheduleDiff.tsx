import { BlastRadiusChange } from "@/lib/types";

function Row({ c, safe }: { c: BlastRadiusChange; safe: boolean }) {
  return (
    <tr>
      <td className="px-4 py-2 font-medium text-gray-800">{c.action}</td>
      <td className="px-4 py-2 text-gray-500">{c.source_policy}</td>
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

export default function ScheduleDiff({ safe, unsafe }: { safe: BlastRadiusChange[]; unsafe: BlastRadiusChange[] }) {
  return (
    <section className="border-t border-gray-200 bg-white px-6 py-5">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-500">Blast Radius Results</h2>
        <span className="text-xs text-gray-400">
          {safe.length} safe to remove &middot; {unsafe.length} flagged
        </span>
      </div>
      {safe.length === 0 && unsafe.length === 0 ? (
        <p className="text-sm text-gray-500">No unused permissions found — nothing to propose.</p>
      ) : (
        <div className="overflow-hidden rounded-md border border-gray-200">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-4 py-2 text-left">Action</th>
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
