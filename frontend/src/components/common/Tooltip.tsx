import type { ReactNode } from "react";

type TooltipProps = {
  /** 触发悬停的内容。 */
  children: ReactNode;
  /** 悬停时展示的提示内容。 */
  content: ReactNode;
  /** 提示出现的位置，默认在下方。 */
  placement?: "top" | "bottom";
  /** 提示气泡宽度，默认 240px。 */
  width?: number;
  className?: string;
};

// 轻量 CSS 悬停提示：无需 JS 状态，依赖 group-hover 显隐。
export function Tooltip({
  children,
  content,
  placement = "bottom",
  width = 240,
  className,
}: TooltipProps) {
  const positionClasses =
    placement === "top"
      ? "bottom-full mb-2 origin-bottom"
      : "top-full mt-2 origin-top";

  return (
    <span className={`group/tooltip relative inline-flex ${className ?? ""}`}>
      {children}
      <span
        className={`pointer-events-none absolute left-1/2 z-40 -translate-x-1/2 scale-95 rounded-lg border border-slate-200 bg-white px-3 py-2 text-left text-xs leading-5 text-slate-600 opacity-0 shadow-xl transition duration-150 ease-out group-hover/tooltip:scale-100 group-hover/tooltip:opacity-100 ${positionClasses}`}
        role="tooltip"
        style={{ width: `${width}px`, maxWidth: "min(80vw, 320px)" }}
      >
        {content}
      </span>
    </span>
  );
}
