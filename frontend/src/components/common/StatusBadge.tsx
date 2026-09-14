type StatusBadgeProps = {
  label: string;
  tone?: "neutral" | "success" | "warning" | "danger" | "info";
};

const toneClasses: Record<NonNullable<StatusBadgeProps["tone"]>, string> = {
  neutral: "border-slate-700/70 bg-slate-900/70 text-slate-300",
  success: "border-emerald-400/35 bg-emerald-400/10 text-emerald-200",
  warning: "border-amber-400/35 bg-amber-400/10 text-amber-200",
  danger: "border-rose-400/35 bg-rose-500/10 text-rose-200",
  info: "border-cyan-400/35 bg-cyan-400/10 text-cyan-200",
};

export function StatusBadge({ label, tone = "neutral" }: StatusBadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium shadow-[0_0_18px_rgba(15,23,42,0.18)] transition hover:shadow-[0_0_20px_rgba(34,211,238,0.14)] ${toneClasses[tone]}`}
    >
      {label}
    </span>
  );
}
