import { Card, CardHeader, CardTitle, CardBody } from "@/components/ui/Card";

interface Props {
  totalCandidates: number;
  safeCount: number;
  unsafeCount: number;
  validatorSource: string | null;
  sandboxUsed: boolean;
}

export default function ValidationPanel({ totalCandidates, safeCount, unsafeCount, validatorSource, sandboxUsed }: Props) {
  const items = [
    { label: "Candidates found", value: totalCandidates, ok: true },
    { label: "Safe (both evaluators agree)", value: safeCount, ok: true },
    { label: "Flagged / excluded", value: unsafeCount, ok: unsafeCount === 0 },
    { label: "Sandbox executed", value: sandboxUsed ? "yes" : "local fallback", ok: sandboxUsed },
  ];
  return (
    <Card>
      <CardHeader>
        <CardTitle>Independent Validation</CardTitle>
      </CardHeader>
      <CardBody>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {items.map((it) => (
            <div key={it.label} className="rounded-lg border border-slate-100 bg-slate-50/60 px-3 py-2.5">
              <div className="text-xs text-slate-500">{it.label}</div>
              <div className={`mt-0.5 text-lg font-semibold ${it.ok ? "text-slate-900" : "text-accent"}`}>{it.value}</div>
            </div>
          ))}
        </div>
        <p className="mt-3 text-xs text-slate-400">
          Cross-check evaluator: {validatorSource === "aws" ? "real AWS iam:SimulateCustomPolicy" : validatorSource ?? "n/a"}
        </p>
      </CardBody>
    </Card>
  );
}
