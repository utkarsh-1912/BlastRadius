type Tone = "slate" | "success" | "warning" | "danger" | "brand";

const TONE_STYLES: Record<Tone, string> = {
  slate: "bg-slate-100 text-slate-600",
  success: "bg-success-50 text-success-700",
  warning: "bg-warning-50 text-warning-700",
  danger: "bg-red-50 text-accent-dark",
  brand: "bg-brand-50 text-brand-700",
};

export default function Badge({ tone = "slate", children }: { tone?: Tone; children: React.ReactNode }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide ${TONE_STYLES[tone]}`}>
      {children}
    </span>
  );
}
