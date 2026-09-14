import { useEffect, useState, type ReactNode } from "react";
import { Tooltip } from "./Tooltip";

export type BarTone = "cyan" | "violet" | "emerald" | "amber" | "rose" | "slate";

export type BarDatum = {
  /** 唯一标识。 */
  key: string;
  /** 行标题。 */
  label: ReactNode;
  /** 数值，用于计算条形长度。 */
  value: number;
  /** 条形末尾展示的文本，默认展示 value。 */
  display?: string;
  tone?: BarTone;
  /** 悬停时展示的提示内容。 */
  tooltip?: ReactNode;
};

const barClasses: Record<BarTone, string> = {
  cyan: "bg-cyan-400",
  violet: "bg-violet-400",
  emerald: "bg-emerald-400",
  amber: "bg-amber-400",
  rose: "bg-rose-400",
  slate: "bg-slate-400",
};

// 轻量横向条形图：挂载时条形从 0 动画展开，悬停每一行可看详情。
export function InteractiveBars({
  data,
  emptyLabel = "暂无数据",
}: {
  data: BarDatum[];
  emptyLabel?: string;
}) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const id = window.requestAnimationFrame(() => setMounted(true));
    return () => window.cancelAnimationFrame(id);
  }, []);

  if (data.length === 0) {
    return <p className="text-sm text-slate-400">{emptyLabel}</p>;
  }

  const max = Math.max(1, ...data.map((item) => item.value));

  return (
    <div className="space-y-3">
      {data.map((item) => {
        const ratio = max > 0 ? item.value / max : 0;
        const width = mounted ? `${Math.max(2, ratio * 100)}%` : "0%";
        const tone = item.tone ?? "cyan";

        const row = (
          <div className="group/bar w-full cursor-default rounded-lg px-2 py-1.5 transition hover:bg-slate-50">
            <div className="flex items-center justify-between gap-3 text-sm">
              <span className="min-w-0 truncate font-medium text-slate-700">
                {item.label}
              </span>
              <span className="shrink-0 font-semibold text-slate-900">
                {item.display ?? item.value}
              </span>
            </div>
            <div className="mt-2 h-2.5 overflow-hidden rounded-full bg-slate-100">
              <div
                className={`h-full rounded-full transition-all duration-700 ease-out ${barClasses[tone]} group-hover/bar:brightness-105`}
                style={{ width }}
              />
            </div>
          </div>
        );

        if (!item.tooltip) {
          return <div key={item.key}>{row}</div>;
        }

        return (
          <Tooltip key={item.key} content={item.tooltip} width={260} className="block w-full">
            {row}
          </Tooltip>
        );
      })}
    </div>
  );
}
