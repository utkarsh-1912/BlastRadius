import { TimelineEvent } from "@/lib/types";

const KIND_STYLES: Record<TimelineEvent["kind"], string> = {
  success: "text-emerald-700",
  error: "text-accent",
  warn: "text-amber-700",
  waiting: "text-gray-500",
  info: "text-gray-700",
};

const KIND_MARK: Record<TimelineEvent["kind"], string> = {
  success: "✓",
  error: "✗",
  warn: "!",
  waiting: "⏸",
  info: "·",
};

function formatTime(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString([], { hour12: false });
}

export default function AgentTimeline({ events }: { events: TimelineEvent[] }) {
  return (
    <section className="flex flex-col border-r border-gray-200 bg-white">
      <div className="border-b border-gray-100 px-5 py-3 text-xs font-semibold uppercase tracking-wide text-gray-500">
        Agent Activity
      </div>
      <div className="flex-1 space-y-2 overflow-y-auto px-5 py-4">
        {events.length === 0 && <p className="text-sm text-gray-400">Waiting for a planning request…</p>}
        {events.map((e, i) => (
          <div key={i} className="flex gap-2 text-sm">
            <span className="w-16 shrink-0 font-mono text-xs text-gray-400">{formatTime(e.ts)}</span>
            <span className={`shrink-0 font-mono ${KIND_STYLES[e.kind]}`}>{KIND_MARK[e.kind]}</span>
            <div>
              <div className={`font-medium ${KIND_STYLES[e.kind]}`}>{e.label}</div>
              {e.detail && <div className="text-xs text-gray-500">{e.detail}</div>}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
