import { useEffect, useRef, useState } from "react";

type Phase = "standby" | "running" | "completed";

type AgentOrbit3DProps = {
  /** standby=待命, running=分析中, completed=已完成。 */
  phase?: Phase;
};

type OrbitAgent = {
  key: string;
  zh: string;
  en: string;
  role: string;
};

const agents: OrbitAgent[] = [
  { key: "research", zh: "调研", en: "Research", role: "收集公开资料与竞品信息" },
  { key: "evidence", zh: "证据", en: "Evidence", role: "抽取结构化证据并标记可信度" },
  { key: "product", zh: "产品", en: "Product", role: "生成产品维度分析矩阵" },
  { key: "business", zh: "商业", en: "Business", role: "分析定位、价格与市场策略" },
  { key: "verification", zh: "校验", en: "Verification", role: "校验结论与矩阵是否被证据支撑" },
  { key: "risk", zh: "风险", en: "Risk", role: "识别数据缺口与潜在风险" },
  { key: "quality", zh: "质检", en: "Quality", role: "检查证据覆盖与结论可靠性" },
  { key: "strategy", zh: "策略", en: "Strategy", role: "生成最终竞品策略报告" },
];

// 轨道与中心（viewBox/百分比坐标，0-100）。
const CX = 50;
const CY = 52;
const RADIUS_X = 40;
const RADIUS_Y = 17;
const N = agents.length;

function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) {
    return false;
  }
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function AgentOrbit3D({ phase = "standby" }: AgentOrbit3DProps) {
  const [hoveredKey, setHoveredKey] = useState<string | null>(null);

  const wrapperRefs = useRef<Array<HTMLDivElement | null>>([]);
  const innerRefs = useRef<Array<HTMLDivElement | null>>([]);
  const lineRefs = useRef<Array<SVGLineElement | null>>([]);
  const particleRefs = useRef<Array<SVGCircleElement | null>>([]);
  const hoveredRef = useRef<string | null>(null);
  const frameRef = useRef<number>();

  const accent = phase === "completed" ? "#34d399" : "#7dd3fc";
  const phaseLabel =
    phase === "completed" ? "COMPLETED" : phase === "running" ? "ANALYZING" : "READY";
  const phaseZh =
    phase === "completed" ? "分析完成" : phase === "running" ? "分析进行中" : "待命就绪";

  useEffect(() => {
    hoveredRef.current = hoveredKey;
  }, [hoveredKey]);

  useEffect(() => {
    const reduced = prefersReducedMotion();

    function render(timeMs: number) {
      for (let i = 0; i < N; i += 1) {
        const wrapper = wrapperRefs.current[i];
        const inner = innerRefs.current[i];
        const line = lineRefs.current[i];
        const particle = particleRefs.current[i];

        const theta = (i / N) * Math.PI * 2 + timeMs * 0.00022;
        const cos = Math.cos(theta);
        const sin = Math.sin(theta);
        const x = CX + RADIUS_X * cos;
        const y = CY + RADIUS_Y * sin;
        const norm = (sin + 1) / 2; // 0(后/上/小) -> 1(前/下/大)
        const isHovered = hoveredRef.current === agents[i].key;
        const scale = (0.72 + 0.46 * norm) * (isHovered ? 1.18 : 1);
        const opacity = 0.55 + 0.45 * norm;
        const z = isHovered ? 40 : Math.round(norm * 18) + 1;

        if (wrapper) {
          wrapper.style.left = `${x}%`;
          wrapper.style.top = `${y}%`;
          wrapper.style.zIndex = String(z);
        }
        if (inner) {
          inner.style.transform = `scale(${scale.toFixed(3)})`;
          inner.style.opacity = opacity.toFixed(3);
        }
        if (line) {
          line.setAttribute("x2", x.toFixed(2));
          line.setAttribute("y2", y.toFixed(2));
          line.setAttribute(
            "stroke-opacity",
            isHovered ? "0.95" : (0.16 + 0.24 * norm).toFixed(2),
          );
          line.setAttribute("stroke-width", isHovered ? "0.75" : "0.4");
        }
        if (particle) {
          if (reduced) {
            particle.setAttribute("opacity", "0");
          } else {
            const f = (timeMs * 0.00055 + i / N) % 1;
            particle.setAttribute("cx", (CX + (x - CX) * f).toFixed(2));
            particle.setAttribute("cy", (CY + (y - CY) * f).toFixed(2));
            particle.setAttribute("opacity", (0.25 + 0.7 * norm).toFixed(2));
          }
        }
      }

      if (!reduced) {
        frameRef.current = window.requestAnimationFrame(render);
      }
    }

    // 至少渲染一帧（静态快照），动态时持续循环。
    frameRef.current = window.requestAnimationFrame(render);

    return () => {
      if (frameRef.current) {
        window.cancelAnimationFrame(frameRef.current);
      }
    };
  }, [phase]);

  return (
    <div className="relative mx-auto aspect-square w-full max-w-[460px]">
      {/* 连接线 + 流动粒子 */}
      <svg
        className="absolute inset-0 h-full w-full"
        viewBox="0 0 100 100"
        preserveAspectRatio="xMidYMid meet"
        aria-hidden
      >
        {agents.map((agent, i) => (
          <line
            key={`line-${agent.key}`}
            ref={(el) => {
              lineRefs.current[i] = el;
            }}
            x1={CX}
            y1={CY}
            x2={CX + RADIUS_X}
            y2={CY}
            stroke={accent}
            strokeWidth={0.4}
            strokeLinecap="round"
          />
        ))}
        {agents.map((agent, i) => (
          <circle
            key={`p-${agent.key}`}
            ref={(el) => {
              particleRefs.current[i] = el;
            }}
            r={0.9}
            cx={CX}
            cy={CY}
            fill={accent}
          />
        ))}
      </svg>

      {/* 中心核心 */}
      <div
        className="absolute left-1/2 -translate-x-1/2 -translate-y-1/2"
        style={{ left: `${CX}%`, top: `${CY}%`, zIndex: 10 }}
      >
        <div
          className="agent-core-pulse flex h-24 w-24 flex-col items-center justify-center rounded-full border bg-gradient-to-br from-[#0e1b3a] to-[#111c3e] text-center sm:h-28 sm:w-28"
          style={{ borderColor: `${accent}80` }}
        >
          <span
            className="text-[10px] font-semibold uppercase tracking-[0.16em]"
            style={{ color: accent }}
          >
            {phaseLabel}
          </span>
          <span className="mt-0.5 text-sm font-bold text-[#f1f6ff]">
            智能分析核心
          </span>
          <span className="mt-0.5 text-[10px] text-[#8aa0c6]">{phaseZh}</span>
        </div>
      </div>

      {/* 周围 Agent 节点 */}
      {agents.map((agent, i) => {
        const isHovered = hoveredKey === agent.key;
        return (
          <div
            key={agent.key}
            ref={(el) => {
              wrapperRefs.current[i] = el;
            }}
            className="absolute -translate-x-1/2 -translate-y-1/2"
            style={{ left: `${CX + RADIUS_X}%`, top: `${CY}%` }}
          >
            <div
              ref={(el) => {
                innerRefs.current[i] = el;
              }}
              className="flex min-w-[58px] cursor-default flex-col items-center rounded-xl border bg-[#0b1226]/85 px-2.5 py-1.5 text-center backdrop-blur-sm transition-[box-shadow] duration-200"
              style={{
                borderColor: `${accent}55`,
                boxShadow: isHovered ? `0 0 22px ${accent}99` : undefined,
              }}
              onMouseEnter={() => setHoveredKey(agent.key)}
              onMouseLeave={() =>
                setHoveredKey((current) =>
                  current === agent.key ? null : current,
                )
              }
            >
              <span className="flex items-center gap-1 text-sm font-semibold text-[#e6eefc]">
                {agent.zh}
                {phase === "completed" ? (
                  <span className="h-1.5 w-1.5 rounded-full bg-[#34d399]" />
                ) : null}
              </span>
              <span
                className="text-[9px] uppercase tracking-[0.1em]"
                style={{ color: accent }}
              >
                {agent.en}
              </span>
            </div>

            {/* hover tooltip（随节点移动，不被缩放） */}
            <div
              className={`pointer-events-none absolute bottom-full left-1/2 z-[45] mb-2 w-44 -translate-x-1/2 rounded-lg border border-[#38bdf8]/40 bg-[#0a1326]/95 px-3 py-2 text-center shadow-[0_14px_40px_rgba(2,6,23,0.6)] backdrop-blur-md transition duration-150 ${
                isHovered ? "scale-100 opacity-100" : "scale-95 opacity-0"
              }`}
            >
              <p className="text-xs font-semibold text-[#f1f6ff]">
                {agent.zh} <span style={{ color: accent }}>{agent.en}</span>
              </p>
              <p className="mt-1 text-[11px] leading-4 text-[#9fb2d4]">
                {agent.role}
              </p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
