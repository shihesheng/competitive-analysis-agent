import { useEffect, useRef, useState } from "react";

type ScoreRingProps = {
  /** 当前得分。 */
  value: number;
  /** 满分，默认 100。 */
  max?: number;
  label: string;
  /** 环的色调。 */
  tone?: "cyan" | "emerald" | "amber" | "rose";
  /** 小数位，默认 0。 */
  decimals?: number;
};

const toneColor: Record<NonNullable<ScoreRingProps["tone"]>, string> = {
  cyan: "rgb(34 211 238)",
  emerald: "rgb(52 211 153)",
  amber: "rgb(251 191 36)",
  rose: "rgb(244 63 94)",
};

// 得分圆环：挂载时从 0 动画递增到目标分数。
export function ScoreRing({
  value,
  max = 100,
  label,
  tone = "cyan",
  decimals = 0,
}: ScoreRingProps) {
  const [animated, setAnimated] = useState(0);
  const frameRef = useRef<number>();

  useEffect(() => {
    const start = performance.now();
    const duration = 900;
    const target = Number.isFinite(value) ? value : 0;

    function tick(now: number) {
      const progress = Math.min(1, (now - start) / duration);
      // easeOutCubic
      const eased = 1 - Math.pow(1 - progress, 3);
      setAnimated(target * eased);

      if (progress < 1) {
        frameRef.current = window.requestAnimationFrame(tick);
      }
    }

    frameRef.current = window.requestAnimationFrame(tick);

    return () => {
      if (frameRef.current) {
        window.cancelAnimationFrame(frameRef.current);
      }
    };
  }, [value]);

  const percent = max > 0 ? Math.max(0, Math.min(100, (animated / max) * 100)) : 0;
  const color = toneColor[tone];

  return (
    <div className="flex flex-col items-center">
      <div
        className="flex h-28 w-28 items-center justify-center rounded-full"
        style={{
          background: `conic-gradient(${color} ${percent}%, rgb(226 232 240) ${percent}% 100%)`,
        }}
      >
        <div className="flex h-20 w-20 flex-col items-center justify-center rounded-full bg-white">
          <span className="text-2xl font-semibold text-slate-900">
            {animated.toFixed(decimals)}
          </span>
          <span className="text-[10px] uppercase tracking-[0.18em] text-slate-400">
            / {max}
          </span>
        </div>
      </div>
      <p className="mt-3 text-sm font-medium text-slate-600">{label}</p>
    </div>
  );
}
