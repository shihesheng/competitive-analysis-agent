type LoadingStateProps = {
  label?: string;
};

export function LoadingState({ label = "加载中..." }: LoadingStateProps) {
  return (
    <div className="flex min-h-32 items-center justify-center rounded-xl border border-slate-800 bg-slate-950/55 p-6 text-sm text-slate-300 shadow-[0_18px_50px_rgba(2,6,23,0.18)]">
      <span className="mr-3 h-2.5 w-2.5 rounded-full bg-cyan-300 shadow-[0_0_18px_rgba(103,232,249,0.8)]" />
      {label}
    </div>
  );
}
