type MetricCardProps = {
  label: string;
  value: string | number;
  helper?: string;
};

export function MetricCard({ label, value, helper }: MetricCardProps) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-4 shadow-[0_18px_50px_rgba(2,6,23,0.18)] transition duration-200 hover:-translate-y-0.5 hover:border-cyan-300/40 hover:shadow-[0_18px_50px_rgba(8,145,178,0.12)]">
      <p className="text-sm text-slate-400">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-slate-50">{value}</p>
      {helper ? <p className="mt-2 text-xs text-slate-500">{helper}</p> : null}
    </div>
  );
}
