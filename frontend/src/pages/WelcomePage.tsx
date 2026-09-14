import { useEffect, useRef, useState, type ReactNode } from "react";
import { authApi, type AuthUser } from "../api/authApi";
import { ParticleField } from "../components/common/ParticleField";

type WelcomePageProps = {
  onLogin: (token: string, user: AuthUser) => void;
};

type AgentNode = {
  key: string;
  zh: string;
  en: string;
  role: string;
  x: number;
  y: number;
};

const agentLabels: Array<Omit<AgentNode, "x" | "y">> = [
  { key: "research", zh: "调研", en: "Research", role: "规划本次需要采集和补齐的数据" },
  { key: "collector", zh: "采集", en: "Collector", role: "产品识别、本地事实读取与 MCP 调度" },
  { key: "evidence", zh: "证据", en: "Evidence", role: "抽取结构化证据并标记可信度" },
  { key: "analysis", zh: "分析", en: "Analysis", role: "只分析有证据支撑的事实差异" },
  { key: "verification", zh: "校验", en: "Verification", role: "忠实性校验，剔除无证据支撑的结论" },
  { key: "quality", zh: "质检", en: "Quality", role: "检查证据覆盖与结论可靠性" },
  { key: "report", zh: "报告", en: "Report", role: "生成专业电竞鼠标 final_report" },
];

// 在以 (50,50) 为圆心、半径 36 的圆上均匀分布 Agent 节点（数量由 agentLabels 决定，viewBox 0-100 单位）。
const CENTER = 50;
const RADIUS = 36;
const agentNodes: AgentNode[] = agentLabels.map((label, index) => {
  const angle = (-90 + (index * 360) / agentLabels.length) * (Math.PI / 180);
  return {
    ...label,
    x: CENTER + RADIUS * Math.cos(angle),
    y: CENTER + RADIUS * Math.sin(angle),
  };
});

// 能力流程带：数据规划 → 证据结构化 → 事实校验 → 质量门控 → 专业报告
const capabilitySteps = [
  { zh: "数据规划", tip: "拆解本地事实、官网规格、评价测评和实时价格需求" },
  { zh: "证据抽取", tip: "提取可引用证据并生成 Evidence ID" },
  { zh: "事实校验", tip: "检查 Claim 是否被 evidence_ids 支撑" },
  { zh: "质量门控", tip: "检查覆盖率、证据完整性与风险水位" },
  { zh: "专业报告", tip: "生成电竞鼠标专业 schema 报告" },
];

// 右侧 Agent 网络下方的系统状态。
const systemStatus = [
  "多 Agent 网络已就绪",
  "证据抽取管线待命",
  "质量门控已开启",
  "专业报告引擎就绪",
];

const agentSummary: Array<{ en: string; zh: string }> = [
  { en: "Research", zh: "调研规划" },
  { en: "Collector", zh: "采集识别" },
  { en: "Evidence", zh: "证据结构化" },
  { en: "Analysis", zh: "事实分析" },
  { en: "Verification", zh: "忠实校验" },
  { en: "Quality", zh: "质量审查" },
  { en: "Report", zh: "报告生成" },
];

function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) {
      return;
    }

    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(query.matches);

    const handler = (event: MediaQueryListEvent) => setReduced(event.matches);
    query.addEventListener?.("change", handler);
    return () => query.removeEventListener?.("change", handler);
  }, []);

  return reduced;
}

// hover 时在上方/下方弹出的指标详情卡片，不 hover 时完全隐藏，不占布局。
function StatCard({
  value,
  label,
  detailPlacement = "top",
  children,
}: {
  value: string;
  label: string;
  detailPlacement?: "top" | "bottom";
  children: ReactNode;
}) {
  const detailPosition =
    detailPlacement === "top" ? "bottom-full mb-3" : "top-full mt-3";

  return (
    <div className="group relative">
      <div className="cursor-default rounded-xl border border-[#ffffff1a] bg-white/5 px-3 py-4 text-center backdrop-blur-sm transition duration-200 group-hover:-translate-y-1 group-hover:border-[#38bdf8]/60 group-hover:bg-[#38bdf8]/10 group-hover:shadow-[0_14px_40px_rgba(56,189,248,0.28)]">
        <p className="text-2xl font-bold text-[#f1f6ff]">{value}</p>
        <p className="mt-1 text-xs leading-5 text-[#8aa0c6]">{label}</p>
      </div>
      <div
        className={`pointer-events-none absolute left-1/2 z-20 w-64 -translate-x-1/2 scale-95 rounded-xl border border-[#38bdf8]/30 bg-[#0a1326]/95 p-4 text-left opacity-0 shadow-[0_20px_60px_rgba(2,6,23,0.6)] backdrop-blur-md transition duration-200 ease-out group-hover:scale-100 group-hover:opacity-100 ${detailPosition}`}
      >
        {children}
      </div>
    </div>
  );
}

export function WelcomePage({ onLogin }: WelcomePageProps) {
  const reducedMotion = usePrefersReducedMotion();
  const [pointer, setPointer] = useState({ x: 0, y: 0 });
  const [hoveredAgent, setHoveredAgent] = useState<string | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);
  const frameRef = useRef<number>();

  async function handleLoginSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (loading) {
      return;
    }

    setLoginError(null);
    setLoading(true);
    try {
      const result = await authApi.login(username.trim(), password);
      onLogin(result.token, result.user);
    } catch (err) {
      setLoginError(err instanceof Error ? err.message : "账号或密码错误");
    } finally {
      setLoading(false);
    }
  }

  function handlePointerMove(event: React.MouseEvent<HTMLDivElement>) {
    if (reducedMotion) {
      return;
    }

    const x = event.clientX / window.innerWidth - 0.5;
    const y = event.clientY / window.innerHeight - 0.5;

    if (frameRef.current) {
      window.cancelAnimationFrame(frameRef.current);
    }
    frameRef.current = window.requestAnimationFrame(() => setPointer({ x, y }));
  }

  useEffect(() => {
    return () => {
      if (frameRef.current) {
        window.cancelAnimationFrame(frameRef.current);
      }
    };
  }, []);

  const parallax = (depth: number) => ({
    transform: `translate3d(${pointer.x * depth}px, ${pointer.y * depth}px, 0)`,
  });

  return (
    <div
      className="relative min-h-screen w-full overflow-hidden"
      onMouseMove={handlePointerMove}
      style={{
        background:
          "radial-gradient(1100px 560px at 50% -6%, rgba(56,130,246,0.12), transparent 60%)," +
          "linear-gradient(180deg, #05070e 0%, #060a16 55%, #03040c 100%)",
      }}
    >
      {/* 自研 canvas 粒子背景 */}
      <ParticleField className="pointer-events-none absolute inset-0" />

      {/* 动态网格 */}
      <div
        className="welcome-grid pointer-events-none absolute inset-[-60px] opacity-60"
        style={parallax(-12)}
        aria-hidden
      />

      {/* 模糊渐变光斑 */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
        <div
          className="welcome-blob absolute -left-24 top-10 h-80 w-80 rounded-full bg-[#22d3ee]/20 blur-3xl"
          style={parallax(18)}
        />
        <div
          className="welcome-blob absolute right-[-6rem] top-1/3 h-96 w-96 rounded-full bg-[#818cf8]/20 blur-3xl"
          style={{ ...parallax(26), animationDelay: "3s" }}
        />
        <div
          className="welcome-blob absolute bottom-[-8rem] left-1/3 h-80 w-80 rounded-full bg-[#2563eb]/15 blur-3xl"
          style={{ ...parallax(14), animationDelay: "1.5s" }}
        />

        {/* 背景中很淡的数据流线条 */}
        <svg
          className="absolute bottom-0 right-0 h-1/2 w-2/3 opacity-40"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          aria-hidden
        >
          <line className="welcome-flow" x1="0" y1="78" x2="100" y2="92" stroke="rgba(56,189,248,0.4)" strokeWidth="0.3" />
          <line className="welcome-flow" x1="12" y1="100" x2="100" y2="64" stroke="rgba(129,140,248,0.4)" strokeWidth="0.3" style={{ animationDelay: "0.6s" }} />
          <line className="welcome-flow" x1="40" y1="100" x2="100" y2="40" stroke="rgba(56,189,248,0.3)" strokeWidth="0.3" style={{ animationDelay: "1.1s" }} />
        </svg>

        {/* 右侧竖向数据流 */}
        <svg
          className="absolute right-0 top-0 hidden h-full w-1/3 opacity-30 lg:block"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          aria-hidden
        >
          <line className="welcome-flow" x1="84" y1="0" x2="78" y2="100" stroke="rgba(56,189,248,0.4)" strokeWidth="0.25" style={{ animationDelay: "0.3s" }} />
          <line className="welcome-flow" x1="94" y1="0" x2="100" y2="100" stroke="rgba(129,140,248,0.35)" strokeWidth="0.25" style={{ animationDelay: "0.9s" }} />
          <line className="welcome-flow" x1="70" y1="0" x2="64" y2="100" stroke="rgba(56,189,248,0.25)" strokeWidth="0.25" style={{ animationDelay: "1.4s" }} />
        </svg>
      </div>

      {/* 跟随鼠标的柔光 */}
      {!reducedMotion ? (
        <div
          className="pointer-events-none absolute h-[480px] w-[480px] rounded-full bg-[#38bdf8]/10 blur-3xl"
          style={{
            left: `calc(50% + ${pointer.x * 220}px)`,
            top: `calc(50% + ${pointer.y * 220}px)`,
            transform: "translate(-50%, -50%)",
          }}
          aria-hidden
        />
      ) : null}

      <div className="relative z-10 mx-auto flex min-h-screen max-w-7xl flex-col items-center gap-10 px-6 py-12 lg:flex-row lg:gap-12 lg:py-16">
        {/* 左侧文案 */}
        <div className="w-full max-w-xl lg:flex-1">
          <span
            className="welcome-fade-up inline-flex items-center gap-2 rounded-full border border-[#38bdf8]/30 bg-[#38bdf8]/10 px-3 py-1.5 text-xs font-semibold tracking-[0.18em] text-[#7dd3fc]"
            style={{ animationDelay: "0s" }}
          >
            <span className="h-1.5 w-1.5 rounded-full bg-[#38bdf8]" />
            BYTEDANCE AI CHALLENGE
          </span>

          <h1
            className="welcome-fade-up mt-6 text-4xl font-bold leading-tight text-[#f1f6ff] sm:text-5xl lg:text-6xl"
            style={{ animationDelay: "0.12s" }}
          >
            字节跳动 AI 挑战赛
          </h1>
          <p
            className="welcome-fade-up mt-4 bg-gradient-to-r from-[#67e8f9] via-[#818cf8] to-[#c084fc] bg-clip-text text-2xl font-semibold text-transparent sm:text-3xl"
            style={{ animationDelay: "0.24s" }}
          >
            AI 竞品情报中枢
          </p>

          <p
            className="welcome-fade-up mt-6 max-w-lg text-base leading-7 text-[#9fb2d4]"
            style={{ animationDelay: "0.36s" }}
          >
            多 Agent 协同完成数据规划、证据结构化、事实校验、质量审查与专业报告生成。当前聚焦电竞鼠标竞品分析，从稳定硬件事实和可追溯证据生成可信报告。
          </p>

          {/* 能力流程带 */}
          <div
            className="welcome-fade-up mt-7 rounded-2xl border border-[#ffffff14] bg-white/5 p-3 backdrop-blur-sm"
            style={{ animationDelay: "0.46s" }}
          >
            <p className="px-1 pb-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-[#5f7299]">
              Analysis Pipeline
            </p>
            <div className="flex items-center">
              {capabilitySteps.map((step, index) => (
                <div key={step.zh} className="flex flex-1 items-center last:flex-none">
                  <div className="group relative shrink-0">
                    <button
                      className="welcome-fade-up inline-flex cursor-default items-center rounded-full border border-[#38bdf8]/25 bg-[#0b1226]/70 px-2.5 py-1.5 text-xs font-medium text-[#cdd9f0] transition duration-200 hover:-translate-y-0.5 hover:border-[#38bdf8]/70 hover:bg-[#38bdf8]/15 hover:text-[#e6f2ff] hover:shadow-[0_6px_20px_rgba(56,189,248,0.3)]"
                      style={{ animationDelay: `${0.5 + index * 0.1}s` }}
                      type="button"
                    >
                      {step.zh}
                    </button>
                    <span className="pointer-events-none absolute bottom-full left-1/2 z-30 mb-2 w-52 -translate-x-1/2 scale-95 rounded-lg border border-[#38bdf8]/30 bg-[#0a1326]/95 px-3 py-2 text-xs leading-5 text-[#b9c8e6] opacity-0 shadow-lg backdrop-blur-md transition duration-150 group-hover:scale-100 group-hover:opacity-100">
                      {step.tip}
                    </span>
                  </div>
                  {index < capabilitySteps.length - 1 ? (
                    <span className="welcome-line-flow mx-1 h-px flex-1 rounded-full" />
                  ) : null}
                </div>
              ))}
            </div>
          </div>

          {/* 登录卡片 */}
          <form
            className="welcome-fade-up mt-8 max-w-sm rounded-2xl border border-[#38bdf8]/25 bg-[#0a1326]/70 p-5 shadow-[0_20px_60px_rgba(2,6,23,0.5)] backdrop-blur-md"
            style={{ animationDelay: "0.58s" }}
            onSubmit={handleLoginSubmit}
          >
            <label className="block">
              <span className="text-xs font-medium tracking-[0.08em] text-[#9fb2d4]">
                账号
              </span>
              <input
                autoComplete="username"
                className="mt-1.5 w-full rounded-lg border px-3 py-2.5 text-sm outline-none transition !border-[#38bdf8]/35 !bg-[#0b1226]/85 !text-[#e6eefc] placeholder:!text-[#5f7299] focus:!border-[#7dd3fc] focus:shadow-[0_0_0_3px_rgba(56,189,248,0.22)]"
                onChange={(event) => setUsername(event.target.value)}
                placeholder="请输入账号"
                value={username}
              />
            </label>

            <label className="mt-3 block">
              <span className="text-xs font-medium tracking-[0.08em] text-[#9fb2d4]">
                密码
              </span>
              <input
                autoComplete="current-password"
                className="mt-1.5 w-full rounded-lg border px-3 py-2.5 text-sm outline-none transition !border-[#38bdf8]/35 !bg-[#0b1226]/85 !text-[#e6eefc] placeholder:!text-[#5f7299] focus:!border-[#7dd3fc] focus:shadow-[0_0_0_3px_rgba(56,189,248,0.22)]"
                onChange={(event) => setPassword(event.target.value)}
                placeholder="请输入密码"
                type="password"
                value={password}
              />
            </label>

            {loginError ? (
              <p className="mt-3 rounded-lg border border-rose-400/40 bg-rose-500/15 px-3 py-2 text-xs text-rose-200">
                {loginError}
              </p>
            ) : null}

            <button
              className="group relative mt-4 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-[#22d3ee] to-[#6366f1] px-7 py-3 text-base font-semibold text-white shadow-[0_10px_40px_rgba(34,211,238,0.35)] transition duration-200 hover:-translate-y-0.5 hover:shadow-[0_18px_55px_rgba(99,102,241,0.6)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#7dd3fc] disabled:cursor-not-allowed disabled:opacity-70"
              disabled={loading}
              type="submit"
            >
              <span className="pointer-events-none absolute -inset-1 rounded-xl bg-gradient-to-r from-[#22d3ee] to-[#6366f1] opacity-0 blur-md transition duration-200 group-hover:opacity-60" />
              <span className="relative">
                {loading ? "登录中..." : "登录进入系统"}
              </span>
            </button>

            <p className="mt-3 text-xs text-[#6f84a8]">
              测试账号：admin · 测试密码：123456
            </p>
          </form>

          {/* 指标卡片（hover 展开详情） */}
          <div
            className="welcome-fade-up mt-10 grid max-w-md grid-cols-3 gap-4"
            style={{ animationDelay: "0.68s" }}
          >
            <StatCard value="8" label="个协作 Agent">
              <p className="text-xs font-semibold text-[#7dd3fc]">8 个协作 Agent</p>
              <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1.5">
                {agentSummary.map((agent) => (
                  <div key={agent.en} className="flex items-baseline gap-1.5">
                    <span className="text-[11px] font-medium text-[#e6eefc]">
                      {agent.en}
                    </span>
                    <span className="text-[10px] text-[#8aa0c6]">{agent.zh}</span>
                  </div>
                ))}
              </div>
            </StatCard>

            <StatCard value="21" label="条结构化证据">
              <p className="text-xs font-semibold text-[#7dd3fc]">证据来源结构</p>
              <div className="mt-2 space-y-2">
                {[
                  { label: "官方资料", width: "82%" },
                  { label: "评测内容", width: "64%" },
                  { label: "电商信息", width: "46%" },
                ].map((item) => (
                  <div key={item.label}>
                    <p className="text-[11px] text-[#cdd9f0]">{item.label}</p>
                    <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-white/10">
                      <div
                        className="h-full w-0 rounded-full bg-gradient-to-r from-[#22d3ee] to-[#6366f1] transition-all duration-700 ease-out group-hover:w-[var(--bar-w)]"
                        style={{ "--bar-w": item.width } as React.CSSProperties}
                      />
                    </div>
                  </div>
                ))}
              </div>
              <p className="mt-2 text-[10px] leading-4 text-[#8aa0c6]">
                用户口碑 · 多维度证据归档 · 可绑定 Claim 与 Report
              </p>
            </StatCard>

            <StatCard value="100%" label="引用追踪率">
              <p className="text-xs font-semibold text-[#7dd3fc]">引用可追溯</p>
              <div className="mt-2 flex items-center gap-1.5 text-[11px] font-medium">
                <span className="rounded-md bg-[#22d3ee]/15 px-2 py-1 text-[#67e8f9]">
                  Evidence
                </span>
                <span className="text-[#4b5e84]">→</span>
                <span className="rounded-md bg-[#818cf8]/15 px-2 py-1 text-[#a5b4fc]">
                  Claim
                </span>
                <span className="text-[#4b5e84]">→</span>
                <span className="rounded-md bg-[#c084fc]/15 px-2 py-1 text-[#d8b4fe]">
                  Report
                </span>
              </div>
              <svg className="mt-2 h-2 w-full" viewBox="0 0 100 4" preserveAspectRatio="none" aria-hidden>
                <line x1="0" y1="2" x2="100" y2="2" stroke="rgba(125,211,252,0.18)" strokeWidth="1" />
                <line className="welcome-flow" x1="0" y1="2" x2="100" y2="2" stroke="rgba(125,211,252,0.85)" strokeWidth="1.2" strokeLinecap="round" />
              </svg>
              <ul className="mt-2 space-y-1 text-[10px] leading-4 text-[#8aa0c6]">
                <li>结论可追溯</li>
                <li>降低 LLM 幻觉风险</li>
                <li>支持质量门控审查</li>
              </ul>
            </StatCard>
          </div>
        </div>

        {/* 右侧 Agent 网络 */}
        <div className="w-full max-w-md lg:flex-1" style={parallax(10)}>
          <div className="relative mx-auto aspect-square w-full max-w-[460px]">
            {/* 连接线 + 流动光点 */}
            <svg
              className="absolute inset-0 h-full w-full"
              viewBox="0 0 100 100"
              preserveAspectRatio="xMidYMid meet"
              aria-hidden
            >
              {agentNodes.map((node, index) => {
                const isActive = hoveredAgent === node.key;
                return (
                  <g key={`line-${node.key}`}>
                    <line
                      x1={CENTER}
                      y1={CENTER}
                      x2={node.x}
                      y2={node.y}
                      stroke={isActive ? "rgba(125,211,252,0.45)" : "rgba(125,211,252,0.16)"}
                      strokeWidth={isActive ? 0.7 : 0.4}
                    />
                    <line
                      className="welcome-flow"
                      x1={CENTER}
                      y1={CENTER}
                      x2={node.x}
                      y2={node.y}
                      stroke={isActive ? "rgba(165,243,252,1)" : "rgba(125,211,252,0.85)"}
                      strokeWidth={isActive ? 0.8 : 0.5}
                      strokeLinecap="round"
                    />
                    {!reducedMotion ? (
                      <circle r="0.9" fill={isActive ? "#a5f3fc" : "#7dd3fc"}>
                        <animateMotion
                          dur="2.4s"
                          repeatCount="indefinite"
                          begin={`${index * 0.3}s`}
                          path={`M${CENTER},${CENTER} L${node.x},${node.y}`}
                        />
                      </circle>
                    ) : null}
                  </g>
                );
              })}
            </svg>

            {/* 中心核心节点 */}
            <div
              className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2"
              style={{ zIndex: 2 }}
            >
              <div className="welcome-core flex h-24 w-24 flex-col items-center justify-center rounded-full border border-[#7dd3fc]/50 bg-gradient-to-br from-[#0e1b3a] to-[#111c3e] text-center sm:h-28 sm:w-28">
                <span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[#7dd3fc]">
                  Intelligence Core
                </span>
                <span className="mt-1 text-sm font-bold text-[#f1f6ff]">
                  智能分析核心
                </span>
              </div>
            </div>

            {/* 周围 Agent 节点 */}
            {agentNodes.map((node, index) => {
              const isActive = hoveredAgent === node.key;
              const tipBelow = node.y < CENTER;
              return (
                <div
                  key={node.key}
                  className="welcome-node absolute"
                  style={{
                    left: `${node.x}%`,
                    top: `${node.y}%`,
                    transform: "translate(-50%, -50%)",
                    animationDelay: `${0.3 + index * 0.12}s`,
                    zIndex: isActive ? 6 : 3,
                  }}
                  onMouseEnter={() => setHoveredAgent(node.key)}
                  onMouseLeave={() =>
                    setHoveredAgent((current) => (current === node.key ? null : current))
                  }
                >
                  <div
                    className="welcome-node-inner flex min-w-[64px] cursor-default flex-col items-center rounded-xl border border-[#38bdf8]/30 bg-[#0b1226]/85 px-3 py-2 text-center backdrop-blur-sm transition-transform duration-200"
                    style={{
                      animationDelay: `${index * 0.4}s, ${index * 0.4}s`,
                      transform: isActive ? "scale(1.14)" : "scale(1)",
                      boxShadow: isActive
                        ? "0 0 0 4px rgba(56,189,248,0.12), 0 0 28px rgba(56,189,248,0.55)"
                        : undefined,
                    }}
                  >
                    <span className="text-sm font-semibold text-[#e6eefc]">{node.zh}</span>
                    <span className="text-[9px] uppercase tracking-[0.12em] text-[#7dd3fc]">
                      {node.en}
                    </span>
                  </div>

                  {/* hover tooltip */}
                  <div
                    className={`pointer-events-none absolute left-1/2 z-20 w-44 -translate-x-1/2 rounded-lg border border-[#38bdf8]/40 bg-[#0a1326]/95 px-3 py-2 text-center shadow-[0_14px_40px_rgba(2,6,23,0.6)] backdrop-blur-md transition duration-150 ${
                      isActive ? "scale-100 opacity-100" : "scale-95 opacity-0"
                    } ${tipBelow ? "top-full mt-2" : "bottom-full mb-2"}`}
                  >
                    <p className="text-xs font-semibold text-[#f1f6ff]">
                      {node.zh}{" "}
                      <span className="text-[#7dd3fc]">{node.en}</span>
                    </p>
                    <p className="mt-1 text-[11px] leading-4 text-[#9fb2d4]">{node.role}</p>
                  </div>
                </div>
              );
            })}
          </div>

          <p className="mt-6 text-center text-xs tracking-[0.2em] text-[#5f7299]">
            MULTI-AGENT COLLABORATION NETWORK
          </p>

          {/* 系统状态面板 */}
          <div className="welcome-fade-up mx-auto mt-5 max-w-[460px] rounded-2xl border border-[#ffffff14] bg-white/5 p-4 backdrop-blur-md" style={{ animationDelay: "0.8s" }}>
            <div className="flex items-center justify-between">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#7dd3fc]">
                系统状态
              </p>
              <span className="text-[10px] font-medium text-[#34d399]">ONLINE</span>
            </div>
            <ul className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
              {systemStatus.map((item, index) => (
                <li key={item} className="flex items-center gap-2 text-xs text-[#cdd9f0]">
                  <span
                    className="welcome-status-dot h-2 w-2 shrink-0 rounded-full bg-[#34d399]"
                    style={{ animationDelay: `${index * 0.4}s` }}
                  />
                  {item}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
