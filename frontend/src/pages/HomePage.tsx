import { useEffect, useRef, useState } from "react";
import { analysisApi } from "../api/analysisApi";
import { AgentOrbit3D } from "../components/common/AgentOrbit3D";
import { ProductOrbit } from "../components/common/ProductOrbit";
import { EmptyState } from "../components/common/EmptyState";
import { LoadingState } from "../components/common/LoadingState";
import type { Industry } from "../types/analysis";

type HomeSelection = {
  selectedDomain?: string | null;
  selectedCategory?: string | null;
  selectedIndustryKey?: string | null;
};

type HomePageProps = {
  taskId?: string;
  displayTaskId?: string;
  selectedDomain?: string | null;
  selectedCategory?: string | null;
  selectedIndustryKey?: string | null;
  onNavigate: (key: string) => void;
  onSelectionChange: (selection: HomeSelection) => void;
};

type SelectOption = {
  key: string;
  label: string;
  description: string;
  available: boolean;
};

const industries: SelectOption[] = [
  {
    key: "gaming_mouse",
    label: "电竞外设",
    description: "官方型号、硬件事实、模具/点击系统、评价测评与实时价格分析",
    available: true,
  },
];

type OrbitProductDef = {
  key: string;
  label: string;
  description: string;
  available: boolean;
  glyph: string;
};

type OrbitModeDef = {
  key: string;
  label: string;
  en: string;
  tagline: string;
  items: OrbitProductDef[];
};

// 品类入口：当前只有电竞鼠标接入后端，大框内只展示可运行品类。
const orbitModes: OrbitModeDef[] = [
  {
    key: "category",
    label: "品类",
    en: "CATEGORY",
    tagline: "当前开放电竞鼠标专业分析",
    items: [
      {
        key: "gaming_mouse",
        label: "电竞鼠标",
        description:
          "当前可分析：双产品输入、官方规格 MCP、价格情报、硬件评分与专业报告。",
        available: true,
        glyph: "mouse",
      },
    ],
  },
];

const allProducts: OrbitProductDef[] = orbitModes
  .flatMap((mode) => mode.items)
  .filter((product) => product.key === "gaming_mouse");
const runnableProductKeys = new Set(["gaming_mouse"]);

const categorySelectOptions = [
  { key: "gaming_mouse", label: "电竞鼠标", status: "当前可分析" },
  { key: "gaming_keyboard", label: "电竞键盘", status: "敬请期待" },
  { key: "gaming_headset", label: "电竞耳机", status: "敬请期待" },
  { key: "gaming_monitor", label: "电竞显示器", status: "敬请期待" },
  { key: "gaming_mousepad", label: "电竞鼠标垫", status: "敬请期待" },
];

function getRunnableIndustryKey(categoryKey: string) {
  return runnableProductKeys.has(categoryKey) ? categoryKey : null;
}

function normalizeIndustries(payload: unknown): Industry[] {
  const rawItems = Array.isArray(payload)
    ? payload
    : Array.isArray((payload as { industries?: unknown })?.industries)
      ? (payload as { industries: unknown[] }).industries
      : [];

  return rawItems
    .filter((item): item is Record<string, unknown> => {
      return Boolean(item && typeof item === "object");
    })
    .map((item) => {
      const key =
        typeof item.industry_key === "string"
          ? item.industry_key
          : typeof item.key === "string"
            ? item.key
            : undefined;

      const representativeProducts =
        item.representative_products &&
        typeof item.representative_products === "object" &&
        !Array.isArray(item.representative_products)
          ? Object.entries(
              item.representative_products as Record<string, unknown>,
            ).reduce<Record<string, string[]>>((acc, [brand, products]) => {
              acc[brand] = Array.isArray(products)
                ? products.filter(
                    (product): product is string => typeof product === "string",
                  )
                : [];
              return acc;
            }, {})
          : undefined;

      return {
        industry_key: key,
        key,
        name:
          typeof item.name === "string" ? item.name : key || "未知行业",
        competitors: Array.isArray(item.competitors)
          ? item.competitors.filter(
              (competitor): competitor is string =>
                typeof competitor === "string",
            )
          : [],
        dimensions: Array.isArray(item.dimensions)
          ? item.dimensions.filter(
              (dimension): dimension is string => typeof dimension === "string",
            )
          : [],
        description:
          typeof item.description === "string" ? item.description : undefined,
        representative_products: representativeProducts,
      };
    });
}

type PillTone = "success" | "warning" | "danger" | "info" | "neutral";

const pillToneClasses: Record<PillTone, string> = {
  success: "border-[#34d399]/40 bg-[#34d399]/12 text-[#6ee7b7]",
  warning: "border-[#fbbf24]/40 bg-[#fbbf24]/12 text-[#fcd34d]",
  danger: "border-[#fb7185]/40 bg-[#fb7185]/12 text-[#fda4af]",
  info: "border-[#38bdf8]/40 bg-[#38bdf8]/12 text-[#7dd3fc]",
  neutral: "border-[#ffffff22] bg-white/5 text-[#9fb2d4]",
};

// 深色科技风的状态胶囊。
function Pill({ label, tone = "neutral" }: { label: string; tone?: PillTone }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium ${pillToneClasses[tone]}`}
    >
      {label}
    </span>
  );
}

const capabilityCards = [
  {
    key: "workflow",
    title: "电竞鼠标垂直分析",
    desc: "围绕两款电竞鼠标完成产品识别、本地硬件事实读取、规格补全和专业报告生成。",
    detail: "后端当前聚焦 gaming_mouse 场景，输出 GamingMouseFinalReportSchema，而不是泛化行业报告。",
    tone: "from-[#22d3ee]/20",
    border: "border-[#38bdf8]/30",
  },
  {
    key: "evidence",
    title: "规格与价格 MCP",
    desc: "SearchMCP 先发现官方候选，OfficialSpecMCP 抽取规格，PriceMCP 采集实时价格线索。",
    detail: "官网规格、价格、评价测评、长期可靠性等外部数据会被结构化记录；缺失时明确进入 pending_data。",
    tone: "from-[#34d399]/20",
    border: "border-[#34d399]/30",
  },
  {
    key: "quality",
    title: "硬件事实评分",
    desc: "基于重量、传感器、DPI、回报率、连接、续航、微动和板载内存生成本地事实基线。",
    detail: "握法、手型、游戏类型、口碑和实时性价比不强行下结论；待 MCP 补齐前只展示保守评分和风险提示。",
    tone: "from-[#818cf8]/20",
    border: "border-[#818cf8]/30",
  },
];

const capabilityVisualThemes = [
  {
    accent: "cyan",
    chips: ["产品识别", "硬件读取", "报告生成"],
    status: "数据输入中",
    visual: "mouse",
  },
  {
    accent: "violet",
    chips: ["SearchMCP", "SpecMCP", "PriceMCP"],
    status: "数据同步中",
    visual: "matrix",
  },
  {
    accent: "gold",
    chips: ["重量", "DPI", "回报率"],
    status: "最终校验中",
    visual: "score",
  },
];

const analysisFlowSteps = [
  {
    key: "mission-brief",
    routeKey: "overview",
    code: "01",
    label: "战情输入",
    subtitle: "MISSION BRIEF",
    layer: "Strategy Layer",
    metric: "目标 / 用户 / 场景",
    desc: "确认 gaming_mouse 垂直场景，锁定两款电竞鼠标、目标用户和分析任务边界。",
    input: "双产品 + 目标用户",
    process: "ResearchAgent 规划官方规格、价格、评价和硬件事实需求",
    output: "data_requirements",
    positionClass: "mission-node-1",
  },
  {
    key: "entity-resolution",
    routeKey: "product-compare",
    code: "02",
    label: "产品识别",
    subtitle: "ENTITY RESOLUTION",
    layer: "Data Layer",
    metric: "型号 / 别名 / 置信度",
    desc: "CollectorAgent 匹配本地产品库，处理别名、未知型号和低置信候选。",
    input: "产品名称或产品 ID",
    process: "本地 facts 命中，未命中则进入 SearchMCP 候选发现",
    output: "resolved_products",
    positionClass: "mission-node-2",
  },
  {
    key: "search-mcp",
    routeKey: "workflow",
    code: "03",
    label: "候选搜索",
    subtitle: "SEARCH MCP",
    layer: "MCP Layer",
    metric: "官网候选 / 相关性",
    desc: "SearchMCP 发现官方页面和外部候选，但不会直接把网页内容写成硬件事实。",
    input: "未确认型号",
    process: "搜索官方候选、过滤非电竞鼠标和低相关结果",
    output: "official_candidates",
    positionClass: "mission-node-3",
  },
  {
    key: "official-spec",
    routeKey: "workflow",
    code: "04",
    label: "官网规格",
    subtitle: "OFFICIAL SPEC",
    layer: "MCP Layer",
    metric: "重量 / DPI / 回报率",
    desc: "OfficialSpecMCP 从官网候选抽取结构化规格，补全稳定硬件事实。",
    input: "官方 URL 候选",
    process: "抽取重量、传感器、DPI、连接、续航、微动等字段",
    output: "official_spec_records",
    positionClass: "mission-node-4",
  },
  {
    key: "price-intel",
    routeKey: "workflow",
    code: "05",
    label: "价格情报",
    subtitle: "PRICE INTEL",
    layer: "Market Layer",
    metric: "实时价 / 可信度",
    desc: "PriceMCP 采集实时价格线索，保留官方价阻塞、低可信来源和地区可买性提示。",
    input: "产品与价格目标",
    process: "优先官方价，再采集零售和搜索候选，并计算 price_status",
    output: "price_status",
    positionClass: "mission-node-5",
  },
  {
    key: "hardware-score",
    routeKey: "workflow",
    code: "06",
    label: "硬件评分",
    subtitle: "SCORE BASELINE",
    layer: "Analysis Layer",
    metric: "硬件事实基线",
    desc: "AnalysisAgent 基于稳定硬件事实生成本地评分，避免把口碑和体验缺口伪装成结论。",
    input: "product_facts + evidence",
    process: "计算硬件、驱动支持、点击系统和保守 overall 分",
    output: "product_scores",
    positionClass: "mission-node-6",
  },
  {
    key: "trust-gate",
    routeKey: "workflow",
    code: "07",
    label: "证据校验",
    subtitle: "TRUST GATE",
    layer: "Trust Layer",
    metric: "Claim / Evidence",
    desc: "VerificationAgent 检查每条 claim 是否被 evidence 支撑，unsupported claims 不进入最终报告。",
    input: "claims + evidence_ids",
    process: "生成 faithfulness_report、risk_flags 和待披露数据缺口",
    output: "faithfulness_report",
    positionClass: "mission-node-7",
  },
  {
    key: "decision-report",
    routeKey: "report",
    code: "08",
    label: "决策报告",
    subtitle: "DECISION REPORT",
    layer: "Business Layer",
    metric: "可信建议 / 风险边界",
    desc: "QualityAgent 做质量门控，ReportAgent 输出电竞鼠标专业商业报告。",
    input: "quality_result",
    process: "approved / limited / partial_report 分级交付",
    output: "GamingMouseFinalReport",
    positionClass: "mission-node-8",
  },
];

const missionRadarMetrics = [
  {
    label: "Data Foundation",
    value: "Local Facts + MCP",
    desc: "本地硬件事实与外部候选分层采集",
  },
  {
    label: "Trust Control",
    value: "Evidence-bound Claims",
    desc: "结论绑定 evidence，unsupported 自动剔除",
  },
  {
    label: "Business Output",
    value: "Decision Report",
    desc: "价格、风险、pending 数据一起披露",
  },
];

const missionCardLayouts = [
  { group: 0, x: -260, y: 34, accent: "cyan" },
  { group: 0, x: 0, y: -52, accent: "cyan" },
  { group: 0, x: 260, y: 34, accent: "cyan" },
  { group: 1, x: -170, y: -18, accent: "purple" },
  { group: 1, x: 170, y: 46, accent: "purple" },
  { group: 2, x: -265, y: 42, accent: "gold" },
  { group: 2, x: 0, y: -58, accent: "gold" },
  { group: 2, x: 265, y: 42, accent: "gold" },
];

const missionMetricThresholds = [0.08, 0.62, 0.78];

const HOME_CAPABILITIES_EXPANDED_KEY = "homeCapabilitiesExpanded";

function getStoredCapabilitiesExpanded() {
  if (typeof window === "undefined") {
    return true;
  }

  return window.sessionStorage.getItem(HOME_CAPABILITIES_EXPANDED_KEY) !== "false";
}

export function HomePage({
  taskId,
  displayTaskId,
  selectedDomain,
  selectedCategory,
  selectedIndustryKey,
  onNavigate,
  onSelectionChange,
}: HomePageProps) {
  const [backendIndustries, setBackendIndustries] = useState<Industry[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [taskStatus, setTaskStatus] = useState<string | null>(null);
  const [capabilitiesExpanded, setCapabilitiesExpanded] = useState(
    getStoredCapabilitiesExpanded,
  );
  const [missionScrollProgress, setMissionScrollProgress] = useState(0);
  const [selectedCategoryPreview, setSelectedCategoryPreview] =
    useState("gaming_mouse");
  const missionMapRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let ignore = false;

    analysisApi
      .getIndustries()
      .then((payload) => {
        if (!ignore) {
          setBackendIndustries(normalizeIndustries(payload));
          setError(null);
        }
      })
      .catch((err: Error) => {
        if (!ignore) {
          setError(err.message);
        }
      })
      .finally(() => {
        if (!ignore) {
          setIsLoading(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.sessionStorage.setItem(
        HOME_CAPABILITIES_EXPANDED_KEY,
        String(capabilitiesExpanded),
      );
    }
  }, [capabilitiesExpanded]);

  useEffect(() => {
    let frameId: number | null = null;
    let scrollTarget: HTMLElement | Window = window;

    const getScrollTarget = (element: HTMLElement): HTMLElement | Window => {
      let parent = element.parentElement;

      while (parent) {
        const overflowY = window.getComputedStyle(parent).overflowY;
        const canScroll =
          (overflowY === "auto" || overflowY === "scroll" || overflowY === "overlay") &&
          parent.scrollHeight > parent.clientHeight;

        if (canScroll) {
          return parent;
        }

        parent = parent.parentElement;
      }

      return window;
    };

    const updateProgress = () => {
      const element = missionMapRef.current;
      if (!element) {
        return;
      }

      const rect = element.getBoundingClientRect();
      scrollTarget = getScrollTarget(element);
      const isWindowTarget = scrollTarget === window;
      const viewportHeight = isWindowTarget
        ? window.innerHeight || 1
        : (scrollTarget as HTMLElement).clientHeight || 1;
      const targetTop = isWindowTarget
        ? 0
        : (scrollTarget as HTMLElement).getBoundingClientRect().top;
      const relativeTop = rect.top - targetTop;
      const travel = Math.max(rect.height - viewportHeight * 0.52, 1);
      const rawProgress = (viewportHeight * 0.16 - relativeTop) / travel;
      const nextProgress = Math.min(Math.max(rawProgress, 0), 1);

      setMissionScrollProgress((current) =>
        Math.abs(current - nextProgress) > 0.008 ? nextProgress : current,
      );
    };

    const scheduleProgressUpdate = () => {
      if (frameId !== null) {
        return;
      }

      frameId = window.requestAnimationFrame(() => {
        frameId = null;
        updateProgress();
      });
    };

    updateProgress();
    const initialElement = missionMapRef.current;
    scrollTarget = initialElement ? getScrollTarget(initialElement) : window;
    scrollTarget.addEventListener("scroll", scheduleProgressUpdate, {
      passive: true,
    });
    window.addEventListener("resize", scheduleProgressUpdate);

    return () => {
      if (frameId !== null) {
        window.cancelAnimationFrame(frameId);
      }
      scrollTarget.removeEventListener("scroll", scheduleProgressUpdate);
      window.removeEventListener("resize", scheduleProgressUpdate);
    };
  }, []);

  // 轻量读取当前任务状态，用于驱动协作动画的待命/分析中/完成态（不影响主流程）。
  useEffect(() => {
    if (!taskId) {
      setTaskStatus(null);
      return;
    }

    const activeTaskId = taskId;
    let cancelled = false;
    let timerId: number | undefined;

    async function pollStatus() {
      try {
        const result = await analysisApi.getStatus(activeTaskId);
        if (cancelled) {
          return;
        }
        const status = (result?.status ?? "").toLowerCase();
        setTaskStatus(status);
        if ((status === "completed" || status === "failed") && timerId) {
          window.clearInterval(timerId);
          timerId = undefined;
        }
      } catch {
        if (!cancelled) {
          setTaskStatus(null);
        }
      }
    }

    pollStatus();
    timerId = window.setInterval(pollStatus, 3000);

    return () => {
      cancelled = true;
      if (timerId) {
        window.clearInterval(timerId);
      }
    };
  }, [taskId]);

  const orbitPhase: "standby" | "running" | "completed" = !taskId
    ? "standby"
    : taskStatus === "completed"
      ? "completed"
      : "running";

  const industryValue = selectedDomain ?? "gaming_mouse";
  const categoryValue = selectedCategory ?? "gaming_mouse";
  const selectedIndustry =
    industries.find((industry) => industry.key === industryValue) ?? industries[0];
  const selectedCategoryOption =
    allProducts.find((product) => product.key === categoryValue) ?? allProducts[0];
  const selectedMode =
    orbitModes.find((mode) =>
      mode.items.some((item) => item.key === categoryValue),
    ) ?? orbitModes[0];
  const selectedBackendIndustry = backendIndustries.find((industry) => {
    return (industry.industry_key || industry.key) === selectedCategoryOption.key;
  });
  const hasSelectedBackendIndustry = Boolean(selectedBackendIndustry);
  const connectedRunnableCount = backendIndustries.filter((industry) =>
    getRunnableIndustryKey(industry.industry_key || industry.key || ""),
  ).length;
  const canEnterConfig =
    selectedIndustry.key === "gaming_mouse" &&
    selectedCategoryOption.available &&
    Boolean(getRunnableIndustryKey(selectedCategoryOption.key)) &&
    hasSelectedBackendIndustry;

  const missionSceneIndex =
    missionScrollProgress < 0.2 ? -1 : missionScrollProgress < 0.5 ? 0 : missionScrollProgress < 0.73 ? 1 : 2;
  const missionSceneProgress =
    missionSceneIndex < 0
      ? 0
      : missionSceneIndex === 0
        ? (missionScrollProgress - 0.2) / 0.3
        : missionSceneIndex === 1
          ? (missionScrollProgress - 0.5) / 0.23
          : (missionScrollProgress - 0.73) / 0.27;
  const activeFlowIndex =
    missionSceneIndex < 0
      ? 0
      : missionSceneIndex === 0
        ? Math.min(2, Math.max(0, Math.round(missionSceneProgress * 2)))
        : missionSceneIndex === 1
          ? 3 + Math.min(1, Math.max(0, Math.round(missionSceneProgress)))
          : 5 + Math.min(2, Math.max(0, Math.round(missionSceneProgress * 2)));
  const missionCompleted = Boolean(taskId && taskStatus === "completed");
  const missionCoreStatus = !taskId
    ? "READY"
    : missionCompleted
      ? "COMPLETE"
      : "RUNNING";
  const missionHubVisibility = Math.max(0, 1 - missionScrollProgress / 0.18);
  const missionDepthLabel = `${Math.round(missionScrollProgress * 100)}% DEPTH`;
  const selectedCategoryPreviewOption =
    categorySelectOptions.find((option) => option.key === selectedCategoryPreview) ??
    categorySelectOptions[0];

  function handleCategoryChange(nextCategory: string) {
    onSelectionChange({
      selectedDomain: "gaming_mouse",
      selectedCategory: nextCategory,
      selectedIndustryKey: getRunnableIndustryKey(nextCategory),
    });
  }

  function handleEnterConfig(nextCategory = selectedCategoryOption.key) {
    const nextIndustryKey = getRunnableIndustryKey(nextCategory);
    if (!nextIndustryKey) {
      return;
    }

    onSelectionChange({
      selectedDomain: "gaming_mouse",
      selectedCategory: nextCategory,
      selectedIndustryKey: nextIndustryKey,
    });
    onNavigate("product-compare");
  }

  return (
    <section className="mx-auto max-w-[1280px]">
      <div
        className="relative overflow-visible rounded-3xl border border-[#1d2b4a] p-5 shadow-[0_24px_80px_rgba(2,6,23,0.45)] md:p-7"
        style={{
          background:
            "radial-gradient(900px 500px at 14% 8%, rgba(37,99,235,0.16), transparent 55%)," +
            "radial-gradient(800px 600px at 92% 92%, rgba(129,140,248,0.14), transparent 55%)," +
            "linear-gradient(135deg, #070d1c 0%, #0b1426 55%, #080c18 100%)",
        }}
      >
        {/* 动态网格 + 光斑 */}
        <div
          className="welcome-grid pointer-events-none absolute inset-[-40px] opacity-50"
          aria-hidden
        />
        <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
          <div className="welcome-blob absolute -left-16 -top-12 h-64 w-64 rounded-full bg-[#22d3ee]/15 blur-3xl" />
          <div
            className="welcome-blob absolute right-[-4rem] top-1/3 h-72 w-72 rounded-full bg-[#818cf8]/15 blur-3xl"
            style={{ animationDelay: "3s" }}
          />
        </div>
        <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-[#38bdf8]/60 to-transparent" />

        <div className="relative space-y-6">
          {/* Hero */}
          <div className="grid items-center gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
            <div>
              <p className="text-sm font-semibold tracking-[0.04em] text-[#7dd3fc]">
                Multi-Agent Competitive Intelligence
              </p>
              <h2 className="mt-3 text-4xl font-bold leading-tight text-[#f1f6ff] md:text-5xl">
                AI 竞品情报中枢
              </h2>
              <p className="mt-4 max-w-xl text-sm leading-7 text-[#9fb2d4] md:text-base">
                多 Agent 协同完成数据规划、证据结构化、事实校验、质量审查与专业报告生成。
              </p>
              <p className="mt-2 max-w-xl text-sm leading-6 text-[#7e91b5]">
                面向产品团队的竞品分析系统，从公开资料中抽取证据，生成可追溯的策略报告。
              </p>

              <div className="mt-7 flex flex-wrap gap-2">
                <Pill
                  label={isLoading ? "正在读取分析场景" : "分析场景已连接"}
                  tone={isLoading ? "warning" : error ? "danger" : "success"}
                />
                <Pill
                  label={
                    connectedRunnableCount > 0
                      ? `${connectedRunnableCount} 个电竞品类可分析`
                      : "电竞分析服务未就绪"
                  }
                  tone={connectedRunnableCount > 0 ? "success" : "warning"}
                />
                <Pill
                  label={displayTaskId ? `当前任务：${displayTaskId}` : "暂无任务"}
                  tone={taskId ? "info" : "neutral"}
                />
              </div>
            </div>

            {/* 伪 3D Agent 协作动画 */}
            <div className="min-w-0">
              <AgentOrbit3D phase={orbitPhase} />
              <p className="mt-2 text-center text-xs tracking-[0.2em] text-[#5f7299]">
                MULTI-AGENT COLLABORATION
              </p>
            </div>
          </div>

          <section className="rounded-2xl border border-[#ffffff14] bg-[#0a1326]/40 p-5 backdrop-blur-sm md:p-6">
            <div className="mb-5 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <p className="text-sm font-medium text-[#7dd3fc]">
                  Capability Highlights
                </p>
                <h3 className="mt-2 text-2xl font-semibold text-[#f1f6ff]">
                  系统核心能力
                </h3>
                <p className="mt-2 max-w-3xl text-sm leading-6 text-[#8aa0c6]">
                  对齐后端最新电竞鼠标链路：本地硬件事实、官网规格 MCP、实时价格线索、保守评分与 pending 数据披露。
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2 sm:justify-end">
                <Pill label="核心能力展示" tone="info" />
                <button
                  aria-controls="home-capability-cards"
                  aria-expanded={capabilitiesExpanded}
                  className="capability-unfurl-button"
                  onClick={() =>
                    setCapabilitiesExpanded((isExpanded) => !isExpanded)
                  }
                  type="button"
                >
                  {capabilitiesExpanded ? "收起能力展示 ↑" : "展开能力展示 ↓"}
                </button>
              </div>
            </div>

            {!capabilitiesExpanded ? (
              <div className="capability-cube-idle">
                <div className="capability-cube-core" aria-hidden>
                  {Array.from({ length: 8 }, (_, index) => (
                    <span
                      className={`capability-cube-dot capability-cube-dot-${index + 1}`}
                      key={index}
                    />
                  ))}
                  <span className="capability-cube-line capability-cube-line-a" />
                  <span className="capability-cube-line capability-cube-line-b" />
                  <span className="capability-cube-line capability-cube-line-c" />
                </div>
                <div className="capability-cube-copy">
                  <span className="capability-cube-kicker">
                    Holographic Capability Cube
                  </span>
                  <strong>三面能力魔方待展开</strong>
                  <span>
                    电竞鼠标垂直分析 / 规格与价格 MCP / 硬件事实评分
                  </span>
                </div>
              </div>
            ) : null}

            {!capabilitiesExpanded ? (
              <div className="hidden">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                  <p className="text-sm font-semibold text-[#f1f6ff]">
                    系统核心能力
                  </p>
                  <p className="text-sm leading-6 text-[#9fb2d4]">
                    电竞鼠标垂直分析 · 规格与价格 MCP · 硬件事实评分
                  </p>
                </div>
              </div>
            ) : null}

            <div
              className={`grid transition-all duration-300 ease-out ${
                capabilitiesExpanded
                  ? "mt-5 grid-rows-[1fr] opacity-100"
                  : "mt-0 grid-rows-[0fr] opacity-0"
              }`}
              id="home-capability-cards"
            >
              <div className="overflow-visible">
                <div
                  className={`capability-unfurl-panel ${
                    capabilitiesExpanded ? "capability-unfurl-open" : ""
                  }`}
                >
                  {capabilityCards.map((card, index) => {
                    const visual =
                      capabilityVisualThemes[index] ?? capabilityVisualThemes[0];

                    return (
                      <button
                        key={card.key}
                        className={`capability-holo-card capability-holo-card-${index + 1} capability-${visual.accent}`}
                        onClick={() => onNavigate(card.key)}
                        type="button"
                      >
                        <span className="capability-holo-visual" aria-hidden>
                          {visual.visual === "mouse" ? (
                            <span className="capability-mouse-projection">
                              <span className="capability-mouse-shell" />
                              <span className="capability-mouse-part capability-mouse-part-sensor" />
                              <span className="capability-mouse-part capability-mouse-part-switch" />
                              <span className="capability-mouse-part capability-mouse-part-wheel" />
                              <span className="capability-mouse-scan" />
                            </span>
                          ) : null}
                          {visual.visual === "matrix" ? (
                            <span className="capability-matrix-projection">
                              <span className="capability-matrix-sweep" />
                              <span className="capability-price-line" />
                              <span className="capability-matrix-bars" />
                            </span>
                          ) : null}
                          {visual.visual === "score" ? (
                            <span className="capability-score-projection">
                              <span className="capability-score-beam capability-score-beam-1" />
                              <span className="capability-score-beam capability-score-beam-2" />
                              <span className="capability-score-beam capability-score-beam-3" />
                              <span className="capability-score-ring" />
                              <span className="capability-score-number">87</span>
                            </span>
                          ) : null}
                        </span>

                        <span className="capability-holo-topline">
                          <span>Capability</span>
                          <span className="capability-holo-status">
                            {visual.status}
                          </span>
                        </span>
                        <span className="capability-holo-title">{card.title}</span>
                        <span className="capability-holo-desc">{card.desc}</span>
                        <span className="capability-holo-chips">
                          {visual.chips.map((chip) => (
                            <span key={chip}>{chip}</span>
                          ))}
                        </span>
                        <span className="capability-holo-detail">{card.detail}</span>
                        <span className="capability-holo-link">查看详情 →</span>
                      </button>
                    );
                  })}
                </div>
                <div className="hidden">
                  {capabilityCards.map((card) => (
                    <button
                      key={card.key}
                      className={`group overflow-hidden rounded-2xl border bg-gradient-to-b ${card.tone} to-transparent ${card.border} bg-[#0b1426]/60 p-5 text-left transition duration-200 hover:-translate-y-1 hover:shadow-[0_16px_44px_rgba(56,189,248,0.18)]`}
                      onClick={() => onNavigate(card.key)}
                      type="button"
                    >
                      <p className="text-xs font-medium uppercase tracking-[0.18em] text-[#6f84a8]">
                        Capability
                      </p>
                      <h3 className="mt-2 text-base font-semibold text-[#f1f6ff]">
                        {card.title}
                      </h3>
                      <p className="mt-2 text-sm leading-6 text-[#9fb2d4]">
                        {card.desc}
                      </p>
                      <div className="grid grid-rows-[0fr] transition-all duration-300 group-hover:grid-rows-[1fr]">
                        <p className="overflow-hidden text-sm leading-6 text-[#7dd3fc]">
                          <span className="mt-2 block">{card.detail}</span>
                        </p>
                      </div>
                      <span className="mt-3 inline-block text-sm font-medium text-[#7dd3fc] transition group-hover:translate-x-1">
                        查看详情 →
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="mt-7 border-t border-[#ffffff14] pt-6">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
                <div>
                  <p className="text-sm font-medium text-[#7dd3fc]">
                    Intelligence Mission Map
                  </p>
                  <h3 className="mt-2 text-xl font-semibold text-[#f1f6ff]">
                    分析作战雷达
                  </h3>
                  <p className="mt-2 max-w-3xl text-sm leading-6 text-[#8aa0c6]">
                    从战情输入、MCP 采集、硬件评分到证据校验和商业报告，完整呈现后端真实竞品情报链路。
                  </p>
                </div>
                <div className="flex flex-wrap gap-2 sm:justify-end">
                  <Pill label="8 节点情报链路" tone="info" />
                  <Pill label="MCP + Evidence + Quality" tone="success" />
                </div>
              </div>

              <div className="mission-scroll-shell mt-5" ref={missionMapRef}>
                <div className="mission-stream-sticky">
                  <div className="mission-stream-status">
                    <div>
                      <p className="mission-stream-eyebrow">
                        CYBER-DIGITAL STREAM
                      </p>
                      <p className="mission-stream-title">
                        Intelligence Mission Map / 分析作战雷达
                      </p>
                    </div>
                    <div className="mission-stream-pills">
                      <span>8 节点情报链路</span>
                      <span>MCP + Evidence + Quality</span>
                      <span>{missionDepthLabel}</span>
                    </div>
                  </div>

                  <div className="mission-stream-stage">
                    <div className="mission-stream-space" aria-hidden>
                      <span className="mission-stream-grid" />
                      <span className="mission-stream-aurora mission-stream-aurora-left" />
                      <span className="mission-stream-aurora mission-stream-aurora-right" />
                      <span className="mission-stream-light mission-stream-light-a" />
                      <span className="mission-stream-light mission-stream-light-b" />
                      <span className="mission-stream-pulse mission-stream-pulse-a" />
                      <span className="mission-stream-pulse mission-stream-pulse-b" />
                    </div>

                    <div
                      className="mission-hub-tower"
                      style={{
                        opacity: missionHubVisibility,
                        transform: `translate3d(-50%, ${-missionScrollProgress * 220}px, ${
                          120 - missionScrollProgress * 620
                        }px) rotateX(${12 + missionScrollProgress * 28}deg) scale(${
                          1 - missionScrollProgress * 0.24
                        })`,
                      }}
                    >
                      <span className="mission-hub-ring" />
                      <span className="mission-hub-label">Intelligence Core</span>
                      <span className="mission-hub-name">情报中枢</span>
                      <span className="mission-hub-state">{missionCoreStatus}</span>
                      <span className="mission-hub-agents">7 Agents / 3 MCP</span>
                      <span className="mission-hub-task">
                        {displayTaskId ?? "等待任务"}
                      </span>
                    </div>

                    <div className="mission-holo-axis">
                      {analysisFlowSteps.map((step, index) => {
                        const layout = missionCardLayouts[index];
                        const groupDelta = layout.group - missionSceneIndex;
                        const isBeforeStream = missionSceneIndex < 0;
                        const isGroupFocused = groupDelta === 0 && !isBeforeStream;
                        const isActive = index === activeFlowIndex && !isBeforeStream;
                        const isComplete = missionCompleted || index < activeFlowIndex;
                        const distance = Math.abs(groupDelta);
                        const output =
                          step.routeKey === "product-compare"
                            ? displayTaskId ?? "待创建"
                            : step.output;
                        const translateY = isBeforeStream
                          ? 210 + index * 8
                          : layout.y + groupDelta * 260;
                        const translateZ = isBeforeStream
                          ? -420 - index * 18
                          : isGroupFocused
                            ? isActive
                              ? 148
                              : 82
                            : -260 - distance * 95;
                        const scale = isBeforeStream
                          ? 0.44
                          : isGroupFocused
                            ? isActive
                              ? 1.08
                              : 0.92
                            : 0.58;
                        const opacity = isBeforeStream
                          ? 0.16
                          : isGroupFocused
                            ? 1
                            : distance === 1
                              ? 0.22
                              : 0.07;

                        return (
                          <button
                            className={`mission-holo-card mission-holo-${layout.accent} ${
                              isActive
                                ? "mission-holo-active"
                                : isComplete
                                  ? "mission-holo-complete"
                                  : "mission-holo-idle"
                            }`}
                            key={step.key}
                            onClick={() => onNavigate(step.routeKey)}
                            style={{
                              opacity,
                              transform: `translate3d(${layout.x}px, ${translateY}px, ${translateZ}px) rotateX(${
                                isGroupFocused ? -9 : 18 * groupDelta
                              }deg) rotateY(${
                                layout.x > 0 ? -13 : layout.x < 0 ? 13 : 0
                              }deg) scale(${scale})`,
                              zIndex: isGroupFocused
                                ? 60 - Math.abs(index - activeFlowIndex)
                                : 10 - distance,
                            }}
                            title={`${step.label}: ${step.desc}`}
                            type="button"
                          >
                            <span className="mission-holo-scan" />
                            <span className="mission-holo-topline">
                              <span className="mission-holo-code">{step.code}</span>
                              <span className="mission-holo-state">
                                {isActive ? "FOCUS" : isComplete ? "COMPLETE" : "STANDBY"}
                              </span>
                            </span>
                            <span className="mission-holo-title">{step.label}</span>
                            <span className="mission-holo-subtitle">
                              {step.subtitle}
                            </span>
                            <span className="mission-holo-layer">{step.layer}</span>
                            <span className="mission-holo-metric">{step.metric}</span>
                            <span className="mission-holo-detail">
                              <span>
                                <strong>Input</strong>
                                {step.input}
                              </span>
                              <span>
                                <strong>Process</strong>
                                {step.process}
                              </span>
                              <span>
                                <strong>Output</strong>
                                {output}
                              </span>
                            </span>
                            <span className="mission-holo-check">✓</span>
                          </button>
                        );
                      })}
                    </div>

                    <div className="mission-data-links" aria-hidden>
                      <span className="mission-data-link mission-data-link-a" />
                      <span className="mission-data-link mission-data-link-b" />
                      <span className="mission-data-link mission-data-link-c" />
                    </div>
                  </div>

                  <div className="mission-output-bar">
                    {missionRadarMetrics.map((metric, index) => {
                      const isMetricActive =
                        missionScrollProgress >= missionMetricThresholds[index];

                      return (
                        <div
                          className={`mission-output-light ${
                            isMetricActive ? "mission-output-active" : ""
                          }`}
                          key={metric.label}
                        >
                          <span className="mission-output-orb" />
                          <span>
                            <span className="mission-output-label">
                              {metric.label}
                            </span>
                            <span className="mission-output-value">
                              {metric.value}
                            </span>
                            <span className="mission-output-desc">
                              {metric.desc}
                            </span>
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>

              <div className="hidden">
                {missionRadarMetrics.map((metric) => (
                  <div
                    className="rounded-2xl border border-[#38bdf8]/18 bg-[#07111f]/72 px-4 py-3 shadow-[inset_0_1px_0_rgba(125,211,252,0.08)]"
                    key={metric.label}
                  >
                    <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[#7dd3fc]">
                      {metric.label}
                    </p>
                    <p className="mt-1 text-sm font-semibold text-[#f8fbff]">
                      {metric.value}
                    </p>
                    <p className="mt-1 text-xs leading-5 text-[#8aa0c6]">
                      {metric.desc}
                    </p>
                  </div>
                ))}
              </div>

              <div className="hidden">
                <div className="mission-map relative min-h-[660px] rounded-3xl border border-[#38bdf8]/18 bg-[#07111f]/70 px-4 py-5 shadow-[inset_0_1px_0_rgba(125,211,252,0.08),0_22px_70px_rgba(2,6,23,0.34)] md:px-6 md:py-7">
                  <div className="mission-map-surface pointer-events-none absolute inset-0 overflow-hidden rounded-3xl">
                    <div className="welcome-grid absolute inset-0 opacity-25" />
                    <div className="mission-radar-rings" />
                    <div className="mission-orbit mission-orbit-a" />
                    <div className="mission-orbit mission-orbit-b" />
                    <div className="mission-scan-line" />
                    <div className="mission-glow mission-glow-left" />
                    <div className="mission-glow mission-glow-right" />
                  </div>

                  <div className="mission-core">
                    <span className="mission-core-pulse" />
                    <span className="text-[10px] font-semibold uppercase tracking-[0.26em] text-[#7dd3fc]">
                      Intelligence Core
                    </span>
                    <span className="mt-1 text-lg font-semibold text-[#f8fbff]">
                      情报中枢
                    </span>
                    <span className="mt-2 rounded-full border border-[#38bdf8]/30 bg-[#38bdf8]/10 px-3 py-1 text-[11px] font-semibold text-[#bae6fd]">
                      {missionCoreStatus}
                    </span>
                    <span className="mt-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-[#34d399]">
                      7 Agents / 3 MCP
                    </span>
                    <span className="mt-2 max-w-[150px] truncate text-xs text-[#8aa0c6]">
                      {displayTaskId ?? "等待任务"}
                    </span>
                  </div>

                  <div className="mission-node-layer">
                    {analysisFlowSteps.map((step, index) => {
                      const isPreviewActive = index === activeFlowIndex;
                      const isActive = isPreviewActive;
                      const hasPassedInPreview = index < activeFlowIndex;
                      const isComplete =
                        missionCompleted || hasPassedInPreview;
                      const output =
                        step.routeKey === "product-compare"
                          ? displayTaskId ?? "待创建"
                          : step.output;

                      return (
                        <button
                          className={`mission-chip group ${step.positionClass} ${
                            isActive
                              ? "mission-chip-active"
                              : isComplete
                                ? "mission-chip-complete"
                                : "mission-chip-idle"
                          }`}
                          key={step.key}
                          onClick={() => onNavigate(step.routeKey)}
                          title={`${step.label}：${step.desc}`}
                          type="button"
                        >
                          <span className="mission-chip-topline">
                            <span className="mission-chip-code">{step.code}</span>
                            <span className="mission-chip-state">
                              {isActive ? "扫描中" : isComplete ? "已完成" : "待命"}
                            </span>
                          </span>
                          <span className="mission-chip-title">{step.label}</span>
                          <span className="mission-chip-subtitle">
                            {step.subtitle}
                          </span>
                          <span className="mission-chip-layer">{step.layer}</span>
                          <span className="mission-chip-metric">{step.metric}</span>
                          {(isComplete || isActive) && !isActive ? (
                            <span className="mission-chip-check">✓</span>
                          ) : null}
                          {isActive ? <span className="mission-chip-beam" /> : null}

                          <span className="mission-chip-detail">
                            <span>
                              <strong>Input</strong>
                              {step.input}
                            </span>
                            <span>
                              <strong>Process</strong>
                              {step.process}
                            </span>
                            <span>
                              <strong>Output</strong>
                              {output}
                            </span>
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>
            </div>
          </section>

          {isLoading ? <LoadingState label="正在加载分析场景..." /> : null}

          {!isLoading && error ? (
            <EmptyState
              title="分析场景加载失败"
              description={error}
              action={<Pill label="请确认系统服务已启动" tone="danger" />}
            />
          ) : null}

          {!isLoading && !error ? (
            <section className="rounded-2xl border border-[#ffffff14] bg-[#0a1326]/55 p-5 backdrop-blur-sm md:p-6">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <p className="text-sm font-medium text-[#7dd3fc]">分析场景选择</p>
                  <h3 className="mt-2 text-2xl font-semibold text-[#f1f6ff]">
                    品类选择
                  </h3>
                  <p className="mt-2 max-w-3xl text-sm leading-6 text-[#8aa0c6]">
                    当前正式开放电竞鼠标专业分析，其他外设品类暂未接入后端。
                  </p>
                  <div className="category-select-row mt-4">
                    <label
                      className="category-select-label"
                      htmlFor="category-preview-select"
                    >
                      选择品类
                    </label>
                    <span className="category-select-field">
                      <select
                        className="category-select-control"
                        id="category-preview-select"
                        onChange={(event) =>
                          setSelectedCategoryPreview(event.target.value)
                        }
                        value={selectedCategoryPreview}
                      >
                        {categorySelectOptions.map((option) => (
                          <option key={option.key} value={option.key}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                      <span className="category-select-arrow" aria-hidden>
                        ↓
                      </span>
                    </span>
                    <span
                      className={`category-select-status ${
                        selectedCategoryPreviewOption.key === "gaming_mouse"
                          ? "category-select-status-active"
                          : "category-select-status-planned"
                      }`}
                    >
                      {selectedCategoryPreviewOption.status}
                    </span>
                  </div>
                </div>
                <Pill
                  label={canEnterConfig ? "1 个品类已接入" : "敬请期待"}
                  tone={canEnterConfig ? "success" : "warning"}
                />
              </div>

              {/* 环形悬浮品类选择器：大框只展示后端已接入的电竞鼠标。 */}
              <div className="category-mesh-frame mt-6">
                <ProductOrbit
                  activeKey={categoryValue}
                  canEnter={canEnterConfig}
                  modes={orbitModes}
                  onEnter={handleEnterConfig}
                  onSelect={handleCategoryChange}
                />
              </div>

            </section>
          ) : null}
        </div>
      </div>
    </section>
  );
}
