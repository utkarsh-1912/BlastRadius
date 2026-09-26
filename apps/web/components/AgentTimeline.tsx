import { CheckCircle2, XCircle, AlertTriangle, PauseCircle, Circle, Radar } from "lucide-react";
import { TimelineEvent } from "@/lib/types";
import { Card, CardHeader, CardTitle, CardBody } from "@/components/ui/Card";
import EmptyState from "@/components/ui/EmptyState";

const KIND_META: Record<TimelineEvent["kind"], { icon: typeof Circle; dot: string; text: string }> = {
  success: { icon: CheckCircle2, dot: "text-success-500", text: "text-slate-700" },
  error: { icon: XCircle, dot: "text-accent", text: "text-accent" },
  warn: { icon: AlertTriangle, dot: "text-warning-500", text: "text-slate-700" },
  waiting: { icon: PauseCircle, dot: "text-slate-400", text: "text-slate-500" },
  info: { icon: Circle, dot: "text-slate-300", text: "text-slate-600" },
};

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString([], { hour12: false });
}

export default function AgentTimeline({ events }: { events: TimelineEvent[] }) {
  return (
    <Card className="flex h-full flex-col overflow-hidden">
      <CardHeader>
        <CardTitle>Agent Activity</CardTitle>
      </CardHeader>
      <CardBody className="flex-1 overflow-y-auto">
        {events.length === 0 ? (
          <EmptyState icon={Radar} title="Waiting for a request" description="The agent's activity will stream here." />
        ) : (
          <ol>
            {events.map((e, i) => {
              const meta = KIND_META[e.kind];
              const Icon = meta.icon;
              return (
                <li key={i} className="flex gap-3 text-sm">
                  <div className="flex flex-col items-center pt-0.5">
                    <Icon className={`h-4 w-4 shrink-0 ${meta.dot}`} strokeWidth={2} />
                    {i < events.length - 1 && <div className="my-1 w-px flex-1 bg-slate-100" />}
                  </div>
                  <div className="min-w-0 pb-4">
                    <div className="flex items-baseline gap-2">
                      <span className={`font-medium ${meta.text}`}>{e.label}</span>
                      <span className="font-mono text-[11px] text-slate-300">{formatTime(e.ts)}</span>
                    </div>
                    {e.detail && <p className="mt-0.5 text-xs leading-relaxed text-slate-500">{e.detail}</p>}
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </CardBody>
    </Card>
  );
}
