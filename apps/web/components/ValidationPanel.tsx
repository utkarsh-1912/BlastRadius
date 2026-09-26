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
    <section className="border-t border-gray-200 bg-white px-6 py-5">
      <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-gray-500">Independent Validation</h2>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {items.map((it) => (
          <div key={it.label} className="rounded-md border border-gray-200 px-3 py-2">
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-700">{it.label}</span>
            </div>
            <div className={`mt-1 text-lg font-semibold ${it.ok ? "text-gray-900" : "text-accent"}`}>{it.value}</div>
          </div>
        ))}
      </div>
      <div className="mt-3 text-xs text-gray-400">
        Cross-check evaluator: {validatorSource === "aws" ? "real AWS iam:SimulateCustomPolicy" : validatorSource ?? "n/a"}
      </div>
    </section>
  );
}
