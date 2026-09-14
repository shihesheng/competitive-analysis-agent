import { useEffect, useMemo, useState, type ReactNode } from "react";
import { analysisApi } from "../api/analysisApi";
import { EmptyState } from "../components/common/EmptyState";
import { LoadingState } from "../components/common/LoadingState";
import { StatusBadge } from "../components/common/StatusBadge";
import type { AgentSidebarItem } from "../components/layout/Sidebar";
import type {
  AgentTrace,
  AnalysisStatus,
  AnalysisAiInterpretation,
  ArtifactsSummary,
  Claim,
  ErrorLogItem,
  ExternalProductCandidate,
  FinalReport,
  OfficialSpecRecord,
  QualityResult,
  ReviewIntelRecord,
  ReviewTicket,
  SearchMcpResult,
  HumanFeedbackRecord,
  SwotPoint,
} from "../types/analysis";

type WorkflowPageProps = {
  taskId?: string;
  displayTaskId?: string;
  agentDetailName?: string | null;
  onAgentOpen: (agentName: string) => void;
  onAgentDetailClose: () => void;
  selectedAgent: string;
  onSelectedAgentChange: (agentName: string) => void;
  onSidebarAgentsChange?: (agents: AgentSidebarItem[]) => void;
  onNavigate: (key: string) => void;
};

type Tone = "neutral" | "success" | "warning" | "danger" | "info";
type AgentStatus = AgentSidebarItem["status"];

type AgentDefinition = {
  name: string;
  role: string;
  summary: string;
  detail: string;
  input: string;
  output: string;
};

type McpToolDefinition = {
  name: string;
  status: string;
  detail: string;
};

type ReportResponse = {
  final_report?: FinalReport;
  quality_result?: QualityResult;
  quality_status?: string;
  degraded_report?: boolean;
  needs_human_review?: boolean;
  review_ticket?: ReviewTicket;
  evidence_list?: unknown[];
  resolved_products?: unknown[];
  unresolved_products?: string[];
  search_mcp_results?: SearchMcpResult[];
  external_product_candidates?: ExternalProductCandidate[];
  official_spec_records?: OfficialSpecRecord[];
  review_intel_records?: ReviewIntelRecord[];
  review_intel_status?: Record<string, unknown>;
  price_records?: Array<Record<string, unknown>>;
  price_status?: Record<string, unknown>;
  analysis_ai_interpretation?: AnalysisAiInterpretation;
  human_feedback?: HumanFeedbackRecord[];
};

const AGENTS: AgentDefinition[] = [
  {
    name: "ResearchAgent",
    role: "调研规划员",
    summary: "规划本次分析需要哪些数据",
    detail: "把用户输入拆成数据需求：本地硬件事实、官网规格、用户评价、博主测评、实时价格、驱动生态。",
    input: "产品 A / 产品 B + 分析场景",
    output: "data_requirements / pending_data",
  },
  {
    name: "CollectorAgent",
    role: "采集与实体识别员",
    summary: "识别产品，并调度本地库与 MCP 工具层",
    detail: "完成别名命中、实体消歧、变体识别、本地 JSON 读取；后续会并行调用官网、评价、价格、搜索 MCP。",
    input: "用户输入 + 本地事实库 + MCP Tool Layer",
    output: "resolved_products / product_facts / pending external data",
  },
  {
    name: "EvidenceAgent",
    role: "证据结构化员",
    summary: "把采集结果变成可追溯 evidence",
    detail: "统一 evidence_id、source_type、credibility、source_url，让后续 claim 必须绑定证据。",
    input: "raw_research / local facts / pending records",
    output: "evidence_list / evidence_status",
  },
  {
    name: "AnalysisAgent",
    role: "分析师",
    summary: "只分析有证据支撑的事实差异",
    detail: "当前主要分析硬件事实；没有真实评价/测评证据时，不输出握法、手型、适合游戏等主观结论。",
    input: "evidence_list + product facts",
    output: "hardware_analysis / claims / risks",
  },
  {
    name: "VerificationAgent",
    role: "事实校验员",
    summary: "检查结论是否被 evidence 支撑",
    detail: "检查 claim.evidence_ids 是否有效，数字和矩阵结论是否能被引用证据支撑，拦截幻觉结论。",
    input: "claims / evidence_list / matrices",
    output: "faithfulness_report / unsupported_claim_ids",
  },
  {
    name: "QualityAgent",
    role: "质量门控员",
    summary: "决定通过、打回或有限报告",
    detail: "可以打回 Research、Collector、Evidence、Analysis；多次自动修复仍不足时生成 partial_report。",
    input: "faithfulness / risks / pending data / coverage",
    output: "quality_result / reject_to / approved_with_limitations",
  },
  {
    name: "ReportAgent",
    role: "报告撰写员",
    summary: "生成最终报告",
    detail: "只整合前面 Agent 的结构化结果，输出最终建议、风险披露、pending 数据说明和证据引用。",
    input: "verified claims + quality result",
    output: "final_report / used_claim_ids / used_evidence_ids",
  },
];

const MCP_TOOLS: McpToolDefinition[] = [
  { name: "本地 JSON 事实库", status: "active", detail: "当前已启用，提供稳定硬件参数和型号别名。" },
  { name: "官网规格 MCP", status: "active", detail: "已接入，用于抽取官网规格、固件更新、驱动资料。" },
  { name: "评价/测评 MCP", status: "active", detail: "已接入，采集用户反馈、博主测评和体验口碑；本地评价库命中即时读取，未命中走实时爬取。" },
  { name: "实时价格 MCP", status: "active", detail: "已接入，联网搜索 + 大模型抽取当前售价；官方价被反爬拦截时退用其他来源并标低可信。" },
  { name: "搜索 MCP", status: "active", detail: "已接入，用于识别未知简称、变体和新品的官网候选。" },
];

function mcpToolsFromReport(report: Record<string, unknown>): McpToolDefinition[] {
  const officialSpecs = officialSpecRecordsFromReport(report);
  const officialCollected = officialSpecs.filter((item) => normalize(item.status) === "collected").length;
  const priceStatus = asRecord(report.price_status);
  const priceRecords = asRecords(report.price_records);
  const reviewStatus = reviewIntelStatusFromReport(report);
  const reviewRecords = reviewIntelRecordsFromReport(report);
  const reviewCollected =
    asNumber(reviewStatus.collected_count) ??
    reviewRecords.filter((item) => reviewSignalEntries(item).length > 0).length;
  const reviewSourceCount =
    asNumber(reviewStatus.source_count) ??
    reviewRecords.reduce((sum, item) => sum + asStrings(item.source_urls).length, 0);
  const reviewStatusValue = asString(reviewStatus.status) || (reviewRecords.length ? asString(reviewRecords[0]?.status) : "");
  const priceCollected =
    asNumber(priceStatus.collected_count) ??
    priceRecords.filter((item) => normalize(item.status) === "collected").length;

  return MCP_TOOLS.map((tool) => {
    if (tool.name.includes("璇勪环") || tool.name.includes("娴嬭瘎") || tool.name.includes("评价") || tool.name.includes("测评")) {
      if (reviewCollected > 0) {
        return {
          ...tool,
          status: "active",
          detail: `已通过真实搜索 + LLM 抽取 ${reviewCollected}/${reviewRecords.length || reviewCollected} 款产品的测评/口碑信号，来源 ${reviewSourceCount} 个。`,
        };
      }
      if (reviewRecords.length || reviewStatusValue) {
        return {
          ...tool,
          status: reviewStatusValue || "pending",
          detail: `ReviewIntelMCP 已运行：${reviewStatusLabel(reviewStatusValue)}。${asString(reviewStatus.note) || "未生成体验结论；请查看 Collector / Evidence / Verification 详情。"}`,
        };
      }
      return tool;
    }
    if (tool.name.includes("瀹樼綉") || tool.name.includes("官网规格")) {
      if (officialCollected > 0) {
        return {
          ...tool,
          status: "active",
          detail: `已抽取 ${officialCollected}/${officialSpecs.length || officialCollected} 条官网规格记录，硬件表会使用这些真实字段。`,
        };
      }
      return tool;
    }
    if (tool.name.includes("瀹炴椂") || tool.name.includes("实时价格")) {
      if (priceCollected > 0) {
        return {
          ...tool,
          status: "active",
          detail: `已采集 ${priceCollected}/${priceRecords.length || priceCollected} 款产品的实时价格线索，弱来源会被标低可信。`,
        };
      }
      if (priceRecords.length || Object.keys(priceStatus).length) {
        return {
          ...tool,
          status: asString(priceStatus.status) || "pending",
          detail: asString(priceStatus.note) || tool.detail,
        };
      }
      return tool;
    }
    return tool;
  });
}

const QUALITY_TARGETS = [
  { name: "ResearchAgent", reason: "数据需求不完整" },
  { name: "CollectorAgent", reason: "缺少竞品或来源" },
  { name: "EvidenceAgent", reason: "证据结构不合格" },
  { name: "AnalysisAgent", reason: "结论没有证据支撑" },
];

const RESEARCH_REQUIREMENTS = [
  {
    name: "硬件数据",
    status: "complete",
    owner: "本地 JSON / OfficialSpec MCP",
    fields: ["重量", "传感器", "DPI", "回报率", "连接方式", "点击系统", "软件"],
    summary: "如果本地 JSON 命中两款产品，则直接展示硬件事实；否则标记为 pending，等待官网 MCP 补齐。",
  },
  {
    name: "用户评价与电商评论",
    status: "pending",
    owner: "ReviewIntel MCP",
    fields: ["手感", "品控", "售后", "长期使用问题", "适合人群"],
    summary: "当前不输出体验结论，等待真实评论采集和 LLM 汇总。",
  },
  {
    name: "博主测评与体验口碑",
    status: "pending",
    owner: "ReviewIntel MCP",
    fields: ["握法", "游戏类型", "对比观点", "延迟/续航体验"],
    summary: "后续采集 Bilibili / YouTube / 专业测评站摘要。",
  },
  {
    name: "实时价格与可买性",
    status: "pending",
    owner: "Price MCP",
    fields: ["当前价格", "折扣", "区域库存", "历史低价"],
    summary: "价格不再写死，后续由实时 MCP 补齐。",
  },
  {
    name: "驱动生态与软件体验",
    status: "partial",
    owner: "CollectorAgent / ReviewIntel MCP",
    fields: ["驱动名称", "板载内存", "宏/配置", "稳定性反馈"],
    summary: "本地只保留软件事实，驱动稳定性等待用户评价验证。",
  },
];

function requirementMeta(status: string): { label: string; second: string; tone: Tone } {
  switch (status) {
    case "complete":
      return { label: "已采集", second: "已准备", tone: "success" };
    case "partial":
      return { label: "部分采集", second: "部分事实", tone: "info" };
    case "no_data":
      return { label: "已尝试·未抓到", second: "未抓到数据", tone: "warning" };
    default:
      return { label: "待采集", second: "等待采集", tone: "warning" };
  }
}

const SOURCE_PRIORITIES = [
  {
    level: "P0",
    name: "品牌官网 / 官方规格",
    credibility: "最高",
    usage: "硬件参数、固件、驱动、官方型号命名",
  },
  {
    level: "P1",
    name: "专业测评站 / 实测数据",
    credibility: "高",
    usage: "传感器表现、延迟、重量校验、续航实测",
  },
  {
    level: "P2",
    name: "博主测评 / 长视频体验",
    credibility: "中",
    usage: "手感、握法、游戏场景、对比体验",
  },
  {
    level: "P3",
    name: "电商评论 / 社区口碑",
    credibility: "需交叉验证",
    usage: "品控、售后、长期可靠性、驱动问题",
  },
];

const RESEARCH_HANDOFFS = [
  {
    agent: "CollectorAgent",
    task: "根据数据需求调度本地 JSON 与后续 MCP 工具，完成产品识别和数据采集。",
  },
  {
    agent: "EvidenceAgent",
    task: "把采集结果统一转换成 evidence，并标注来源、可信度和 pending 状态。",
  },
  {
    agent: "AnalysisAgent",
    task: "只分析 evidence 支撑的硬件事实差异，外部体验数据缺失时不编结论。",
  },
  {
    agent: "QualityAgent",
    task: "检查结论是否有证据、pending 是否披露，并据此降低报告可信度。",
  },
];

const STATUS_LABEL: Record<AgentStatus, string> = {
  waiting: "等待",
  running: "运行中",
  done: "完成",
  limited: "有限通过",
  partial: "有限报告",
  failed: "失败",
};

const STATUS_TONE: Record<AgentStatus, Tone> = {
  waiting: "neutral",
  running: "info",
  done: "success",
  limited: "warning",
  partial: "warning",
  failed: "danger",
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asRecords(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value)
    ? value.filter(
        (item): item is Record<string, unknown> =>
          Boolean(item) && typeof item === "object" && !Array.isArray(item),
      )
    : [];
}

function asString(value: unknown, fallback = ""): string {
  if (typeof value === "string" && value.trim()) return value.trim();
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return fallback;
}

function asNumber(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function normalize(value: unknown): string {
  return asString(value).toLowerCase();
}

function extractReport(response: ReportResponse | FinalReport | null): Record<string, unknown> {
  if (!response) return {};
  const record = asRecord(response);
  return asRecord(record.final_report ?? response);
}

function traceMap(traceLog: AgentTrace[]) {
  return traceLog.reduce<Record<string, AgentTrace>>((acc, trace) => {
    acc[trace.agent_name] = trace;
    return acc;
  }, {});
}

function qualityStatusText(
  status: AnalysisStatus | null,
  quality: QualityResult | undefined,
  reportResponse: ReportResponse | FinalReport | null,
  report: Record<string, unknown>,
) {
  const responseRecord = asRecord(reportResponse);
  return (
    asString(quality?.status) ||
    asString(responseRecord.quality_status) ||
    asString(report.quality_status) ||
    asString(status?.quality_status) ||
    "pending"
  );
}

function isFinalDone(status: AnalysisStatus | null) {
  return normalize(status?.status) === "completed" || normalize(status?.status) === "failed";
}

function deriveStatus(
  agent: AgentDefinition,
  trace: AgentTrace | undefined,
  status: AnalysisStatus | null,
  qualityStatus: string,
  hasReport: boolean,
): AgentStatus {
  if (status?.current_agent === agent.name && !isFinalDone(status)) return "running";
  const traceStatus = normalize(trace?.status);
  if (traceStatus === "failed" || traceStatus === "schema_failed") return "failed";
  if (agent.name === "QualityAgent") {
    const quality = normalize(qualityStatus);
    if (quality === "partial_report") return "partial";
    if (quality === "approved_with_limitations") return "limited";
    if (quality === "approved") return "done";
  }
  if (agent.name === "ReportAgent" && hasReport) return "done";
  if (trace) return "done";
  return "waiting";
}

function qualityTone(qualityStatus: string): Tone {
  const value = normalize(qualityStatus);
  if (value === "approved") return "success";
  if (value === "approved_with_limitations" || value === "partial_report") return "warning";
  if (value.includes("reject") || value === "failed") return "danger";
  return "neutral";
}

function currentIndex(currentAgent: string) {
  const index = AGENTS.findIndex((agent) => agent.name === currentAgent);
  return index >= 0 ? index : -1;
}

function tooltipClass(extra = "") {
  return `pointer-events-none absolute z-40 hidden w-72 rounded-lg border border-cyan-300/25 bg-slate-950/95 p-3 text-left text-xs leading-5 text-slate-300 shadow-[0_20px_60px_rgba(2,6,23,0.65)] group-hover:block ${extra}`;
}

function FlowStyles() {
  return (
    <style>
      {`
        @keyframes dag-flow {
          0% { transform: translateX(0); opacity: 0; }
          15% { opacity: 1; }
          85% { opacity: 1; }
          100% { transform: translateX(34px); opacity: 0; }
        }
        @keyframes dag-drop {
          0% { transform: translateY(0); opacity: .2; }
          40% { opacity: 1; }
          100% { transform: translateY(24px); opacity: .2; }
        }
        @keyframes agent-card-pulse {
          0%, 100% { box-shadow: 0 0 0 rgba(34, 211, 238, 0); }
          50% { box-shadow: 0 0 28px rgba(34, 211, 238, 0.18); }
        }
      `}
    </style>
  );
}

function FlowArrow({ active, label }: { active: boolean; label?: string }) {
  return (
    <div className="relative flex h-full min-w-7 items-center">
      <div className={`h-px w-full ${active ? "bg-cyan-300/70" : "bg-slate-700"}`} />
      {active ? (
        <span
          className="absolute left-0 h-1.5 w-1.5 rounded-full bg-cyan-200 shadow-[0_0_12px_rgba(103,232,249,0.9)]"
          style={{ animation: "dag-flow 1.6s linear infinite" }}
        />
      ) : null}
      {label ? (
        <span className="absolute -bottom-4 left-1/2 -translate-x-1/2 text-[10px] text-slate-500">
          {label}
        </span>
      ) : null}
    </div>
  );
}

function AgentNode({
  agent,
  status,
  isCurrent,
  isSelected,
  onSelect,
}: {
  agent: AgentDefinition;
  status: AgentStatus;
  isCurrent: boolean;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const statusMeta: Record<AgentStatus, { label: string; dot: string; pill: string }> = {
    waiting: {
      label: "pending",
      dot: "bg-slate-500",
      pill: "border-slate-700 bg-slate-900 text-slate-300",
    },
    running: {
      label: "running",
      dot: "bg-cyan-300",
      pill: "border-cyan-300/45 bg-cyan-300/10 text-cyan-100",
    },
    done: {
      label: "completed",
      dot: "bg-emerald-300",
      pill: "border-emerald-300/45 bg-emerald-300/10 text-emerald-100",
    },
    limited: {
      label: "limited",
      dot: "bg-amber-300",
      pill: "border-amber-300/45 bg-amber-300/10 text-amber-100",
    },
    partial: {
      label: "partial",
      dot: "bg-orange-300",
      pill: "border-orange-300/45 bg-orange-300/10 text-orange-100",
    },
    failed: {
      label: "failed",
      dot: "bg-rose-300",
      pill: "border-rose-300/45 bg-rose-300/10 text-rose-100",
    },
  };
  const meta = statusMeta[status] || statusMeta.waiting;
  const activeClass = isCurrent
    ? "border-cyan-300 bg-cyan-400/15 shadow-[0_0_28px_rgba(34,211,238,0.16)]"
    : status === "done"
      ? "border-emerald-400/35 bg-emerald-400/10"
      : status === "limited" || status === "partial"
        ? "border-amber-400/45 bg-amber-400/10"
        : status === "failed"
          ? "border-rose-400/45 bg-rose-500/10"
          : "border-slate-700 bg-slate-900/70";

  return (
    <button className="group relative min-w-0 text-left" onClick={onSelect} type="button">
      <div
        className={`h-full rounded-lg border p-3 transition hover:-translate-y-0.5 hover:border-cyan-300/60 ${
          isSelected ? "ring-2 ring-cyan-300/50" : ""
        } ${activeClass}`}
      >
        <div className="flex items-center justify-between gap-2">
          <p className="truncate text-sm font-semibold text-white">{agent.name}</p>
          <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${meta.dot} ${isCurrent ? "animate-pulse" : ""}`} />
        </div>
        <p className="mt-1 line-clamp-2 min-h-8 text-xs leading-4 text-slate-400">
          {agent.summary}
        </p>
      </div>

      <div className={tooltipClass("left-0 top-[calc(100%+10px)]")}>
        <p className="font-semibold text-cyan-100">{agent.role}</p>
        <p className="mt-2">{agent.detail}</p>
        <div className="mt-3 grid gap-2 border-t border-slate-800 pt-3">
          <p>
            <span className="text-slate-500">输入：</span>
            {agent.input}
          </p>
          <p>
            <span className="text-slate-500">输出：</span>
            {agent.output}
          </p>
        </div>
      </div>
    </button>
  );
}

function McpToolCard({
  name,
  status,
  detail,
}: {
  name: string;
  status: string;
  detail: string;
}) {
  const active = status === "active";
  return (
    <div className="group relative">
      <div
        className={`h-full rounded-lg border p-3 ${
          active
            ? "border-emerald-400/35 bg-emerald-400/10"
            : "border-dashed border-amber-400/40 bg-amber-400/10"
        }`}
      >
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm font-semibold text-white">{name}</p>
          <StatusBadge label={active ? "active" : "pending"} tone={active ? "success" : "warning"} />
        </div>
        <p className="mt-2 line-clamp-2 text-xs leading-5 text-slate-400">{detail}</p>
      </div>
      <div className={tooltipClass("left-0 top-[calc(100%+10px)]")}>
        <p className="font-semibold text-cyan-100">{name}</p>
        <p className="mt-2">{detail}</p>
        <p className="mt-3 border-t border-slate-800 pt-3 text-slate-500">
          {active ? "当前流程已使用该数据源。" : "后续接入 MCP 后由 CollectorAgent 并行调用。"}
        </p>
      </div>
    </div>
  );
}

function WorkflowDagCanvas({
  taskId,
  displayTaskId,
  taskStatus,
  currentAgent,
  progress,
  agentStatuses,
  mcpTools,
  hasReport,
  selectedAgent,
  onSelectAgent,
  onNavigate,
}: {
  taskId: string;
  displayTaskId?: string;
  taskStatus?: string;
  currentAgent: string;
  progress: number;
  agentStatuses: Record<string, AgentStatus>;
  mcpTools: McpToolDefinition[];
  hasReport: boolean;
  selectedAgent: string;
  onSelectAgent: (agentName: string) => void;
  onNavigate: (key: string) => void;
}) {
  const activeIndex = currentIndex(currentAgent);
  const completed = normalize(taskStatus) === "completed";

  return (
    <section className="rounded-lg border border-slate-800 bg-slate-950/75 p-5">
      <FlowStyles />
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-cyan-300">
            LangGraph DAG
          </p>
          <h2 className="mt-2 text-2xl font-semibold text-white">
            多 Agent 协作与 MCP 采集链路
          </h2>
          <div className="mt-3 flex flex-wrap gap-2 text-xs">
            <StatusBadge label={`任务 ${displayTaskId || taskId}`} tone="info" />
            <StatusBadge label={taskStatus || "waiting"} tone="neutral" />
            <StatusBadge label={`当前 ${currentAgent}`} tone="info" />
            <StatusBadge label={`进度 ${Math.min(100, Math.max(0, progress))}%`} tone="success" />
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            className="rounded-md border border-slate-700 bg-slate-900/80 px-3 py-2 text-sm font-medium text-slate-200 transition hover:border-cyan-300/50 hover:text-cyan-100"
            onClick={() => onNavigate("product-compare")}
            type="button"
          >
            重新选择产品
          </button>
          <button
            className={`rounded-md px-3 py-2 text-sm font-semibold transition ${
              hasReport
                ? "bg-cyan-300 text-slate-950 hover:bg-cyan-200"
                : "cursor-not-allowed bg-slate-800 text-slate-500"
            }`}
            disabled={!hasReport}
            onClick={() => hasReport && onNavigate("report")}
            type="button"
          >
            查看最终报告
          </button>
        </div>
      </div>

      <div className="mt-5 rounded-lg border border-slate-800 bg-slate-950/80 p-4">
        <div className="mx-auto w-fit rounded-md border border-cyan-300/35 bg-cyan-400/10 px-5 py-3 text-center text-sm font-semibold text-cyan-100">
          LangGraph DAG Agent Workflow
        </div>
        <div className="relative mx-auto h-7 w-px bg-slate-700">
          <span
            className="absolute left-1/2 top-0 h-1.5 w-1.5 -translate-x-1/2 rounded-full bg-cyan-200"
            style={{ animation: "dag-drop 1.4s ease-in-out infinite" }}
          />
        </div>

        <div
          className="grid items-stretch gap-2"
          style={{
            gridTemplateColumns:
              "minmax(105px,1fr) 28px minmax(105px,1fr) 28px minmax(105px,1fr) 28px minmax(105px,1fr) 28px minmax(105px,1fr) 28px minmax(105px,1fr) 28px minmax(105px,1fr)",
          }}
        >
          {AGENTS.map((agent, index) => {
            const arrowActive = completed || (activeIndex >= 0 && index < activeIndex);
            const nodeCurrent = !completed && currentAgent === agent.name;
            return (
              <div className="contents" key={agent.name}>
                <AgentNode
                  agent={agent}
                  status={agentStatuses[agent.name] ?? "waiting"}
                  isCurrent={nodeCurrent}
                  isSelected={selectedAgent === agent.name}
                  onSelect={() => onSelectAgent(agent.name)}
                />
                {index < AGENTS.length - 1 ? (
                  <FlowArrow active={arrowActive} label={index === 1 ? "facts" : undefined} />
                ) : null}
              </div>
            );
          })}
        </div>

        <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1fr)_300px]">
          <div>
            <div className="ml-[calc((100%/7)+16px)] w-fit">
              <div className="mx-auto h-7 w-px border-l border-dashed border-cyan-300/50" />
              <div className="rounded-md border border-cyan-300/35 bg-cyan-400/10 px-4 py-2 text-center text-sm font-semibold text-cyan-100">
                MCP Tool Layer
              </div>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-5">
              {mcpTools.map((tool) => (
                <McpToolCard
                  key={tool.name}
                  name={tool.name}
                  status={tool.status}
                  detail={tool.detail}
                />
              ))}
            </div>
          </div>

          <div className="rounded-lg border border-amber-400/30 bg-amber-400/10 p-4">
            <p className="text-sm font-semibold text-amber-100">QualityAgent 反馈闭环</p>
            <div className="mt-3 space-y-2">
              {QUALITY_TARGETS.map((target) => (
                <button
                  className="group relative flex w-full items-center gap-2 text-left"
                  key={target.name}
                  onClick={() => onSelectAgent(target.name)}
                  type="button"
                >
                  <span className="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-200">
                    Quality
                  </span>
                  <span className="text-amber-200">↩</span>
                  <span className="rounded-md border border-amber-400/35 bg-slate-950 px-2 py-1 text-xs text-amber-100">
                    {target.name}
                  </span>
                  <div className={tooltipClass("right-0 top-[calc(100%+8px)]")}>
                    <p className="font-semibold text-amber-100">打回条件</p>
                    <p className="mt-2">{target.reason}</p>
                    <p className="mt-2 text-slate-500">三次自动修复仍不足时生成 partial_report。</p>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function AgentCardGrid({
  selectedAgent,
  currentAgent,
  agentStatuses,
  traces,
  onSelectAgent,
}: {
  selectedAgent: string;
  currentAgent: string;
  agentStatuses: Record<string, AgentStatus>;
  traces: Record<string, AgentTrace>;
  onSelectAgent: (agentName: string) => void;
}) {
  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      {AGENTS.map((agent, index) => {
        const status = agentStatuses[agent.name] ?? "waiting";
        const selected = selectedAgent === agent.name;
        const running = currentAgent === agent.name;
        const trace = traces[agent.name];
        return (
          <button
            className={`group min-h-[168px] rounded-lg border p-4 text-left transition hover:-translate-y-1 hover:border-cyan-300/60 ${
              selected
                ? "border-cyan-300/60 bg-cyan-400/10 ring-2 ring-cyan-300/30"
                : running
                  ? "border-cyan-300/50 bg-cyan-400/10"
                  : status === "done"
                    ? "border-emerald-400/35 bg-emerald-400/10"
                    : status === "limited" || status === "partial"
                      ? "border-amber-400/40 bg-amber-400/10"
                      : status === "failed"
                        ? "border-rose-400/45 bg-rose-500/10"
                        : "border-slate-800 bg-slate-950/70"
            }`}
            key={agent.name}
            onClick={() => onSelectAgent(agent.name)}
            style={running ? { animation: "agent-card-pulse 1.8s ease-in-out infinite" } : undefined}
            type="button"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                  {String(index + 1).padStart(2, "0")}
                </p>
                <h3 className="mt-2 text-lg font-semibold text-white">{agent.name}</h3>
                <p className="mt-1 text-sm text-slate-400">{agent.role}</p>
              </div>
              <StatusBadge label={STATUS_LABEL[status]} tone={STATUS_TONE[status]} />
            </div>
            <p className="mt-4 text-sm leading-6 text-slate-300">{agent.summary}</p>
            <p className="mt-3 line-clamp-2 text-xs leading-5 text-slate-500">
              {trace?.output_summary || "点击查看该 Agent 的详细数据。"}
            </p>
          </button>
        );
      })}
    </div>
  );
}

function researchTone(status: string): Tone {
  const value = normalize(status);
  if (value === "complete" || value === "active") return "success";
  if (value === "partial") return "warning";
  if (value.includes("pending") || value.includes("mcp_not_connected")) return "warning";
  if (value.includes("fail")) return "danger";
  return "neutral";
}

function productLabelsFromReport(report: Record<string, unknown>, unresolved: string[] = []) {
  const identities = asRecords(report.product_identification);
  const resolved = asRecords(report.resolved_products);
  const products = identities.length ? identities : resolved;
  const labels = products
    .slice(0, 2)
    .map((item, index) => {
      const label =
        [asString(item.brand), asString(item.model || item.official_model)]
          .filter(Boolean)
          .join(" ") ||
        asString(item.product_name) ||
        asString(item.id);
      return label || `产品 ${index + 1}`;
    })
    .filter(Boolean);

  // 未命中本地库的输入也占一个产品位（待搜索 / 官网 MCP 识别），保证两个产品都出现。
  for (const query of unresolved) {
    if (labels.length >= 2) break;
    labels.push(`${query}（待搜索 / 官网 MCP 识别）`);
  }

  return labels.length ? labels : ["产品 A（等待 CollectorAgent 识别）", "产品 B（等待 CollectorAgent 识别）"];
}

function formatValue(value: unknown, fallback = "未找到相应数据") {
  if (Array.isArray(value)) return value.length ? value.join(" / ") : fallback;
  if (typeof value === "boolean") return value ? "支持" : "不支持";
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value === "string" && value.trim()) return value.trim();
  return fallback;
}

function formatDimensions(value: unknown) {
  const dims = asRecord(value);
  const length = asNumber(dims.length);
  const width = asNumber(dims.width);
  const height = asNumber(dims.height);
  if ([length, width, height].every((item) => typeof item === "number")) {
    return `${length} x ${width} x ${height} mm`;
  }
  return "";
}

function officialSpecRecordsFromReport(report: Record<string, unknown>): OfficialSpecRecord[] {
  return asRecords(report.official_spec_records) as OfficialSpecRecord[];
}

function reviewIntelRecordsFromReport(report: Record<string, unknown>): ReviewIntelRecord[] {
  return asRecords(report.review_intel_records) as ReviewIntelRecord[];
}

function reviewIntelStatusFromReport(report: Record<string, unknown>): Record<string, unknown> {
  return asRecord(report.review_intel_status);
}

function reviewSignalEntries(record: ReviewIntelRecord): Array<[string, Record<string, unknown>]> {
  const signals = asRecord(record.signals);
  return Object.entries(signals)
    .map(([dimension, signal]) => [dimension, asRecord(signal)] as [string, Record<string, unknown>])
    .filter(([, signal]) => Boolean(asString(signal.summary)));
}

function reviewRecordLabel(record: ReviewIntelRecord, index = 0): string {
  return [asString(record.brand), asString(record.model)].filter(Boolean).join(" ") || asString(record.input) || `产品 ${index + 1}`;
}

function reviewStatusTone(status: unknown): Tone {
  const value = normalize(status);
  if (value === "available" || value === "collected") return "success";
  if (value === "partial" || value === "partial_collected" || value.includes("llm") || value.includes("no_sources")) return "warning";
  if (value.includes("failed") || value.includes("error")) return "danger";
  if (value.includes("pending") || value.includes("not_configured")) return "warning";
  return "neutral";
}

function reviewStatusLabel(status: unknown): string {
  const value = normalize(status);
  const labels: Record<string, string> = {
    available: "已采集",
    collected: "已采集",
    partial: "部分采集",
    partial_collected: "部分采集",
    no_sources: "未找到测评源",
    insufficient_evidence: "证据不足",
    llm_not_configured: "LLM 未配置",
    llm_extraction_failed: "LLM 抽取失败",
    mcp_not_configured: "MCP 未配置",
    pending: "待采集",
  };
  return labels[value] || asString(status, "待采集");
}

function reviewDimensionLabel(value: unknown): string {
  const key = normalize(value);
  const labels: Record<string, string> = {
    grip_feel: "握法手感",
    hand_size_fit: "手型适配",
    game_type_fit: "游戏类型",
    driver_reputation: "驱动口碑",
    long_term_reliability: "长期可靠性",
    community_sentiment: "社区口碑",
    build_quality: "品控做工",
  };
  return labels[key] || asString(value, key || "体验维度");
}

function isMostlyEnglish(text: string): boolean {
  if (!text) return false;
  const latin = (text.match(/[A-Za-z]/g) || []).length;
  const cjk = (text.match(/[\u4e00-\u9fff]/g) || []).length;
  return latin > 24 && latin > cjk * 2;
}

function localizedConfidence(value: unknown): string {
  const key = normalize(value);
  const labels: Record<string, string> = {
    high: "高可信",
    medium: "中可信",
    low: "低可信",
    none: "无可用证据",
    pending: "待确认",
  };
  return labels[key] || asString(value, "待确认");
}

function localizedSentiment(value: unknown): string {
  const key = normalize(value);
  const labels: Record<string, string> = {
    positive: "正向",
    mixed: "评价分化",
    negative: "负向",
    unknown: "未明确",
  };
  return labels[key] || asString(value, "未明确");
}

function reviewSummaryZh(signal: Record<string, unknown>, dimensionHint?: unknown): string {
  const direct = asString(signal.summary_zh) || asString(signal.chinese_summary);
  if (direct) return direct;
  const summary = asString(signal.summary);
  if (!summary) return "未抽取到可读摘要。";
  if (!isMostlyEnglish(summary)) return summary;

  const dimension = normalize(signal.dimension || dimensionHint);
  const text = summary.toLowerCase();
  if (dimension === "grip_feel") {
    const loud = text.includes("loud") || text.includes("click");
    return `低背对称模具，适合爪握和指握，整体握持比较舒适${loud ? "；点击声音偏明显，介意静音的用户需要注意。" : "。"}`;
  }
  if (dimension === "hand_size_fit") {
    return "对称外形覆盖较宽手型，中到大手更容易获得稳定支撑；具体手型适配仍建议结合真实握持反馈判断。";
  }
  if (dimension === "game_type_fit") {
    const games = ["Apex", "CS2", "Halo"].filter((game) => summary.includes(game));
    return `适合 FPS 和竞技射击场景，强调顺滑追踪、低延迟和快速定位${games.length ? `；来源中提到 ${games.join("、")} 等游戏。` : "。"}`;
  }
  if (dimension === "driver_reputation") {
    return "Razer Synapse 可定制能力较强，桌面端响应和配置项较完整；网页版更方便，但高级设置可能少于桌面端。";
  }
  if (dimension === "long_term_reliability") {
    return "光学滚轮编码器等设计理论上有利于耐久性，但长期真实使用样本仍不足，因此可靠性只能作为弱支撑。";
  }
  if (dimension === "community_sentiment") {
    return "当前来源能体现部分社区/用户口碑，但样本覆盖有限，不能直接当成完整市场口碑结论。";
  }
  if (dimension === "build_quality") {
    return "现有来源对做工和品控有一定正面描述，但仍需要更多长期用户评价交叉验证。";
  }
  return summary;
}

function parseJsonRecord(value: unknown): Record<string, unknown> {
  const text = asString(value);
  if (!text || !text.trim().startsWith("{")) return {};
  try {
    const parsed = JSON.parse(text);
    return asRecord(parsed);
  } catch {
    return {};
  }
}

function readableEvidenceSummary(evidence: Record<string, unknown>): string {
  const rawFromContent = parseJsonRecord(evidence.raw_content);
  const raw = Object.keys(rawFromContent).length ? rawFromContent : parseJsonRecord(evidence.content);
  const signal = asRecord(raw.signal);
  if (Object.keys(signal).length) {
    return reviewSummaryZh(signal, signal.dimension || evidence.related_dimension || evidence.dimension);
  }
  const summary = asString(evidence.summary);
  if (summary && !summary.trim().startsWith("{")) return summary;
  return asString(evidence.claim) || asString(evidence.source_title) || "已结构化为 evidence。";
}

function readableMatrixText(value: unknown, dimension?: unknown): string {
  const text = asString(value);
  const raw = parseJsonRecord(text);
  const signal = asRecord(raw.signal);
  if (Object.keys(signal).length) return reviewSummaryZh(signal, signal.dimension || dimension);
  return text && !text.trim().startsWith("{") ? text : "该格已绑定 evidence，详情见证据中心。";
}

function reviewVerificationReasonZh(value: unknown): string {
  const text = asString(value);
  if (!text) return "已完成测评信号校验。";
  if (text.includes("cites ReviewIntel evidence")) return "该测评信号引用了 ReviewIntel evidence，且来源置信度足够。";
  if (text.includes("low source confidence")) return "该测评信号有 evidence，但来源置信度偏低，只能作为弱支撑。";
  if (text.includes("no evidence_id")) return "该测评信号缺少 evidence_id，不能用于场景推荐。";
  return isMostlyEnglish(text) ? "该条结论已完成自动校验，英文原始原因已折叠为中文摘要。" : text;
}

function officialSpecPayload(item: OfficialSpecRecord): Record<string, unknown> {
  return asRecord(item.record);
}

type HardwareProductSource = "local" | "official";

type HardwareProduct = {
  id: string;
  label: string;
  specs: Record<string, unknown>;
  source: HardwareProductSource;
  sourceLabel: string;
  collectionStatus?: string;
  missingFields: string[];
};

function hardwareSourceFromSpec(item: Record<string, unknown>): HardwareProductSource {
  const source = normalize(item.fact_source);
  const dataStatus = normalize(item.data_status);
  return source.includes("official") || dataStatus.startsWith("official_spec") ? "official" : "local";
}

function hardwareProductsFromReport(report: Record<string, unknown>): HardwareProduct[] {
  // final_report.hardware_specs 可能包含本地 JSON 产品，也可能包含 OfficialSpecMCP 转成的产品事实。
  const localProducts = asRecords(report.hardware_specs)
    .map((item, index) => {
      const source = hardwareSourceFromSpec(item);
      return {
        id: asString(item.product_id) || asString(item.id) || `product-${index + 1}`,
        label:
          [asString(item.brand), asString(item.model)].filter(Boolean).join(" ") ||
          `产品 ${index + 1}`,
        specs: item,
        source,
        sourceLabel: source === "local" ? "本地 JSON" : "官网抽取",
        collectionStatus: asString(item.data_status),
        missingFields: [] as string[],
      };
    })
    .filter(hasUsefulHardware);

  const officialProducts = officialSpecRecordsFromReport(report)
    .map((item, index) => {
      const record = officialSpecPayload(item);
      const label =
        [asString(record.brand), asString(record.official_model) || asString(record.model)]
          .filter(Boolean)
          .join(" ") ||
        asString(item.input) ||
        `官网产品 ${index + 1}`;
      return {
        id: asString(record.product_id) || asString(record.id) || normalize(label) || `official-product-${index + 1}`,
        label,
        specs: record,
        source: "official" as const,
        sourceLabel: "官网抽取",
        collectionStatus: asString(item.status),
        missingFields: [...new Set([...asStrings(item.missing_fields), ...asStrings(record.missing_fields)])],
      };
    })
    .filter(hasUsefulHardware);

  const merged = [...localProducts];
  for (const product of officialProducts) {
    const key = normalize(product.label || product.id);
    const exists = merged.some((item) => normalize(item.label || item.id) === key);
    if (!exists) merged.push(product);
  }

  return merged.slice(0, 2);
}

const HARDWARE_FIELDS = [
  { key: "weight_g", label: "重量", unit: "g" },
  { key: "sensor", label: "传感器" },
  { key: "dpi_max", label: "最高 DPI" },
  { key: "polling_rate_hz", label: "回报率", unit: "Hz" },
  { key: "connection", label: "连接方式" },
  { key: "battery_hours", label: "续航", unit: "h" },
  { key: "switch_type", label: "微动" },
  { key: "click_system", label: "点击系统" },
  { key: "software", label: "驱动 / 软件" },
  { key: "onboard_memory", label: "板载内存" },
];

// 字段 key → 中文名（用于"待补字段"等处，避免直接展示 dimensions_mm 这类代码字段名）。
const HARDWARE_FIELD_LABEL: Record<string, string> = Object.fromEntries(
  HARDWARE_FIELDS.map((field) => [field.key, field.label]),
);

const CONNECTION_VALUE_LABEL: Record<string, string> = {
  "2.4ghz": "2.4G 无线",
  wired: "有线",
  bluetooth: "蓝牙",
};

const CLICK_SYSTEM_VALUE_LABEL: Record<string, string> = {
  optical: "光学微动",
  mechanical: "机械微动",
  hybrid: "混合微动",
  haptic: "触觉微动",
};

const CONFIDENCE_CN: Record<string, string> = {
  high: "高",
  medium: "中",
  low: "低",
  pending: "待定",
};

// 采集流水线子步骤名 / 状态 → 中文。
const PIPELINE_STEP_LABEL: Record<string, string> = {
  ProductResolver: "本地实体识别",
  SearchMCP: "联网搜索",
  ProductFact: "产品事实读取",
  OfficialSpec: "官网规格抽取",
  ReviewIntel: "评价情报",
  Price: "实时价格",
};

const SUBSTEP_STATUS_LABEL: Record<string, string> = {
  success: "成功",
  partial: "部分完成",
  complete: "已完成",
  collected: "已采集",
  pending: "待处理",
  skipped: "跳过",
  official_candidate_found: "找到官网候选",
  review_candidate_found: "找到测评候选",
  low_confidence_candidates: "候选可信度低",
  off_category_suspected: "疑似非鼠标",
  mcp_not_connected: "MCP 未接入",
};

function fieldLabel(key: string): string {
  return HARDWARE_FIELD_LABEL[key] || key;
}

function hasHardwareFieldValue(specs: Record<string, unknown>, key: string) {
  const value = specs[key];
  if (key === "dimensions_mm") {
    return Boolean(formatDimensions(value));
  }
  if (key === "connection") {
    return Array.isArray(value) && value.length > 0;
  }
  return value !== null && value !== undefined && value !== "" && !(Array.isArray(value) && value.length === 0);
}

function hardwareValue(specs: Record<string, unknown>, key: string, unit?: string) {
  if (key === "dimensions_mm") return formatDimensions(specs[key]);
  const value = specs[key];
  if (key === "connection") {
    const items = Array.isArray(value) ? value : [];
    return items.length
      ? items.map((item) => CONNECTION_VALUE_LABEL[normalize(item)] || String(item)).join(" / ")
      : "";
  }
  if (key === "click_system" && value) {
    return CLICK_SYSTEM_VALUE_LABEL[normalize(value)] || String(value);
  }
  if (typeof value === "number" && Number.isFinite(value) && unit) return `${value}${unit}`;
  return formatValue(value, "");
}

function missingHardwareReason(product: HardwareProduct, key: string): string {
  if (product.source === "local") return "本地未找到相应数据";
  const status = normalize(product.collectionStatus);
  if (status === "fetch_failed") return "疑似反爬拦截";
  if (status.includes("failed") || status.includes("error")) return "抽取失败";
  if (status === "insufficient_specs" || product.missingFields.includes(key)) return "官网未披露";
  if (status === "partial_collected") return "当前来源未找到";
  return "未找到相应数据";
}

function hardwareDisplayValue(product: HardwareProduct, field: { key: string; unit?: string }) {
  const value = hardwareValue(product.specs, field.key, field.unit);
  return value || missingHardwareReason(product, field.key);
}

function hasUsefulHardware(product: { specs: Record<string, unknown> }) {
  return HARDWARE_FIELDS.some((field) => hasHardwareFieldValue(product.specs, field.key));
}

function HardwareMiniTable({ products }: { products: HardwareProduct[] }) {
  if (products.length < 2) {
    return (
      <div className="rounded-md border border-amber-400/25 bg-amber-400/10 p-3 text-sm leading-6 text-amber-100">
        本地 JSON 未同时命中两款产品；未命中的产品会交给搜索 / 官网规格 MCP 识别来源。
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-md border border-slate-800 bg-slate-950/70">
      <div className="grid grid-cols-[120px_minmax(0,1fr)_minmax(0,1fr)] border-b border-slate-800 bg-slate-900/70 text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
        <div className="p-3">字段</div>
        {products.map((product) => (
          <div className="min-w-0 p-3 text-slate-300" key={product.id}>
            <span className="block truncate">{product.label}</span>
            <span className={`mt-1 inline-block rounded-full px-2 py-0.5 text-[10px] ${
              product.source === "local" ? "bg-emerald-400/10 text-emerald-200" : "bg-cyan-400/10 text-cyan-200"
            }`}>
              {product.sourceLabel}
            </span>
          </div>
        ))}
      </div>
      {HARDWARE_FIELDS.map((field) => (
        <div
          className="grid grid-cols-[120px_minmax(0,1fr)_minmax(0,1fr)] border-b border-slate-800/80 last:border-b-0"
          key={field.key}
        >
          <div className="p-3 text-xs text-slate-500">{field.label}</div>
          {products.map((product) => (
            <div className="min-w-0 break-words p-3 text-sm text-slate-200" key={product.id}>
              <span className={hasHardwareFieldValue(product.specs, field.key) ? "text-slate-200" : "text-amber-300/85"}>
                {hardwareDisplayValue(product, field)}
              </span>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

function officialSpecDisplayName(item: OfficialSpecRecord, index: number): string {
  const record = officialSpecPayload(item);
  return (
    [asString(record.brand), asString(record.official_model) || asString(record.model)]
      .filter(Boolean)
      .join(" ") ||
    asString(item.input) ||
    `产品 ${index + 1}`
  );
}

function officialSpecStatusTone(status: unknown): Tone {
  const value = normalize(status);
  if (value === "collected" || value === "complete") return "success";
  if (value.includes("partial") || value.includes("missing") || value.includes("insufficient")) return "warning";
  if (value.includes("error") || value.includes("failed")) return "danger";
  if (value.includes("pending") || value.includes("not_connected")) return "warning";
  return "neutral";
}

function officialSpecStatusLabel(status: unknown): string {
  const value = normalize(status);
  const labels: Record<string, string> = {
    collected: "已采集",
    complete: "已采集",
    partial: "部分采集",
    partial_collected: "部分采集",
    insufficient_specs: "规格不足",
    pending: "待采集",
    mcp_not_connected: "MCP 未接入",
    mcp_not_configured: "MCP 未配置",
    mcp_error: "采集异常",
    llm_error: "LLM 异常",
    llm_failed: "LLM 抽取失败",
    fetch_failed: "抓取被拦截",
    validation_failed: "解析失败",
    rate_limited: "限流",
    missing_url: "缺少链接",
  };
  return labels[value] || asString(status, "待采集");
}

function officialSpecConfidence(item: OfficialSpecRecord): string {
  const record = officialSpecPayload(item);
  return asString(item.confidence) || asString(record.confidence) || "pending";
}

function officialUrlFromHardwareProduct(product: HardwareProduct): string {
  const direct = asString(product.specs.official_url);
  if (direct) return direct;
  const sources = asRecords(product.specs.sources);
  const officialSource = sources.find((source) => normalize(source.source_type) === "official" || isExternalUrl(asString(source.url)));
  return asString(officialSource?.url);
}

function OfficialSpecResultTable({
  records,
  localProducts = [],
}: {
  records: OfficialSpecRecord[];
  localProducts?: HardwareProduct[];
}) {
  const localSourceProducts = localProducts.filter((product) => product.source === "local");
  if (!records.length && !localSourceProducts.length) return null;
  const collected = records.filter((item) => normalize(item.status) === "collected").length + localSourceProducts.length;
  const total = records.length + localSourceProducts.length;

  return (
    <div className="rounded-lg border border-cyan-300/25 bg-slate-900/45 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Official Spec MCP</p>
          <h4 className="mt-2 text-lg font-semibold text-white">官网规格抽取 · 数据来源</h4>
          <p className="mt-1 text-xs leading-5 text-slate-400">
            先由联网搜索找到官网 / 高可信候选，再由官网规格 MCP + 大模型抽取硬件字段；具体数值见下方对比表。
          </p>
        </div>
        <StatusBadge label={`已采集 ${collected}/${total}`} tone={collected === total ? "success" : "warning"} />
      </div>

      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        {localSourceProducts.map((product, index) => {
          const url = officialUrlFromHardwareProduct(product);
          return (
            <div className="rounded-md border border-emerald-400/20 bg-emerald-400/10 p-3" key={`local-source-${product.id}-${index}`}>
              <div className="flex items-center justify-between gap-2">
                <p className="truncate text-sm font-semibold text-slate-100">{product.label}</p>
                <StatusBadge label="本地 JSON" tone="success" />
              </div>
              <p className="mt-2 text-[11px] leading-4 text-emerald-100/85">
                本地事实库已收录硬件参数；官网页面作为来源链接保留，后续可由官网规格 MCP 复核。
              </p>
              {isExternalUrl(url) ? (
                <a className="mt-2 block truncate text-xs text-cyan-300 underline-offset-2 hover:underline" href={url} rel="noreferrer" target="_blank">
                  {url}
                </a>
              ) : (
                <p className="mt-2 text-xs text-slate-500">本地条目未提供官方 URL。</p>
              )}
            </div>
          );
        })}
        {records.map((item, index) => {
          const record = officialSpecPayload(item);
          const extra = asRecord(item);
          const url = asString(item.source_url) || asString(record.official_url);
          const missing = [...new Set([...asStrings(item.missing_fields), ...asStrings(record.missing_fields)])];
          const sourceCount = asNumber(extra.merged_source_count) ?? (url ? 1 : 0);
          const blocked = normalize(item.status) === "fetch_failed";
          const failed = normalize(item.status).includes("failed") || normalize(item.status).includes("error");
          return (
            <div className="rounded-md border border-slate-800 bg-slate-950/60 p-3" key={`source-${item.input || index}`}>
              <div className="flex items-center justify-between gap-2">
                <p className="truncate text-sm font-semibold text-slate-100">{officialSpecDisplayName(item, index)}</p>
                <StatusBadge label={officialSpecStatusLabel(item.status)} tone={officialSpecStatusTone(item.status)} />
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <StatusBadge
                  label={`可信度 ${CONFIDENCE_CN[normalize(officialSpecConfidence(item))] || officialSpecConfidence(item)}`}
                  tone={officialSpecConfidence(item) === "high" ? "success" : "warning"}
                />
                {sourceCount > 1 ? <StatusBadge label={`合并 ${sourceCount} 个来源`} tone="info" /> : null}
              </div>
              {isExternalUrl(url) ? (
                <a className="mt-2 block truncate text-xs text-cyan-300 underline-offset-2 hover:underline" href={url} rel="noreferrer" target="_blank">
                  {asString(item.source_domain) || url}
                </a>
              ) : (
                <p className="mt-2 text-xs text-slate-500">官网链接待联网搜索补齐</p>
              )}
              {blocked ? (
                <p className="mt-2 rounded border border-rose-400/30 bg-rose-500/10 px-2 py-1 text-[11px] leading-4 text-rose-200">
                  ⛔ 该来源被反爬拦截，没抓到页面（不是没有数据）；可换一个高可信来源或接入 Tavily extract 后重试。
                </p>
              ) : failed ? (
                <p className="mt-2 text-[11px] leading-4 text-rose-200/90">该来源抽取失败，未贡献字段。</p>
              ) : missing.length ? (
                <p className="mt-2 text-[11px] leading-4 text-amber-200/90">
                  页面已抓到，但其中没有这些字段（不是被拦截）：{missing.map(fieldLabel).join(" / ")}。可换含该参数的高可信来源补齐。
                </p>
              ) : (
                <p className="mt-2 text-[11px] leading-4 text-emerald-200/90">关键字段已从来源页面抽全。</p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ResearchAgentPlanningDetail({
  agent,
  status,
  trace,
  report,
  unresolvedProducts,
  externalProductCandidates,
}: {
  agent: AgentDefinition;
  status: AgentStatus;
  trace?: AgentTrace;
  report: Record<string, unknown>;
  unresolvedProducts: string[];
  externalProductCandidates: ExternalProductCandidate[];
}) {
  const productLabels = productLabelsFromReport(report, unresolvedProducts);
  const hardwareProducts = hardwareProductsFromReport(report);
  const localHardwareProducts = hardwareProducts.filter((product) => product.source === "local");
  const officialHardwareProducts = hardwareProducts.filter((product) => product.source === "official");
  const localHardwareAvailable = localHardwareProducts.length >= 2 && localHardwareProducts.every(hasUsefulHardware);
  const hardwareComparisonAvailable = hardwareProducts.length >= 2 && hardwareProducts.every(hasUsefulHardware);
  const officialCandidateCount = externalProductCandidates.filter(
    (item) =>
      item.candidate_status === "official_candidate_found" ||
      (item.official_candidates?.length ?? 0) > 0,
  ).length;
  const searchCandidateCount = externalProductCandidates.filter(
    (item) => (item.usable_candidate_count ?? 0) > 0,
  ).length;
  const searchMcpActive = externalProductCandidates.length > 0;
  const officialNeed = !localHardwareAvailable;
  const knownProductCount = localHardwareProducts.filter(hasUsefulHardware).length;
  const officialHardwareCount = officialHardwareProducts.filter(hasUsefulHardware).length;
  const reviewStatus = reviewIntelStatusFromReport(report);
  const reviewRecords = reviewIntelRecordsFromReport(report);
  const reviewCollected =
    asNumber(reviewStatus.collected_count) ??
    reviewRecords.filter((item) => reviewSignalEntries(item).length > 0).length;
  const reviewSignalCount = reviewRecords.reduce((sum, item) => sum + reviewSignalEntries(item).length, 0);
  const reviewSourceCount =
    asNumber(reviewStatus.source_count) ??
    reviewRecords.reduce((sum, item) => sum + asStrings(item.source_urls).length, 0);
  const reviewStatusValue = asString(reviewStatus.status) || (reviewRecords.length ? asString(reviewRecords[0]?.status) : "pending");
  const priceStatus = asRecord(report.price_status);
  const priceRecords = asRecords(report.price_records);
  const priceCollected =
    asNumber(priceStatus.collected_count) ??
    priceRecords.filter((item) => normalize(item.status) === "collected").length;
  const priceStatusValue = asString(priceStatus.status) || (priceRecords.length ? "partial" : "pending");
  const localHardwareStatus =
    localHardwareAvailable ? "ready" : knownProductCount > 0 ? "partial" : "missing";
  const targetDataCards = [
    {
      title: "官网识别 / 搜索 MCP",
      tone: officialCandidateCount > 0 ? "官网已识别" : searchMcpActive ? "已搜索" : officialNeed ? "待搜索" : "不需要",
      body:
        officialCandidateCount > 0
          ? `SearchMCP 只处理未命中的输入，已找到 ${officialCandidateCount} 个官网候选；本地命中产品不走搜索。`
          : searchCandidateCount > 0
            ? `SearchMCP 已找到 ${searchCandidateCount} 个可用候选，但仍需确认官方实体。`
            : officialNeed
              ? "本地未完整命中时会调用 SearchMCP 查找官网候选；找到候选前不生成硬件事实。"
              : "两款产品已由本地 JSON 命中，当前不需要搜索识别。"
    },
    {
      title: "硬件数据",
      tone:
        localHardwareStatus === "ready"
          ? "已采集"
          : localHardwareStatus === "partial"
            ? "部分命中"
            : officialCandidateCount > 0
              ? "待规格抽取"
              : "未命中",
      body: localHardwareAvailable
        ? "两款产品均命中本地 JSON，可直接读取重量、传感器、DPI、回报率、连接、续航、微动、点击系统、驱动与板载内存。"
        : hardwareComparisonAvailable
          ? `当前硬件对比由本地 JSON ${knownProductCount} 款 + 官网抽取 ${officialHardwareCount} 款组成；每个字段会标注来源和缺失原因。`
        : knownProductCount > 0
          ? `当前仅有 ${knownProductCount} 款产品命中本地事实库，未命中产品交给 SearchMCP / OfficialSpecMCP 识别并抽取。`
          : officialCandidateCount > 0
            ? "官网候选已识别，但还没有抽取到重量、DPI、回报率等规格字段；等待官网规格 MCP。"
            : "两款输入均未命中本地产品事实库，当前不能生成硬件参数对比或赢家判断，需要先交给搜索/官网 MCP 识别官方型号。",
    },
    {
      title: "官网规格核验",
      tone: officialHardwareCount > 0 ? "已采集" : officialCandidateCount > 0 ? "官网已识别" : officialNeed ? "待采集" : "暂不需要",
      body: officialNeed
        ? officialHardwareCount > 0
          ? `OfficialSpecMCP 已抽取 ${officialHardwareCount} 款非本地产品的硬件字段；未披露字段会显示原因，不当作本地事实。`
          : officialCandidateCount > 0
            ? "已找到官网候选页面，下一步由官网规格 MCP 抽取参数页、固件更新、驱动说明和地区版本差异。"
            : "用于确认官方型号、参数页、固件更新、驱动说明和地区版本差异；采集完成前不输出硬件赢家结论。"
        : "本地已有稳定硬件参数，官网规格只作为后续复核来源，不参与当前基础事实判断。",
    },
    {
      title: "评价与测评情报",
      tone: "pending",
      body: "用户口碑、博主测评、握法手感、游戏适配和长期可靠性目前不写死，后续由 ReviewIntel MCP 与 LLM 摘要补齐。",
    },
    {
      title: "实时价格",
      tone: "pending",
      body: "价格会随时间变化，当前只规划采集任务，不从本地 JSON 生成性价比结论。",
    },
  ];
  const liveTargetDataCards = targetDataCards.map((item, index) => {
    if (index === 3) {
      return {
        ...item,
        tone: reviewCollected > 0 ? `已采集 ${reviewCollected}/${reviewRecords.length || reviewCollected}` : reviewStatusLabel(reviewStatusValue),
        body:
          reviewCollected > 0
            ? `ReviewIntelMCP 已通过真实搜索和 LLM 抽取 ${reviewSignalCount} 条体验/口碑信号，覆盖 ${reviewSourceCount} 个来源；这些结论会进入 Evidence、Analysis 与 Verification。`
            : `${reviewStatusLabel(reviewStatusValue)}：${asString(reviewStatus.note) || "未生成体验结论；不会用规则假数据替代真实测评抽取。"}`,
      };
    }
    if (index === 4) {
      return {
        ...item,
        tone: priceCollected > 0 ? `已采集 ${priceCollected}/${priceRecords.length || priceCollected}` : priceStatusValue,
        body:
          priceCollected > 0
            ? `PriceMCP 已采集实时价格线索；官方价、零售/搜索价会按可信度进入 Evidence 和 Analysis，弱来源会降低报告可信度。`
            : `${priceStatusValue}：${asString(priceStatus.note) || "当前没有可用于性价比判断的实时价格证据。"}`,
      };
    }
    return item;
  });
  const handoffCards = [
    "CollectorAgent：先查本地事实库；未命中时生成搜索/官网 MCP 待采集任务。",
    "EvidenceAgent：把硬件事实、来源状态和待补项整理成可追溯 evidence。",
    "AnalysisAgent：只分析有 evidence 支撑的硬件差异，不提前输出体验结论。",
    "QualityAgent：检查 pending 是否披露、结论是否都有证据支撑。",
  ];
  const researchQuestion = localHardwareAvailable
    ? "本次先确认两款电竞鼠标的可验证硬件事实差异，再规划外部数据采集：官网规格用于复核参数，用户评价和博主测评用于体验判断，实时价格用于后续性价比分析。"
    : hardwareComparisonAvailable
      ? `本次采用混合来源：本地 JSON 命中 ${knownProductCount} 款，官网规格抽取 ${officialHardwareCount} 款；后续评价测评和实时价格仍等待 MCP。`
    : officialCandidateCount > 0
      ? "本次已通过 SearchMCP 找到官网候选；下一步需要官网规格 MCP 从候选页面抽取硬件参数，再进入评价测评、实时价格和质量校验。"
    : "本次先把两个输入作为待识别产品处理：先规划搜索/官网 MCP 确认官方型号和硬件参数，再进入评价测评、实时价格和质量校验；采集完成前不生成硬件赢家或最终推荐。";
  const researchSummary = localHardwareAvailable
    ? (trace?.output_summary || "已规划本地事实读取、官网复核、评价测评、实时价格与质量校验任务。")
    : hardwareComparisonAvailable
      ? (trace?.output_summary || "已形成混合硬件事实：本地 JSON + 官网规格 MCP，缺失字段将显示原因。")
    : officialCandidateCount > 0
      ? (trace?.output_summary || "SearchMCP 已返回官网候选，硬件规格字段等待官网规格 MCP 抽取。")
    : (trace?.output_summary || "本地事实库未完整命中，已规划搜索/官网 MCP 识别、规格补齐、评价测评和价格采集任务。");
  const reviewAttempted = reviewRecords.length > 0 || (Boolean(reviewStatusValue) && reviewStatusValue !== "pending");
  const reviewHasData = reviewCollected > 0 || reviewSignalCount > 0;
  const priceCollectedCount = priceCollected;
  const priceAttempted = priceRecords.length > 0;

  const researchRequirements = RESEARCH_REQUIREMENTS.map((item) => {
    if (item.name === "硬件数据") {
      return {
        ...item,
        status: hardwareComparisonAvailable ? "complete" : "pending",
        summary: localHardwareAvailable
          ? "本地 JSON 已命中两款产品，当前可以展示硬件事实；官网规格后续仅用于复核。"
          : hardwareComparisonAvailable
            ? "本地 JSON 与官网规格 MCP 已共同形成硬件对比；缺失字段显示具体原因。"
          : officialCandidateCount > 0
            ? "SearchMCP 已找到官网候选，但硬件参数字段尚未抽取；等待官网规格 MCP 后再生成硬件对比。"
          : "本地 JSON 未完整命中两款产品，硬件参数、官方型号和赢家判断都等待搜索/官网 MCP 采集后再生成。",
      };
    }
    if (item.name === "实时价格与可买性") {
      const status = priceCollectedCount >= 2 ? "complete" : priceCollectedCount > 0 ? "partial" : priceAttempted ? "no_data" : "pending";
      return {
        ...item,
        status,
        summary:
          priceCollectedCount > 0
            ? `Price MCP 已采集 ${priceCollectedCount} 款产品的实时价格（官方价 / 电商价，详见 Collector 与证据）。`
            : priceAttempted
              ? "Price MCP 已接入并尝试采集，但本轮未抓到可用价格（官方页反爬 / 来源有限）。"
              : "Price MCP 待采集实时价格。",
      };
    }
    if (item.name === "用户评价与电商评论" || item.name === "博主测评与体验口碑") {
      const status = reviewHasData ? (reviewCollected >= 2 ? "complete" : "partial") : reviewAttempted ? "no_data" : "pending";
      return {
        ...item,
        status,
        summary: reviewHasData
          ? `ReviewIntel MCP 已抽取 ${reviewCollected}/${reviewRecords.length || reviewCollected} 款产品的测评 / 口碑信号。`
          : reviewAttempted
            ? "ReviewIntel MCP 已接入并尝试抓取，但因评测页反爬 / 视频无开放 API / LLM 抽取超时，本轮未抓到可用内容。"
            : "等待 ReviewIntel MCP 采集真实评论。",
      };
    }
    return item;
  });

  return (
    <section className="rounded-lg border border-cyan-300/25 bg-slate-950/75 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">
            Research Plan
          </p>
          <h3 className="mt-2 text-2xl font-semibold text-white">{agent.name}</h3>
          <p className="mt-1 text-sm text-slate-400">
            调研规划员：把用户输入拆成可执行的数据任务，明确哪些本地已有、哪些需要后续 MCP 补齐。
          </p>
        </div>
        <StatusBadge label={STATUS_LABEL[status]} tone={STATUS_TONE[status]} />
      </div>

      <div className="mt-5 rounded-lg border border-amber-400/30 bg-amber-400/10 px-4 py-3 text-sm leading-6 text-amber-100">
        ResearchAgent 不做最终推荐，不判断谁更适合；它只规划数据需求。用户评价、博主测评、
        实时价格和长期可靠性如果尚未采集，会标记为待 MCP；已采集的数据会直接进入 Evidence、Analysis 与 Verification。
      </div>

      <div className="mt-5 grid gap-4">
        <div className="h-fit rounded-lg border border-slate-800 bg-slate-900/45 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                Research Target
              </p>
              <h4 className="mt-2 text-lg font-semibold text-white">本次调研目标</h4>
            </div>
            <StatusBadge label="planning only" tone="info" />
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {productLabels.map((label, index) => (
              <div className="rounded-md border border-slate-800 bg-slate-950/60 p-3" key={label}>
                <p className="text-xs uppercase tracking-[0.16em] text-slate-500">
                  产品 {index === 0 ? "A" : "B"}
                </p>
                <p className="mt-2 text-sm font-semibold text-slate-100">{label}</p>
              </div>
            ))}
          </div>
          <div className="mt-4 rounded-md border border-slate-800 bg-slate-950/60 p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
              Research Question
            </p>
            <p className="mt-2 text-sm leading-6 text-slate-200">
              {researchQuestion}
            </p>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {liveTargetDataCards.map((item) => (
              <article
                className="rounded-md border border-slate-800 bg-slate-950/60 p-3"
                key={item.title}
              >
                <div className="flex items-start justify-between gap-3">
                  <h5 className="text-sm font-semibold text-slate-100">{item.title}</h5>
                  <span className="rounded-full border border-cyan-300/25 bg-cyan-300/10 px-2 py-0.5 text-xs font-semibold text-cyan-100">
                    {item.tone}
                  </span>
                </div>
                <p className="mt-2 text-xs leading-5 text-slate-400">{item.body}</p>
              </article>
            ))}
          </div>
          <div className="mt-4 rounded-md border border-slate-800 bg-slate-950/60 p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
              Handoff
            </p>
            <div className="mt-3 grid gap-2 md:grid-cols-2">
              {handoffCards.map((item) => (
                <div className="rounded-md border border-slate-800/80 bg-slate-900/50 px-3 py-2 text-xs leading-5 text-slate-300" key={item}>
                  {item}
                </div>
              ))}
            </div>
          </div>
          <p className="mt-4 text-sm leading-6 text-slate-400">
            当前计划摘要：{researchSummary}
          </p>
        </div>
      </div>

      <div className="mt-5 grid gap-4 xl:grid-cols-2">
        <div className="rounded-lg border border-slate-800 bg-slate-900/45 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                Requirement Matrix
              </p>
              <h4 className="mt-2 text-lg font-semibold text-white">数据需求矩阵</h4>
            </div>
            <StatusBadge label="pending 不等于失败" tone="warning" />
          </div>
          <div className="mt-4 space-y-3">
            {researchRequirements.map((item) => (
              <article
                className="rounded-md border border-slate-800 bg-slate-950/55 p-3 transition hover:border-cyan-300/40"
                key={item.name}
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <h5 className="font-semibold text-slate-100">{item.name}</h5>
                      <StatusBadge label={requirementMeta(item.status).label} tone={requirementMeta(item.status).tone} />
                    </div>
                    <p className="mt-1 text-xs text-slate-500">{item.owner}</p>
                  </div>
                  <StatusBadge
                    label={requirementMeta(item.status).second}
                    tone={requirementMeta(item.status).tone}
                  />
                </div>
                <p className="mt-3 text-sm leading-6 text-slate-400">{item.summary}</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {item.fields.slice(0, 6).map((field) => (
                    <span
                      className="rounded-full border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-300"
                      key={field}
                    >
                      {field}
                    </span>
                  ))}
                </div>
              </article>
            ))}
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded-lg border border-slate-800 bg-slate-900/45 p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
              Source Priority
            </p>
            <h4 className="mt-2 text-lg font-semibold text-white">数据来源优先级</h4>
            <div className="mt-4 space-y-3">
              {SOURCE_PRIORITIES.map((source) => (
                <div className="grid gap-3 rounded-md border border-slate-800 bg-slate-950/55 p-3 sm:grid-cols-[56px_1fr]" key={source.level}>
                  <div className="flex h-10 w-10 items-center justify-center rounded-full border border-cyan-300/35 bg-cyan-400/10 text-sm font-semibold text-cyan-100">
                    {source.level}
                  </div>
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-semibold text-slate-100">{source.name}</p>
                      <StatusBadge label={source.credibility} tone={source.level === "P3" ? "warning" : "success"} />
                    </div>
                    <p className="mt-1 text-sm leading-6 text-slate-400">{source.usage}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-lg border border-slate-800 bg-slate-900/45 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                  Handoff
                </p>
                <h4 className="mt-2 text-lg font-semibold text-white">交给后续 Agent 的任务包</h4>
              </div>
              <StatusBadge label={`${RESEARCH_HANDOFFS.length} tasks`} tone="info" />
            </div>
            <div className="mt-4 space-y-3">
              {RESEARCH_HANDOFFS.map((handoff, index) => (
                <div className="flex gap-3 rounded-md border border-slate-800 bg-slate-950/55 p-3" key={handoff.agent}>
                  <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-cyan-300/35 text-xs font-semibold text-cyan-100">
                    {index + 1}
                  </span>
                  <div>
                    <p className="font-semibold text-slate-100">{handoff.agent}</p>
                    <p className="mt-1 text-sm leading-6 text-slate-400">{handoff.task}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

    </section>
  );
}

// ---------------------------------------------------------------------------
// 其余 Agent 详情面板：尽量读取工作流已产出的真实数据；MCP 未接入的部分标记为待采集，
// AnalysisAgent 的 SWOT / AI 解读区预留给 LLM 阶段（不填假数据）。
// ---------------------------------------------------------------------------

type AgentDetailProps = {
  taskId?: string;
  agent: AgentDefinition;
  status: AgentStatus;
  trace?: AgentTrace;
  report: Record<string, unknown>;
  evidenceList: Record<string, unknown>[];
  claims: Claim[];
  resolvedProducts: Record<string, unknown>[];
  unresolvedProducts: string[];
  searchMcpResults: SearchMcpResult[];
  externalProductCandidates: ExternalProductCandidate[];
  quality?: QualityResult;
  onNavigate?: (key: string) => void;
  onDataChanged?: () => void;
};

const MATCH_BY_LABEL: Record<string, string> = {
  id: "产品 ID",
  model: "官方型号",
  alias: "别名",
  community_alias: "玩家简称",
  family: "系列",
  brand: "品牌",
};

const SOURCE_TYPE_LABEL: Record<string, string> = {
  official: "官方",
  news: "新闻",
  review: "测评",
  report: "报告 / 财报",
  ecommerce: "电商",
  user_review: "用户评论",
};

const CREDIBILITY_LABEL: Record<string, string> = {
  high: "高可信",
  medium: "中可信",
  low: "低可信",
};

const QUALITY_CHECK_LABEL: Record<string, string> = {
  all_claims_have_evidence: "结论都有证据",
  all_evidence_ids_valid: "引用证据有效",
  all_claims_faithful: "结论忠实(无幻觉)",
  all_matrix_claims_faithful: "矩阵数字可溯源",
  all_competitors_covered: "竞品全覆盖",
  all_dimensions_covered: "维度覆盖",
  missing_dimensions_disclosed: "缺口已披露",
  product_matrix_not_empty: "产品矩阵非空",
  business_matrix_not_empty: "商业矩阵非空",
  no_high_severity_risk: "无高危风险",
  high_severity_risk_disclosed: "高危风险已披露",
};

const LIMITATION_COPY: Record<string, { label: string; detail: string; tone: Tone }> = {
  external_data_pending: {
    label: "外部数据仍在补齐",
    detail: "用户评价、博主测评或实时价格尚未形成完整证据链，报告可信度会被下调。",
    tone: "warning",
  },
  weak_price_support: {
    label: "价格证据偏弱",
    detail: "官网价格可能被反爬拦截，或只能使用搜索/电商等低可信来源，性价比结论需要保守处理。",
    tone: "warning",
  },
  weak_review_support: {
    label: "测评口碑证据偏弱",
    detail: "体验类结论依赖测评和用户反馈；来源不足时只能披露趋势，不能当作强推荐依据。",
    tone: "warning",
  },
  human_feedback_unverified: {
    label: "人工反馈待外部验证",
    detail: "人工输入已经进入校验链路，但不能自证为事实；需要官网、测评或用户评价等外部 evidence 支撑后才能进入强结论。",
    tone: "danger",
  },
};

function credibilityTone(value: string): Tone {
  const key = normalize(value);
  if (key === "high") return "success";
  if (key === "medium") return "info";
  if (key === "low") return "warning";
  return "neutral";
}

function isExternalUrl(url: string): boolean {
  return /^https?:\/\//i.test(url);
}

function asStrings(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => asString(item)).filter(Boolean) : [];
}

function candidateStatusTone(status: string): Tone {
  const value = normalize(status);
  if (value === "official_candidate_found") return "success";
  if (value === "review_candidate_found") return "info";
  if (value.includes("low_confidence") || value.includes("off_category")) return "warning";
  if (value.includes("error") || value.includes("rate_limited")) return "danger";
  return "neutral";
}

function candidateStatusLabel(status: string): string {
  const value = normalize(status);
  const labels: Record<string, string> = {
    official_candidate_found: "官网已识别",
    review_candidate_found: "测评候选",
    low_confidence_candidates: "低可信候选",
    off_category_suspected: "疑似非鼠标",
    no_candidates: "未找到候选",
    mcp_not_connected: "未连接",
    mcp_not_configured: "未配置",
    mcp_error: "调用异常",
    mcp_http_error: "请求异常",
    rate_limited: "限流",
  };
  return labels[value] || asString(status, "候选");
}

function AgentDetailFrame({
  agent,
  status,
  eyebrow,
  description,
  children,
}: {
  agent: AgentDefinition;
  status: AgentStatus;
  eyebrow: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-lg border border-cyan-300/25 bg-slate-950/75 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">{eyebrow}</p>
          <h3 className="mt-2 text-2xl font-semibold text-white">{agent.name}</h3>
          <p className="mt-1 text-sm text-slate-400">{description}</p>
        </div>
        <StatusBadge label={STATUS_LABEL[status]} tone={STATUS_TONE[status]} />
      </div>
      <div className="mt-5 grid gap-4">{children}</div>
    </section>
  );
}

function StatTile({ label, value, tone = "neutral" }: { label: string; value: ReactNode; tone?: Tone }) {
  const toneText =
    tone === "success"
      ? "text-emerald-200"
      : tone === "warning"
        ? "text-amber-200"
        : tone === "danger"
          ? "text-rose-200"
          : tone === "info"
            ? "text-cyan-200"
            : "text-slate-100";
  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/60 p-3 text-center">
      <p className={`text-2xl font-semibold ${toneText}`}>{value}</p>
      <p className="mt-1 text-xs text-slate-500">{label}</p>
    </div>
  );
}

function EmptyAgentNote({ label }: { label: string }) {
  return (
    <div className="rounded-md border border-dashed border-slate-700 bg-slate-950/60 p-4 text-sm leading-6 text-slate-500">
      {label}
    </div>
  );
}

type CompareSlot = {
  label: string;
  resolved: boolean;
  specs?: Record<string, unknown>;
  source?: HardwareProductSource;
  sourceLabel?: string;
  collectionStatus?: string;
  missingFields?: string[];
};

type CollectorIdentityCard =
  | {
      type: "local";
      input: string;
      title: string;
      matchedBy: string;
      matchedValue: string;
      confidence: string;
      clickSystem: string;
      aliasWarning: string;
      disambiguation: string;
    }
  | {
      type: "search";
      input: string;
      title: string;
      url: string;
      domain: string;
      candidateStatus: string;
    };

function CollectorCompareTable({ slots }: { slots: CompareSlot[] }) {
  const cols = "grid-cols-[120px_minmax(0,1fr)_minmax(0,1fr)]";
  return (
    <div className="overflow-hidden rounded-md border border-slate-800 bg-slate-950/70">
      <div className={`grid ${cols} border-b border-slate-800 bg-slate-900/70 text-xs font-semibold uppercase tracking-[0.12em] text-slate-500`}>
        <div className="p-3">字段</div>
        {slots.map((slot, index) => (
          <div className="min-w-0 p-3" key={index}>
            <span className="block truncate text-slate-300">{slot.label}</span>
            <span
              className={`mt-1 inline-block rounded-full px-2 py-0.5 text-[10px] ${
                slot.resolved
                  ? slot.source === "official"
                    ? "bg-cyan-400/10 text-cyan-200"
                    : "bg-emerald-400/10 text-emerald-200"
                  : "bg-amber-400/10 text-amber-200"
              }`}
            >
              {slot.resolved ? slot.sourceLabel || "已识别" : "本地未收录"}
            </span>
          </div>
        ))}
      </div>
      {HARDWARE_FIELDS.map((field) => (
        <div className={`grid ${cols} border-b border-slate-800/80 last:border-b-0`} key={field.key}>
          <div className="p-3 text-xs text-slate-500">{field.label}</div>
          {slots.map((slot, index) => (
            <div className="min-w-0 break-words p-3 text-sm" key={index}>
              {slot.resolved && slot.specs ? (
                <span className={hasHardwareFieldValue(slot.specs, field.key) ? "text-slate-200" : "text-amber-300/85"}>
                  {hardwareDisplayValue(
                    {
                      id: `${slot.label}-${index}`,
                      label: slot.label,
                      specs: slot.specs,
                      source: slot.source || "local",
                      sourceLabel: slot.sourceLabel || "本地 JSON",
                      collectionStatus: slot.collectionStatus,
                      missingFields: slot.missingFields || [],
                    },
                    field,
                  )}
                </span>
              ) : (
                <span className="text-amber-300/80">本地未收录</span>
              )}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

function ExternalCandidateTable({ items }: { items: ExternalProductCandidate[] }) {
  if (!items.length) return null;
  return (
    <div className="overflow-hidden rounded-md border border-slate-800 bg-slate-950/70">
      <div className="grid grid-cols-[150px_minmax(0,1.4fr)_150px_minmax(0,1fr)] border-b border-slate-800 bg-slate-900/70 text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
        <div className="p-3">输入</div>
        <div className="p-3">官网候选</div>
        <div className="p-3">网站</div>
        <div className="p-3">下一步</div>
      </div>
      {items.map((item, index) => {
        const best = item.best_candidate || item.official_candidates?.[0] || item.review_candidates?.[0];
        const url = asString(best?.url);
        const title = asString(best?.title, "暂无候选");
        const domain = asString(best?.domain, "—");
        const status = asString(item.candidate_status, "pending");
        return (
          <div
            className="grid grid-cols-[150px_minmax(0,1.4fr)_150px_minmax(0,1fr)] border-b border-slate-800/80 last:border-b-0"
            key={`${item.original_input || index}-${status}`}
          >
            <div className="min-w-0 p-3 text-sm font-semibold text-slate-200">{asString(item.original_input, `产品 ${index + 1}`)}</div>
            <div className="min-w-0 p-3 text-sm">
              {isExternalUrl(url) ? (
                <a className="block truncate text-cyan-300 underline-offset-2 hover:underline" href={url} rel="noreferrer" target="_blank">
                  {title}
                </a>
              ) : (
                <span className="block truncate text-slate-400">{title}</span>
              )}
              <div className="mt-1">
                <StatusBadge
                  label={candidateStatusLabel(status)}
                  tone={candidateStatusTone(status)}
                />
              </div>
            </div>
            <div className="min-w-0 p-3 text-sm text-slate-300">{domain}</div>
            <div className="min-w-0 p-3 text-xs leading-5 text-slate-400">
              {asString(item.next_action, item.consumable_by_next_agent ? "交给官网规格 MCP" : "等待进一步确认")}
            </div>
          </div>
        );
      })}
    </div>
  );
}

const PRICE_STATUS_LABEL: Record<string, string> = {
  collected: "已采集",
  partial: "部分采集",
  available: "已采集",
  no_price_found: "未找到价格",
  no_sources: "无可用来源",
  mcp_not_configured: "MCP 未配置",
  llm_failed: "抽取失败",
  pending: "待采集",
};

const PRICE_SOURCE_LABEL: Record<string, string> = {
  official_store: "官方店",
  retailer: "零售商",
  search_snippet: "搜索摘要",
};

function currencySymbol(currency: string): string {
  const c = currency.toUpperCase();
  if (c === "CNY" || c === "RMB") return "¥";
  if (c === "EUR") return "€";
  if (c === "GBP") return "£";
  return "$";
}

function priceText(value: unknown, sym: string): string {
  const n = asNumber(value);
  return typeof n === "number" ? `${sym}${n}` : "—";
}

function priceDomainIsWeak(domainOrUrl: string): boolean {
  const text = domainOrUrl.toLowerCase();
  return ["youtube.com", "youtu.be", "bilibili.com", "tiktok.com", "reddit.com"].some((domain) => text.includes(domain));
}

function reliablePriceQuotes(record: Record<string, unknown>): Record<string, unknown>[] {
  return asRecords(record.quotes).filter((quote) => {
    const type = normalize(quote.source_type);
    const url = asString(quote.source_url);
    const domain = asString(quote.source_domain) || asString(quote.retailer) || url;
    return Boolean(asNumber(quote.price)) && !priceDomainIsWeak(domain) && ["official_store", "retailer", "search_snippet"].includes(type);
  });
}

function priceQuoteIsOfficial(quote?: Record<string, unknown>): boolean {
  return normalize(quote?.source_type) === "official_store";
}

function priceQuoteIsLowConfidence(quote?: Record<string, unknown>): boolean {
  return Boolean(quote) && !priceQuoteIsOfficial(quote);
}

function priceQuoteDisplayLabel(quote?: Record<string, unknown>): string {
  if (!quote) return "未采集";
  return priceQuoteIsOfficial(quote) ? "官方价" : "低可信电商/搜索价";
}

function priceQuoteTone(quote?: Record<string, unknown>): Tone {
  if (!quote) return "neutral";
  return priceQuoteIsOfficial(quote) ? "success" : "warning";
}

function fallbackPriceLinks(record: Record<string, unknown>): Record<string, unknown>[] {
  const links = asRecords(record.fallback_links);
  const weakQuotes = asRecords(record.quotes)
    .filter((quote) => priceDomainIsWeak(asString(quote.source_url) || asString(quote.source_domain)))
    .map((quote) => ({
      title: asString(quote.retailer) || asString(quote.source_domain) || "fallback source",
      url: asString(quote.source_url),
      domain: asString(quote.source_domain) || asString(quote.retailer),
      confidence: "low",
    }));
  return [...links, ...weakQuotes].filter((item) => asString(item.url)).slice(0, 3);
}

function priceRecordLabel(record: Record<string, unknown>, index = 0): string {
  return [asString(record.brand), asString(record.model)].filter(Boolean).join(" ") || asString(record.input) || `产品 ${index + 1}`;
}

function PriceMcpSection({
  records,
  status,
}: {
  records: Record<string, unknown>[];
  status: Record<string, unknown>;
}) {
  if (!records.length) return null;
  const collected = records.filter((item) => reliablePriceQuotes(item).length > 0).length;
  const priceConfidence = normalize(status.price_confidence);

  return (
    <div className="rounded-lg border border-cyan-300/25 bg-slate-900/45 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Price MCP</p>
          <h4 className="mt-2 text-lg font-semibold text-white">实时价格抽取</h4>
          <p className="mt-1 text-xs leading-5 text-slate-400">
            联网搜索 + 大模型从商店 / 官网页抽取当前售价；官方价抓不到时退而用其他高可信来源（标低可信，并下调报告可信度）。
          </p>
        </div>
        <StatusBadge label={`已采集 ${collected}/${records.length}`} tone={collected === records.length ? "success" : "warning"} />
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        {records.map((record, index) => {
          const summary = asRecord(record.price_summary);
          const currency = asString(record.currency) || asString(summary.currency) || "USD";
          const sym = currencySymbol(currency);
          const blocked = Boolean(record.official_price_blocked);
          const confidence = normalize(record.confidence_level);
          const official = asNumber(summary.official_price);
          const quotes = reliablePriceQuotes(record).slice(0, 4);
          const fallbackLinks = fallbackPriceLinks(record);
          const blockedDomains = asRecords(record.blocked_sources)
            .map((item) => asString(item.domain))
            .filter(Boolean);
          const model = priceRecordLabel(record, index);
          const showSampleStats = quotes.length > 1;
          const primaryQuote = quotes[0];
          const primaryPrice = typeof official === "number" ? official : asNumber(primaryQuote?.price);
          const primaryLabel = typeof official === "number" ? "官方价" : priceQuoteDisplayLabel(primaryQuote);
          return (
            <div className="rounded-md border border-slate-800 bg-slate-950/60 p-3" key={`${asString(record.input) || index}`}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="truncate text-sm font-semibold text-slate-100">{model}</p>
                <div className="flex flex-wrap gap-1.5">
                  <StatusBadge
                    label={PRICE_STATUS_LABEL[normalize(record.status)] || asString(record.status, "待采集")}
                    tone={normalize(record.status) === "collected" ? "success" : "warning"}
                  />
                  {normalize(record.status) === "collected" ? (
                    <StatusBadge
                      label={confidence === "high" ? "高可信" : "低可信"}
                      tone={confidence === "high" ? "success" : "warning"}
                    />
                  ) : null}
                </div>
              </div>

              <div className={`mt-3 grid gap-2 ${showSampleStats ? "grid-cols-3" : "grid-cols-1"}`}>
                <StatTile
                  label={primaryLabel}
                  value={blocked && typeof primaryPrice !== "number" ? "被拦截" : priceText(primaryPrice, sym)}
                  tone={blocked && typeof primaryPrice !== "number" ? "danger" : typeof primaryPrice === "number" ? (typeof official === "number" ? "success" : priceQuoteTone(primaryQuote)) : "neutral"}
                />
                {showSampleStats ? (
                  <>
                    <StatTile label="样本中位价" value={priceText(summary.median_price, sym)} tone="info" />
                    <StatTile label="最低采集价" value={priceText(summary.lowest_price, sym)} tone="neutral" />
                  </>
                ) : null}
              </div>

              {blocked ? (
                <p className="mt-2 rounded border border-rose-400/30 bg-rose-500/10 px-2 py-1 text-[11px] leading-4 text-rose-200">
                  ⛔ 官方价被反爬拦截{blockedDomains.length ? `（${blockedDomains.join("、")}）` : ""}；非官方电商/搜索价会标为低可信，视频/测评链接只作为弱支撑。
                </p>
              ) : null}

              {quotes.length ? (
                <div className="mt-2 space-y-1">
                  {quotes.map((quote, qi) => {
                    const url = asString(quote.source_url);
                    const retailer = asString(quote.retailer) || asString(quote.source_domain);
                    return (
                      <div className="flex items-center justify-between gap-2 rounded border border-slate-800/80 bg-slate-900/40 px-2 py-1 text-[11px]" key={qi}>
                        <span className="font-semibold text-slate-200">
                          {sym}
                          {asNumber(quote.price) ?? "—"}
                        </span>
                        <span className="min-w-0 flex-1 truncate text-slate-400">
                          {isExternalUrl(url) ? (
                            <a className="text-cyan-300 underline-offset-2 hover:underline" href={url} rel="noreferrer" target="_blank">
                              {retailer || "来源"}
                            </a>
                          ) : (
                            retailer || "来源"
                          )}
                        </span>
                        <StatusBadge
                          label={PRICE_SOURCE_LABEL[normalize(quote.source_type)] || asString(quote.source_type, "—")}
                          tone={priceQuoteIsLowConfidence(quote) ? "warning" : "neutral"}
                        />
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="mt-2 text-[11px] leading-4 text-slate-500">未抽到该产品的有效报价。</p>
              )}
              {fallbackLinks.length ? (
                <div className="mt-2 space-y-1 rounded border border-amber-400/25 bg-amber-400/10 p-2">
                  <p className="text-[11px] font-semibold text-amber-100">弱支撑来源（不计入价格）</p>
                  {fallbackLinks.map((link, li) => {
                    const url = asString(link.url);
                    const domain = asString(link.domain) || asString(link.title) || "fallback";
                    return (
                      <div className="flex items-center justify-between gap-2 text-[11px]" key={`${url}-${li}`}>
                        {isExternalUrl(url) ? (
                          <a className="min-w-0 flex-1 truncate text-cyan-300 underline-offset-2 hover:underline" href={url} rel="noreferrer" target="_blank">
                            {domain}
                          </a>
                        ) : (
                          <span className="min-w-0 flex-1 truncate text-slate-400">{domain}</span>
                        )}
                        <StatusBadge label="弱支撑" tone="warning" />
                      </div>
                    );
                  })}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>

      {priceConfidence === "low" ? (
        <p className="mt-3 rounded-md border border-amber-400/25 bg-amber-400/10 px-3 py-2 text-[11px] leading-4 text-amber-100">
          价格仅来自低可信来源 / 官方价被反爬拦截，<strong>报告可信度分已据此下调</strong>。
        </p>
      ) : null}
    </div>
  );
}

const REVIEW_SOURCE_KIND_LABEL: Record<string, string> = {
  review_site: "评测站",
  creator_review: "视频测评",
  community_review: "社区讨论",
  ecommerce_review: "电商评论",
  search_result: "搜索结果",
};

const REVIEW_FETCH_METHOD_LABEL: Record<string, string> = {
  reader: "正文代理抓取",
  direct: "直连抓取",
  reddit_json: "Reddit 接口",
  cache: "命中缓存",
  snippet_only: "仅搜索摘要",
  local_database: "本地数据库",
};

// 两条 demo 路线：本地评价数据库（命中即时读取）vs 实时爬取（ReviewIntel MCP）
function reviewRouteMeta(record: ReviewIntelRecord): { label: string; tone: Tone; sub: string } {
  const route = asString(record.source_route) || asString(record.extraction_method);
  if (route === "local_database") {
    return { label: "本地评价数据库", tone: "success", sub: "命中本地结构化评价库 · 即时读取" };
  }
  if (route === "rule_fallback") {
    return { label: "实时爬取", tone: "info", sub: "ReviewIntel MCP · 规则兜底抽取" };
  }
  return { label: "实时爬取", tone: "info", sub: `ReviewIntel MCP · ${asString(record.llm_model) || "LLM 抽取"}` };
}

function mergeCountMaps(maps: Array<Record<string, number> | undefined>): Array<[string, number]> {
  const merged: Record<string, number> = {};
  for (const map of maps) {
    if (!map) continue;
    for (const [key, value] of Object.entries(map)) {
      if (typeof value === "number" && value > 0) merged[key] = (merged[key] || 0) + value;
    }
  }
  return Object.entries(merged).sort((a, b) => b[1] - a[1]);
}

function ReviewIntelMcpSection({
  records,
  status,
}: {
  records: ReviewIntelRecord[];
  status: Record<string, unknown>;
}) {
  if (!records.length && !Object.keys(status).length) return null;
  const collected = asNumber(status.collected_count) ?? records.filter((item) => reviewSignalEntries(item).length > 0).length;
  const sourceCount = asNumber(status.source_count) ?? records.reduce((sum, item) => sum + asStrings(item.source_urls).length, 0);
  const statusValue = asString(status.status) || (records.length ? asString(records[0]?.status) : "pending");
  const sourceKindCounts = mergeCountMaps(records.map((item) => item.source_summary));
  const fetchMethodCounts = mergeCountMaps(records.map((item) => item.fetch_summary));

  return (
    <div className="rounded-lg border border-cyan-300/25 bg-slate-900/45 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">ReviewIntel MCP</p>
          <h4 className="mt-2 text-lg font-semibold text-white">评价 / 测评抽取结果</h4>
          <p className="mt-1 text-xs leading-5 text-slate-400">
            两条路线并存：命中<span className="text-emerald-300">本地评价数据库</span>的产品（如 GPX / GPX2）直接读取已结构化的博主测评 / 用户评价；未命中的产品走<span className="text-cyan-300">实时爬取</span>——SearchMCP 找到测评/社区/视频/电商来源后由 LLM 抽取握感、适合场景、驱动口碑和长期可靠性，没有真实抽取时不编造结论。
          </p>
        </div>
        <StatusBadge
          label={collected > 0 ? `已采集 ${collected}/${records.length || collected}` : reviewStatusLabel(statusValue)}
          tone={collected > 0 ? "success" : reviewStatusTone(statusValue)}
        />
      </div>

      {(sourceKindCounts.length > 0 || fetchMethodCounts.length > 0) && (
        <div className="mt-3 grid gap-2 rounded-md border border-slate-800/70 bg-slate-950/40 p-3 sm:grid-cols-2">
          {sourceKindCounts.length > 0 && (
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">来源构成</p>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {sourceKindCounts.map(([kind, count]) => (
                  <StatusBadge key={kind} label={`${REVIEW_SOURCE_KIND_LABEL[kind] || kind} ×${count}`} tone="neutral" />
                ))}
              </div>
            </div>
          )}
          {fetchMethodCounts.length > 0 && (
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">正文获取方式</p>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {fetchMethodCounts.map(([method, count]) => (
                  <StatusBadge
                    key={method}
                    label={`${REVIEW_FETCH_METHOD_LABEL[method] || method} ×${count}`}
                    tone={method === "snippet_only" ? "warning" : "info"}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {records.length ? (
        <div className="mt-3 grid gap-3 lg:grid-cols-2">
          {records.map((record, index) => {
            const signals = reviewSignalEntries(record);
            const urls = asStrings(record.source_urls);
            const limitations = asStrings(record.limitations);
            return (
              <article className="rounded-md border border-slate-800 bg-slate-950/60 p-3" key={`${reviewRecordLabel(record, index)}-${index}`}>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="text-sm font-semibold text-slate-100">{reviewRecordLabel(record, index)}</p>
                    <p className="mt-1 text-xs text-slate-500">{reviewRouteMeta(record).sub}</p>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    <StatusBadge label={reviewRouteMeta(record).label} tone={reviewRouteMeta(record).tone} />
                    <StatusBadge label={reviewStatusLabel(record.status)} tone={reviewStatusTone(record.status)} />
                    <StatusBadge label={localizedConfidence(record.confidence_level)} tone={credibilityTone(asString(record.confidence_level))} />
                  </div>
                </div>

                {signals.length ? (
                  <div className="mt-3 space-y-2">
                    {signals.slice(0, 7).map(([dimension, signal]) => {
                      const corroboration = asNumber(signal.corroborating_sources) ?? 0;
                      return (
                      <div className="rounded border border-slate-800/80 bg-slate-900/45 px-2 py-2" key={dimension}>
                        <div className="flex flex-wrap items-center gap-2">
                          <StatusBadge label={reviewDimensionLabel(dimension)} tone="info" />
                          <StatusBadge label={localizedConfidence(signal.confidence)} tone={credibilityTone(asString(signal.confidence))} />
                          <StatusBadge label={localizedSentiment(signal.sentiment)} tone="neutral" />
                          {corroboration >= 2 && (
                            <StatusBadge label={`${corroboration} 来源印证`} tone="success" />
                          )}
                          {asStrings(signal.evidence_ids).map((id) => (
                            <StatusBadge key={id} label={id} tone="neutral" />
                          ))}
                        </div>
                        <p className="mt-2 text-xs leading-5 text-slate-300">{reviewSummaryZh(signal, dimension)}</p>
                        {asStrings(signal.source_urls).slice(0, 2).map((url) => (
                          <a className="mt-1 block truncate text-[11px] text-cyan-300 underline-offset-2 hover:underline" href={url} key={url} rel="noreferrer" target="_blank">
                            {url}
                          </a>
                        ))}
                      </div>
                      );
                    })}
                  </div>
                ) : (
                  <p className="mt-3 rounded border border-amber-400/25 bg-amber-400/10 px-3 py-2 text-xs leading-5 text-amber-100">
                    {asString(record.note) || "未抽取到可支撑体验结论的真实信号。"}
                    {asString(record.llm_error) ? ` LLM 错误：${asString(record.llm_error)}` : ""}
                  </p>
                )}

                {urls.length ? (
                  <div className="mt-3 space-y-1">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">Sources</p>
                    {urls.slice(0, 3).map((url) => (
                      <a className="block truncate text-xs text-cyan-300 underline-offset-2 hover:underline" href={url} key={url} rel="noreferrer" target="_blank">
                        {url}
                      </a>
                    ))}
                  </div>
                ) : null}
                {limitations.length ? (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {limitations.slice(0, 3).map((item) => (
                      <StatusBadge key={item} label={item} tone="warning" />
                    ))}
                  </div>
                ) : null}
              </article>
            );
          })}
        </div>
      ) : (
        <p className="mt-3 rounded-md border border-amber-400/25 bg-amber-400/10 px-3 py-2 text-xs leading-5 text-amber-100">
          {asString(status.note) || "ReviewIntelMCP 尚未返回记录。"}
        </p>
      )}
    </div>
  );
}

function CollectorAgentDetail({
  agent,
  status,
  trace,
  report,
  resolvedProducts,
  unresolvedProducts,
  externalProductCandidates,
}: AgentDetailProps) {
  const identities = asRecords(report.product_identification);
  const resolved = resolvedProducts.length
    ? resolvedProducts
    : identities.filter((item) => !normalize(item.data_status).startsWith("official_spec"));
  const facts = hardwareProductsFromReport(report);
  const localFacts = facts.filter((item) => item.source === "local");
  const officialFacts = facts.filter((item) => item.source === "official");
  const officialSpecRecords = officialSpecRecordsFromReport(report);
  const priceRecords = asRecords(report.price_records);
  const priceStatus = asRecord(report.price_status);
  const reviewIntelRecords = reviewIntelRecordsFromReport(report);
  const reviewIntelStatus = reviewIntelStatusFromReport(report);
  const substeps = asRecords(trace?.substeps);
  const pending = asRecords(report.pending_data);
  const resolvedCount = localFacts.length;
  const hardwareReadyCount = facts.filter(hasUsefulHardware).length;
  const officialCollectedCount = officialSpecRecords.filter((item) => normalize(item.status) === "collected").length;
  // 产品 A/B 两个对比位：已命中的带硬件数据在前，未命中的作为待搜索位补足。
  const compareSlots: CompareSlot[] = [
    ...facts.map((item) => ({
      label: item.label,
      resolved: true,
      specs: item.specs,
      source: item.source,
      sourceLabel: item.sourceLabel,
      collectionStatus: item.collectionStatus,
      missingFields: item.missingFields,
    })),
    ...unresolvedProducts.map((query) => ({ label: query, resolved: false })),
  ].slice(0, 2);
  const localIdentityCards: CollectorIdentityCard[] = resolved.map((item) => {
      const input = asString(item.original_input);
      const brand = asString(item.official_brand) || asString(item.brand);
      const model = asString(item.official_model) || asString(item.model) || "本地命中产品";
      return {
        type: "local" as const,
        input,
        title: [brand, model].filter(Boolean).join(" "),
        matchedBy: asString(item.matched_by),
        matchedValue: asString(item.matched_value),
        confidence: asString(item.match_confidence) || asString(item.official_name_confidence),
        clickSystem: asString(item.click_system),
        aliasWarning: asString(item.alias_warning),
        disambiguation: asString(item.disambiguation_note),
      };
    });
  const searchIdentityCards: CollectorIdentityCard[] = externalProductCandidates.map((candidate) => {
    const best = candidate.best_candidate || candidate.official_candidates?.[0] || candidate.review_candidates?.[0];
    const input = asString(candidate.original_input);
    return {
      type: "search" as const,
      input,
      title: asString(best?.title, input || "官网候选"),
      url: asString(best?.url),
      domain: asString(best?.domain),
      candidateStatus: asString(candidate.candidate_status, "pending"),
    };
  });
  const unresolvedIdentityCards: CollectorIdentityCard[] = unresolvedProducts
    .filter(
      (query) =>
        !externalProductCandidates.some(
          (candidate) => normalize(candidate.original_input) === normalize(query),
        ),
    )
    .map((query) => ({
      type: "search" as const,
      input: query,
      title: query,
      url: "",
      domain: "",
      candidateStatus: "pending",
    }));
  const identityCards: CollectorIdentityCard[] = [
    ...localIdentityCards,
    ...searchIdentityCards,
    ...unresolvedIdentityCards,
  ].slice(0, 2);
  const showCompare = compareSlots.length >= 2;
  const officialCandidateCount = externalProductCandidates.filter(
    (item) =>
      item.candidate_status === "official_candidate_found" ||
      (item.official_candidates?.length ?? 0) > 0,
  ).length;
  const hasRun = resolved.length > 0 || facts.length > 0 || substeps.length > 0 || externalProductCandidates.length > 0 || officialSpecRecords.length > 0;

  return (
    <AgentDetailFrame
      agent={agent}
      status={status}
      eyebrow="Collector"
      description="采集与实体识别员：读取本地事实库；未命中时调用联网搜索找官网候选，再交给官网规格 MCP 抽取硬件参数。"
    >
      {!hasRun ? (
        <EmptyAgentNote label="CollectorAgent 还未运行或暂无识别结果。开始分析后这里会显示实体识别、本地事实读取和采集流水线。" />
      ) : (
        <>
          <div className="rounded-lg border border-slate-800 bg-slate-900/45 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Entity Resolution</p>
                <h4 className="mt-2 text-lg font-semibold text-white">输入识别 / 官网候选</h4>
              </div>
              <div className="flex flex-wrap gap-2">
                <StatusBadge label={`本地命中 ${resolved.length} 款`} tone={resolved.length >= 2 ? "success" : resolved.length ? "warning" : "neutral"} />
                {officialFacts.length ? (
                  <StatusBadge label={`官网抽取 ${officialFacts.length} 款`} tone="info" />
                ) : null}
                {externalProductCandidates.length ? (
                  <StatusBadge
                    label={`官网候选 ${officialCandidateCount} 个`}
                    tone={officialCandidateCount ? "success" : "warning"}
                  />
                ) : null}
                {officialSpecRecords.length ? (
                  <StatusBadge
                    label={`官网规格 ${officialCollectedCount}/${officialSpecRecords.length}`}
                    tone={officialCollectedCount === officialSpecRecords.length ? "success" : "warning"}
                  />
                ) : null}
              </div>
            </div>
            {unresolvedProducts.length > 0 ? (
              <div className="mt-4 rounded-md border border-amber-400/30 bg-amber-400/10 p-3">
                <p className="text-xs font-semibold text-amber-100">未命中本地 JSON 的输入</p>
                {unresolvedProducts.length ? (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {unresolvedProducts.map((q) => (
                      <StatusBadge key={q} label={q} tone="warning" />
                    ))}
                  </div>
                ) : null}
                <p className="mt-2 text-[11px] leading-4 text-amber-100/80">
                  联网搜索会先查找官网候选；候选只用于识别官方页面，不直接写入重量、DPI、回报率等硬件字段。
                </p>
              </div>
            ) : null}
            {externalProductCandidates.length ? (
              <div className="mt-4">
                <ExternalCandidateTable items={externalProductCandidates} />
              </div>
            ) : null}
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              {identityCards.map((item, index) => {
                const isLocal = item.type === "local";
                return (
                  <div className="rounded-md border border-slate-800 bg-slate-950/60 p-3" key={`${item.input}-${index}`}>
                    <p className="text-xs uppercase tracking-[0.16em] text-slate-500">产品 {index === 0 ? "A" : "B"}</p>
                    {item.input ? (
                      <p className="mt-1 text-xs text-slate-500">
                        输入「{item.input}」<span className="text-slate-600">→</span>
                      </p>
                    ) : null}
                    {item.type === "search" && isExternalUrl(item.url) ? (
                      <a
                        className="mt-0.5 block truncate text-sm font-semibold text-cyan-300 underline-offset-2 hover:underline"
                        href={item.url}
                        rel="noreferrer"
                        target="_blank"
                      >
                        {item.title}
                      </a>
                    ) : (
                      <p className="mt-0.5 text-sm font-semibold text-slate-100">{item.title}</p>
                    )}
                    <div className="mt-2 flex flex-wrap gap-2">
                      {isLocal ? (
                        <>
                          {item.matchedBy ? (
                            <StatusBadge
                              label={`${MATCH_BY_LABEL[item.matchedBy] || item.matchedBy}${item.matchedValue ? `: ${item.matchedValue}` : ""}`}
                              tone="info"
                            />
                          ) : null}
                          {item.confidence ? (
                            <StatusBadge
                              label={`可信 ${item.confidence}`}
                              tone={item.confidence === "verified" ? "success" : "warning"}
                            />
                          ) : null}
                          {item.clickSystem ? <StatusBadge label={`点击 ${item.clickSystem}`} tone="neutral" /> : null}
                        </>
                      ) : (
                        <>
                          <StatusBadge label="联网搜索" tone="success" />
                          <StatusBadge label={candidateStatusLabel(asString(item.candidateStatus))} tone={candidateStatusTone(asString(item.candidateStatus))} />
                          {item.domain ? <StatusBadge label={item.domain} tone="neutral" /> : null}
                        </>
                      )}
                    </div>
                    {isLocal && item.aliasWarning ? (
                      <p className="mt-2 rounded border border-amber-400/30 bg-amber-400/10 px-2 py-1 text-[11px] leading-4 text-amber-100">
                        ⚠ {item.aliasWarning}
                      </p>
                    ) : null}
                    {isLocal && item.disambiguation ? (
                      <p className="mt-1 text-[11px] leading-4 text-slate-500">消歧：{item.disambiguation}</p>
                    ) : null}
                    {!isLocal ? (
                      <p className="mt-2 text-[11px] leading-4 text-slate-500">
                        官网候选已找到，硬件参数交给官网规格 MCP 抽取；未找到字段会说明原因。
                      </p>
                    ) : null}
                  </div>
                );
              })}
            </div>
          </div>

          {substeps.length ? (
            <div className="rounded-lg border border-slate-800 bg-slate-900/45 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Pipeline</p>
              <h4 className="mt-2 text-lg font-semibold text-white">采集子步骤</h4>
              <div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                {substeps.map((step, index) => {
                  const rawName = asString(step.name) || `step-${index + 1}`;
                  const rawStatus = asString(step.status) || "pending";
                  const name = PIPELINE_STEP_LABEL[rawName] || rawName;
                  const stepStatus = SUBSTEP_STATUS_LABEL[rawStatus] || rawStatus;
                  const count = asNumber(step.count);
                  return (
                    <div className="rounded-md border border-slate-800 bg-slate-950/60 p-3" key={rawName}>
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-sm font-semibold text-slate-100">{name}</p>
                        <StatusBadge label={stepStatus} tone={researchTone(rawStatus)} />
                      </div>
                      {typeof count === "number" ? <p className="mt-1 text-xs text-slate-500">数量：{count}</p> : null}
                    </div>
                  );
                })}
              </div>
            </div>
          ) : null}

          <OfficialSpecResultTable records={officialSpecRecords} localProducts={localFacts} />

          <PriceMcpSection records={priceRecords} status={priceStatus} />

          <ReviewIntelMcpSection records={reviewIntelRecords} status={reviewIntelStatus} />

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-lg border border-cyan-300/25 bg-cyan-400/10 p-4">
              <div className="flex items-start justify-between gap-3">
                <p className="text-sm font-semibold text-cyan-100">硬件数据</p>
                <StatusBadge
                  label={hardwareReadyCount >= 2 ? "已采集" : officialCollectedCount ? "部分采集" : officialCandidateCount ? "待规格抽取" : "待采集"}
                  tone={hardwareReadyCount >= 2 ? "success" : officialCollectedCount ? "info" : officialCandidateCount ? "info" : "warning"}
                />
              </div>
              <p className="mt-1 text-xs leading-5 text-slate-400">
                {resolvedCount >= 2
                  ? "两款产品均已从本地 JSON 读取稳定硬件字段，可进入对比。"
                  : hardwareReadyCount >= 2
                    ? `硬件数据由本地 JSON ${resolvedCount} 款 + 官网抽取 ${officialFacts.length} 款组成；缺失字段会说明原因。`
                  : officialCollectedCount
                    ? "官网规格 MCP 已抽取到部分硬件字段；未找到的字段会显示官网未披露、抽取失败等原因。"
                  : resolvedCount === 1
                    ? "仅命中 1 款，另一款需搜索 / 官网 MCP 识别并抽取。"
                    : officialCandidateCount
                      ? "联网搜索已识别官网候选；重量、DPI、回报率等规格字段等待官网规格 MCP 抽取。"
                      : "两款输入均未命中本地事实库，无硬件字段可读，等待搜索 / 官网 MCP。"}
              </p>
              <div className="mt-3 grid grid-cols-2 gap-2">
                <StatTile label="本地命中" value={resolvedCount} tone={resolvedCount >= 2 ? "success" : resolvedCount ? "warning" : "neutral"} />
                <StatTile label="官网抽取" value={officialFacts.length} tone={officialFacts.length ? "info" : "neutral"} />
              </div>
              <div className="mt-2 grid grid-cols-1 gap-2">
                <StatTile
                  label="硬件字段 / 款"
                  value={hardwareReadyCount >= 1 ? HARDWARE_FIELDS.length : "—"}
                  tone={hardwareReadyCount >= 1 ? "info" : "neutral"}
                />
              </div>
            </div>
            <div className="rounded-lg border border-cyan-300/20 bg-slate-950/60 p-4">
              <div className="flex items-start justify-between gap-3">
                <p className="text-sm font-semibold text-slate-100">官网规格核验</p>
                <StatusBadge
                  label={officialCollectedCount ? "官网已采集" : officialCandidateCount ? "官网已识别" : resolvedCount >= 2 ? "复核可选" : "待搜索"}
                  tone={officialCollectedCount || officialCandidateCount || resolvedCount >= 2 ? "success" : "warning"}
                />
              </div>
              <p className="mt-1 text-xs leading-5 text-slate-400">
                {officialCandidateCount
                  ? officialCollectedCount
                    ? "官网规格 MCP 已从官方页面抽取规格字段，并写入本次工作流的结构化结果。"
                    : "已拿到官网候选链接，下一步由官网规格 MCP 从该页面抽取规格表并写入硬件字段。"
                  : resolvedCount >= 2
                    ? "本地 JSON 已具备稳定规格，官网核验作为后续复核来源。"
                    : "未找到官网候选前，不生成官方型号和硬件参数结论。"}
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <StatusBadge label="联网搜索 已启用" tone="success" />
                {officialSpecRecords.length ? <StatusBadge label="官网规格抽取 已启用" tone="success" /> : null}
                <StatusBadge label={`官网候选 ${externalProductCandidates.length} 个`} tone={externalProductCandidates.length ? "info" : "neutral"} />
                {pending.length ? <StatusBadge label={`待补 ${pending.length} 项`} tone="warning" /> : null}
              </div>
            </div>
          </div>

          {showCompare ? (
            <div className="rounded-lg border border-slate-800 bg-slate-900/45 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Hardware Comparison</p>
              <h4 className="mt-2 text-lg font-semibold text-white">硬件参数对比</h4>
              <p className="mt-1 text-xs leading-5 text-slate-400">
                {resolvedCount >= 2
                  ? "两款产品的本地 JSON 硬件字段逐项对比（事实底座，非最终购买建议；体验 / 价格等待 MCP）。"
                  : hardwareReadyCount >= 2
                    ? "表格混合展示本地 JSON 与官网抽取字段；每列标注来源，缺失字段显示原因。"
                  : resolvedCount >= 1
                    ? "已命中产品展示本地 JSON 硬件字段；未命中产品先显示本地未收录，后续由官网抽取补上来源。"
                    : "两款产品均未命中本地 JSON，表格保留对比位；未找到字段会标注原因。"}
              </p>
              <div className="mt-3">
                {hardwareReadyCount >= 2 ? (
                  <HardwareMiniTable products={facts} />
                ) : (
                  <CollectorCompareTable slots={compareSlots} />
                )}
              </div>
            </div>
          ) : null}
        </>
      )}
    </AgentDetailFrame>
  );
}

function EvidenceAgentDetail({ agent, status, evidenceList, report }: AgentDetailProps) {
  const items = evidenceList;
  const officialSpecRecords = officialSpecRecordsFromReport(report);
  const isPending = (e: Record<string, unknown>) =>
    Boolean(e.pending_research) || normalize(e.data_status) === "pending_research";
  const verified = items.filter((e) => !isPending(e));
  const pendingCount = items.length - verified.length;
  const credCount = (level: string) => items.filter((e) => normalize(e.credibility) === level).length;
  const sourceGroups = Object.entries(
    items.reduce<Record<string, number>>((acc, item) => {
      const key = asString(item.source_type) || asString(item.used_by_agent) || "unknown";
      acc[key] = (acc[key] || 0) + 1;
      return acc;
    }, {}),
  ).sort((a, b) => b[1] - a[1]);
  const officialEvidenceCount = items.filter((item) => {
    const sourceType = normalize(item.source_type);
    const agentName = normalize(item.used_by_agent);
    const title = normalize(item.source_title);
    return sourceType === "official" || agentName.includes("officialspec") || title.includes("official");
  }).length;
  const cols = "grid-cols-[64px_minmax(0,1fr)_88px_84px_minmax(0,1.1fr)]";

  return (
    <AgentDetailFrame
      agent={agent}
      status={status}
      eyebrow="Evidence"
      description="证据结构化员：把采集结果统一成可追溯证据，标注来源、可信度与待补状态。"
    >
      {items.length === 0 ? (
        <EmptyAgentNote label="EvidenceAgent 还未产出证据。开始分析后这里会列出每条结构化证据及其来源、可信度与溯源链接。" />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
            <StatTile label="证据总数" value={items.length} tone="info" />
            <StatTile label="已验证" value={verified.length} tone="success" />
            <StatTile label="待补 (pending)" value={pendingCount} tone={pendingCount ? "warning" : "neutral"} />
            <StatTile label="高可信" value={credCount("high")} tone="success" />
            <StatTile label="低可信" value={credCount("low")} tone={credCount("low") ? "warning" : "neutral"} />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-lg border border-slate-800 bg-slate-900/45 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Source Mix</p>
                  <h4 className="mt-2 text-lg font-semibold text-white">证据来源分布</h4>
                </div>
                <StatusBadge label={`官网证据 ${officialEvidenceCount}`} tone={officialEvidenceCount ? "success" : "neutral"} />
              </div>
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                {sourceGroups.length ? (
                  sourceGroups.map(([source, count]) => (
                    <div className="rounded-md border border-slate-800 bg-slate-950/60 p-3" key={source}>
                      <p className="text-sm font-semibold text-slate-100">
                        {SOURCE_TYPE_LABEL[normalize(source)] || source}
                      </p>
                      <p className="mt-1 text-2xl font-semibold text-cyan-200">{count}</p>
                    </div>
                  ))
                ) : (
                  <EmptyAgentNote label="暂无来源统计。" />
                )}
              </div>
            </div>
            <div className="rounded-lg border border-cyan-300/25 bg-cyan-400/10 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-cyan-200">Official Spec Evidence</p>
              <h4 className="mt-2 text-lg font-semibold text-white">官网规格证据状态</h4>
              <p className="mt-2 text-sm leading-6 text-slate-300">
                {officialSpecRecords.length
                  ? `已接收 ${officialSpecRecords.length} 条官网规格记录，其中 ${officialSpecRecords.filter((item) => normalize(item.status) === "collected").length} 条完成抽取。`
                  : "当前没有官网规格记录；如果产品不在本地库，会先由联网搜索找官网候选，再交给官网规格 MCP。"}
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                {officialSpecRecords.map((item, index) => (
                  <StatusBadge
                    key={`${item.input || index}-${item.status || "official"}`}
                    label={`${officialSpecDisplayName(item, index)} · ${officialSpecStatusLabel(item.status)}`}
                    tone={officialSpecStatusTone(item.status)}
                  />
                ))}
              </div>
            </div>
          </div>

          <div className="overflow-hidden rounded-md border border-slate-800 bg-slate-950/70">
            <div className={`grid ${cols} border-b border-slate-800 bg-slate-900/70 px-3 py-2 text-xs font-semibold uppercase tracking-[0.1em] text-slate-500`}>
              <div>ID</div>
              <div>维度 / 产品</div>
              <div>来源</div>
              <div>可信度</div>
              <div>溯源</div>
            </div>
            <div className="max-h-[420px] overflow-y-auto">
              {items.map((e, index) => {
                const id = asString(e.evidence_id) || `EV${index + 1}`;
                const dim = asString(e.related_dimension) || asString(e.dimension);
                const platform = asString(e.platform);
                const sourceType = asString(e.source_type);
                const credibility = asString(e.credibility);
                const url = asString(e.source_url);
                const title = asString(e.source_title) || asString(e.source);
                const readable = readableEvidenceSummary(e);
                return (
                  <div className={`grid ${cols} items-center border-b border-slate-800/70 px-3 py-2 text-xs last:border-b-0`} key={id}>
                    <div className="font-mono text-slate-400">{id}</div>
                    <div className="min-w-0">
                      <p className="truncate text-slate-200">{dim || "—"}</p>
                      <p className="truncate text-slate-500">{platform}</p>
                      <p className="mt-1 line-clamp-2 text-slate-400">{readable}</p>
                    </div>
                    <div>
                      <StatusBadge label={SOURCE_TYPE_LABEL[normalize(sourceType)] || sourceType || "—"} tone="neutral" />
                    </div>
                    <div>
                      <StatusBadge label={CREDIBILITY_LABEL[normalize(credibility)] || credibility || "—"} tone={credibilityTone(credibility)} />
                    </div>
                    <div className="min-w-0">
                      {isExternalUrl(url) ? (
                        <a className="block truncate text-cyan-300 underline-offset-2 hover:underline" href={url} target="_blank" rel="noreferrer">
                          {title || url}
                        </a>
                      ) : (
                        <span className="block truncate text-slate-500">
                          {title || url || "本地结构化来源"}
                          {isPending(e) ? "（未抓取到数据）" : ""}
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
          <p className="text-xs leading-5 text-slate-500">
            对比模式下证据优先展示本地结构化硬规格事实和 MCP 返回的真实链接；评价 MCP 已接入但本轮未抓到内容的维度会明确标记为「未抓取到数据」，并在下方说明原因。
          </p>
          {pendingCount > 0 && (
            <div className="rounded-lg border border-amber-400/25 bg-amber-400/5 p-4 text-xs leading-6 text-amber-100/90">
              <p className="text-sm font-semibold text-amber-200">为什么部分用户评价 / 博主测评维度显示「未抓取到数据」？</p>
              <p className="mt-2 text-amber-100/80">
                ReviewIntel 评价 MCP 已经接入并真实发起了抓取，但在本次 demo 中，下面这些维度（用户口碑、驱动长期口碑、长期可靠性等）确实难以稳定拿到数据，原因如下：
              </p>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-amber-100/80">
                <li>主流评测站点和电商评论区普遍部署了反爬 / Cloudflare 人机校验，未登录的自动化请求会被拦截或返回空内容。</li>
                <li>高质量测评大量集中在 YouTube / Bilibili 视频里，而本 demo 没有接入 Google、YouTube、Bilibili 的官方 API（这些都需要付费配额与审核），只能走公开网页。</li>
                <li>即便拿到视频页面，结论也藏在口播和画面中，LLM 难以「看视频」稳定抽取结构化结论，长视频还容易抽取超时。</li>
                <li>本项目重点是多 Agent 协作链路与证据可追溯，而非专门的爬虫工程；在时间有限的 demo 阶段优先保证了硬件规格、官方/电商价格这类可校验的硬事实。</li>
              </ul>
              <p className="mt-2 text-amber-100/70">
                设计上这些维度不会被编造：抓不到就如实标记「未抓取到数据」，并在质量评分中按缺失维度扣分。接入正式的搜索 / 视频字幕 API 后，这些占位会被真实评价证据替换。
              </p>
            </div>
          )}
        </>
      )}
    </AgentDetailFrame>
  );
}

function swotItems(value: unknown): SwotPoint[] {
  return Array.isArray(value)
    ? value.filter((item): item is SwotPoint => Boolean(item) && typeof item === "object")
    : [];
}

function feedbackRecords(value: unknown): HumanFeedbackRecord[] {
  return asRecords(value) as HumanFeedbackRecord[];
}

function swotStatusLabel(value: unknown): string {
  const key = normalize(value);
  if (key === "available") return "AI 已生成";
  if (key === "fallback" || key === "fallback_llm_failed") return "AI 解读已生成";
  return asString(value, "等待生成");
}

function swotStatusTone(value: unknown): Tone {
  const key = normalize(value);
  if (key === "available") return "success";
  if (key === "fallback" || key === "fallback_llm_failed") return "success";
  return "neutral";
}

function swotModelLabel(value: unknown): string {
  const model = asString(value);
  const key = normalize(model);
  if (!model || key.includes("fallback") || key.includes("rule")) return "";
  return model;
}

function feedbackStatusLabel(value: unknown): string {
  const key = normalize(value);
  if (key === "applied_to_report") return "已并入报告";
  if (key === "pending_verification") return "待校验";
  if (key === "needs_external_evidence") return "待外部证据";
  if (key === "verified") return "已校验";
  return asString(value, "待校验");
}

function SwotColumn({
  title,
  items,
  tone,
}: {
  title: string;
  items: SwotPoint[];
  tone: Tone;
}) {
  return (
    <div className="rounded-md border border-violet-400/20 bg-slate-950/60 p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-semibold text-violet-100">{title}</p>
        <StatusBadge label={`${items.length}`} tone={tone} />
      </div>
      <div className="mt-3 space-y-2">
        {items.length ? (
          items.slice(0, 3).map((item, index) => {
            const evidenceIds = asStrings(item.evidence_ids);
            return (
              <div className="rounded border border-slate-800 bg-slate-900/70 p-2" key={`${title}-${index}`}>
                <div className="flex flex-wrap items-center gap-2">
                  {asString(item.product) ? <StatusBadge label={asString(item.product)} tone="neutral" /> : null}
                  {asString(item.confidence) ? (
                    <StatusBadge label={localizedConfidence(item.confidence)} tone={credibilityTone(asString(item.confidence))} />
                  ) : null}
                  <StatusBadge
                    label={evidenceIds.length ? "已绑定证据" : "待绑定证据"}
                    tone={evidenceIds.length ? "success" : "warning"}
                  />
                </div>
                <p className="mt-2 text-xs leading-5 text-slate-300">{asString(item.point, "暂无明确结论")}</p>
                {evidenceIds.length ? (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {evidenceIds.slice(0, 4).map((id) => <StatusBadge key={id} label={id} tone="success" />)}
                  </div>
                ) : (
                  <p className="mt-2 text-[11px] text-slate-500">无直接 evidence_id，按低可信/待验证处理。</p>
                )}
              </div>
            );
          })
        ) : (
          <p className="text-xs leading-5 text-slate-500">等待 AI 根据 evidence / claims 生成。</p>
        )}
      </div>
    </div>
  );
}

function SwotAiPanel({
  taskId,
  report,
  onDataChanged,
}: {
  taskId?: string;
  report: Record<string, unknown>;
  onDataChanged?: () => void;
}) {
  const initialInterpretation = asRecord(report.analysis_ai_interpretation) as AnalysisAiInterpretation;
  const [interpretation, setInterpretation] = useState<AnalysisAiInterpretation>(initialInterpretation);
  const [feedback, setFeedback] = useState<HumanFeedbackRecord[]>(feedbackRecords(report.human_feedback));
  const [message, setMessage] = useState("");
  const [product, setProduct] = useState("");
  const [dimension, setDimension] = useState("scenario_fit");
  const [assistantReply, setAssistantReply] = useState("");
  const [isLoadingSwot, setIsLoadingSwot] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [panelError, setPanelError] = useState("");

  const productOptions = useMemo(() => {
    const labels = asRecords(report.hardware_specs)
      .map((item) => [asString(item.brand), asString(item.model)].filter(Boolean).join(" "))
      .filter(Boolean);
    return Array.from(new Set(labels));
  }, [report]);

  useEffect(() => {
    setInterpretation(initialInterpretation);
    setFeedback(feedbackRecords(report.human_feedback));
  }, [initialInterpretation, report.human_feedback]);

  useEffect(() => {
    if (!taskId) return;
    const activeTaskId = taskId;
    let cancelled = false;
    async function loadSwot() {
      setIsLoadingSwot(true);
      setPanelError("");
      try {
        const resp = await analysisApi.getSwot(activeTaskId);
        if (cancelled) return;
        setInterpretation(resp.analysis_ai_interpretation || {});
        setFeedback(resp.human_feedback || []);
      } catch (err) {
        if (!cancelled) {
          setPanelError(err instanceof Error ? err.message : "SWOT AI 解读加载失败");
        }
      } finally {
        if (!cancelled) setIsLoadingSwot(false);
      }
    }
    loadSwot();
    return () => {
      cancelled = true;
    };
  }, [taskId]);

  async function submitFeedback() {
    const text = message.trim();
    if (!taskId || !text) return;
    setIsSubmitting(true);
    setPanelError("");
    try {
      const resp = await analysisApi.submitHumanFeedback(taskId, {
        message: text,
        product: product || undefined,
        dimension: dimension || undefined,
      });
      setMessage("");
      setAssistantReply(resp.assistant_reply || "已提交给 VerificationAgent。");
      if (resp.analysis_ai_interpretation) {
        setInterpretation(resp.analysis_ai_interpretation);
      }
      setFeedback(resp.human_feedback || (resp.feedback_record ? [...feedback, resp.feedback_record] : feedback));
      onDataChanged?.();
    } catch (err) {
      setPanelError(err instanceof Error ? err.message : "人工反馈提交失败");
    } finally {
      setIsSubmitting(false);
    }
  }

  const swot = asRecord(interpretation.swot);
  const dataGaps = asStrings(interpretation.data_gaps);
  const questions = asStrings(interpretation.human_feedback_questions);

  return (
    <div className="rounded-lg border border-violet-400/35 bg-violet-400/10 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-violet-200">AI Interpretation</p>
          <h4 className="mt-2 text-lg font-semibold text-white">SWOT AI 解读与人工修正</h4>
          <p className="mt-1 text-xs leading-5 text-slate-400">
            AI 只读取当前 evidence / claims / 风险标记；人工输入会进入证据流，由 VerificationAgent 校验后再影响报告。
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <StatusBadge label={swotStatusLabel(interpretation.status)} tone={swotStatusTone(interpretation.status)} />
          {swotModelLabel(interpretation.model) ? <StatusBadge label={swotModelLabel(interpretation.model)} tone="info" /> : null}
        </div>
      </div>

      {panelError ? (
        <div className="mt-3 rounded-md border border-amber-400/35 bg-amber-400/10 px-3 py-2 text-xs text-amber-100">
          {panelError}
        </div>
      ) : null}

      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(320px,0.8fr)]">
        <div className="space-y-4">
          <div className="rounded-md border border-slate-800 bg-slate-950/60 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm font-semibold text-slate-100">AI 总体研判</p>
              {isLoadingSwot ? <StatusBadge label="生成中" tone="info" /> : null}
            </div>
            <p className="mt-2 text-sm leading-6 text-slate-300">
              {asString(interpretation.overall_reading, "等待 AnalysisAgent 调用 LLM 生成 SWOT 解读。")}
            </p>
          </div>

          <div className="grid gap-3 lg:grid-cols-2">
            <SwotColumn title="S 优势" items={swotItems(swot.strengths)} tone="success" />
            <SwotColumn title="W 劣势" items={swotItems(swot.weaknesses)} tone="warning" />
            <SwotColumn title="O 机会" items={swotItems(swot.opportunities)} tone="info" />
            <SwotColumn title="T 威胁" items={swotItems(swot.threats)} tone="danger" />
          </div>

          <div className="grid gap-3 lg:grid-cols-2">
            <div className="rounded-md border border-slate-800 bg-slate-950/60 p-3">
              <p className="text-sm font-semibold text-slate-100">数据不清晰的地方</p>
              <ul className="mt-2 space-y-1 text-xs leading-5 text-slate-400">
                {(dataGaps.length ? dataGaps : ["暂无额外缺口；仍建议用测评/评论数据复核体验类判断。"]).slice(0, 5).map((item, index) => (
                  <li key={index}>• {item}</li>
                ))}
              </ul>
            </div>
            <div className="rounded-md border border-slate-800 bg-slate-950/60 p-3">
              <p className="text-sm font-semibold text-slate-100">可追溯引用</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {asStrings(interpretation.used_claim_ids).slice(0, 8).map((id) => <StatusBadge key={id} label={id} tone="neutral" />)}
                {asStrings(interpretation.used_evidence_ids).slice(0, 8).map((id) => <StatusBadge key={id} label={id} tone="success" />)}
                {!asStrings(interpretation.used_claim_ids).length && !asStrings(interpretation.used_evidence_ids).length ? (
                  <StatusBadge label="等待绑定证据" tone="warning" />
                ) : null}
              </div>
            </div>
          </div>
        </div>

        <aside className="rounded-md border border-slate-800 bg-slate-950/70 p-3">
          <div className="flex items-center justify-between gap-2">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Human Feedback</p>
              <h5 className="mt-1 text-base font-semibold text-white">人工修正对话</h5>
            </div>
            <StatusBadge label={`${feedback.length} 条`} tone={feedback.length ? "success" : "neutral"} />
          </div>

          <div className="mt-3 max-h-56 space-y-2 overflow-y-auto pr-1">
            {feedback.length ? (
              feedback.map((item, index) => (
                <div className="rounded border border-cyan-300/20 bg-cyan-300/5 p-2" key={asString(item.feedback_id) || index}>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <StatusBadge label={asString(item.feedback_id, `HF${index + 1}`)} tone="info" />
                    <StatusBadge label={feedbackStatusLabel(item.status)} tone={normalize(item.status) === "applied_to_report" ? "success" : "warning"} />
                  </div>
                  <p className="mt-2 text-xs leading-5 text-slate-300">{asString(item.message)}</p>
                  <p className="mt-1 text-[11px] text-slate-500">
                    {asString(item.product, "未指定产品")} · {asString(item.dimension, "human_feedback")}
                  </p>
                </div>
              ))
            ) : (
              <p className="rounded border border-slate-800 bg-slate-900/60 p-2 text-xs leading-5 text-slate-500">
                你可以在这里补充“GPX2 打 FPS 不如 Viper V4 Pro，因为重量和回报率差距明显”这类现场修正。
              </p>
            )}
          </div>

          {assistantReply ? (
            <div className="mt-3 rounded border border-emerald-400/25 bg-emerald-400/10 p-2 text-xs leading-5 text-emerald-100">
              {assistantReply}
            </div>
          ) : null}

          <div className="mt-3 space-y-2">
            <select
              className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-200 outline-none transition focus:border-cyan-300"
              onChange={(event) => setProduct(event.target.value)}
              value={product}
            >
              <option value="">不指定产品</option>
              {productOptions.map((label) => (
                <option key={label} value={label}>{label}</option>
              ))}
            </select>
            <select
              className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-200 outline-none transition focus:border-cyan-300"
              onChange={(event) => setDimension(event.target.value)}
              value={dimension}
            >
              <option value="scenario_fit">场景适配</option>
              <option value="fps_performance">FPS 表现</option>
              <option value="grip_feel">握持手感</option>
              <option value="driver_reputation">驱动口碑</option>
              <option value="price_value">价格 / 性价比</option>
              <option value="human_feedback">其他人工补充</option>
            </select>
            <textarea
              className="min-h-28 w-full resize-none rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm leading-6 text-slate-100 outline-none transition placeholder:text-slate-600 focus:border-cyan-300"
              onChange={(event) => setMessage(event.target.value)}
              placeholder={questions[0] || "输入你要补充或纠正的判断，系统会把它作为人工 evidence 交给 VerificationAgent。"}
              value={message}
            />
            <button
              className="w-full rounded-md bg-cyan-300 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-200 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
              disabled={!taskId || !message.trim() || isSubmitting}
              onClick={submitFeedback}
              type="button"
            >
              {isSubmitting ? "提交中..." : "提交给 VerificationAgent"}
            </button>
          </div>
        </aside>
      </div>
    </div>
  );
}

function AnalysisAgentDetail({ agent, status, report, claims, taskId, onDataChanged }: AgentDetailProps) {
  const dimensionEntries = Object.entries(asRecord(asRecord(report.product_matrix).dimensions)).slice(0, 6);
  const hardware = asRecord(report.hardware_fact_comparison);
  const verdicts = asRecord(hardware.hardware_advantages);
  const diffSummary = asStrings(hardware.hardware_diff_summary);
  const risks = asRecords(report.risk_flags);
  const officialSpecRecords = officialSpecRecordsFromReport(report);
  const priceRecords = asRecords(report.price_records);
  const reviewRecords = reviewIntelRecordsFromReport(report);
  const reviewSignalRows = reviewRecords.flatMap((record, recordIndex) =>
    reviewSignalEntries(record).map(([dimension, signal]) => ({
      product: reviewRecordLabel(record, recordIndex),
      dimension,
      signal,
    })),
  );
  const hasRun = dimensionEntries.length > 0 || diffSummary.length > 0 || claims.length > 0 || officialSpecRecords.length > 0 || priceRecords.length > 0 || reviewSignalRows.length > 0;

  const verdictLabels: Array<[string, string]> = [
    ["strongest_hardware", "硬件最强"],
    ["best_software", "软件最佳"],
    ["best_click_system", "点击系统最佳"],
    ["strongest_overall", "综合最强"],
  ];

  return (
    <AgentDetailFrame
      agent={agent}
      status={status}
      eyebrow="Analysis"
      description="分析师：只分析有证据支撑的硬件事实差异；体验 / 价格结论等待 MCP，SWOT 与 AI 解读等待 LLM 接入。"
    >
      {!hasRun ? (
        <EmptyAgentNote label="AnalysisAgent 还未产出硬件对比。开始分析后这里会显示对比矩阵、硬件裁决、证据绑定结论与风险标记。" />
      ) : (
        <>
          {diffSummary.length ? (
            <div className="rounded-lg border border-slate-800 bg-slate-900/45 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Hardware Verdict</p>
              <h4 className="mt-2 text-lg font-semibold text-white">硬件对比结论</h4>
              <div className="mt-3 flex flex-wrap gap-2">
                {verdictLabels.map(([key, label]) =>
                  asString(verdicts[key]) ? (
                    <StatusBadge key={key} label={`${label}：${asString(verdicts[key])}`} tone="success" />
                  ) : null,
                )}
              </div>
              <ul className="mt-3 space-y-2">
                {diffSummary.map((line, index) => (
                  <li className="rounded-md border border-slate-800 bg-slate-950/60 px-3 py-2 text-sm leading-6 text-slate-300" key={index}>
                    {line}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {claims.length ? (
            <div className="rounded-lg border border-slate-800 bg-slate-900/45 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Evidence-bound Claims</p>
                  <h4 className="mt-2 text-lg font-semibold text-white">证据绑定结论</h4>
                </div>
                <StatusBadge label={`${claims.length} claims`} tone="success" />
              </div>
              <div className="mt-3 grid gap-2">
                {claims.slice(0, 8).map((claim, index) => {
                  const evidenceIds = asStrings(claim.evidence_ids);
                  return (
                    <div className="rounded-md border border-slate-800 bg-slate-950/60 p-3" key={claim.claim_id || index}>
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="font-mono text-xs text-cyan-200">{claim.claim_id || `claim-${index + 1}`}</p>
                          <p className="mt-1 text-sm leading-6 text-slate-200">{claim.content}</p>
                        </div>
                        <StatusBadge label={claim.dimension || "hardware"} tone="info" />
                      </div>
                      <div className="mt-2 flex flex-wrap gap-1">
                        {evidenceIds.length ? (
                          evidenceIds.map((id) => <StatusBadge key={id} label={id} tone="neutral" />)
                        ) : (
                          <StatusBadge label="missing evidence_ids" tone="danger" />
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
              <p className="mt-3 text-xs leading-5 text-slate-500">
                AnalysisAgent 只展示绑定 evidence_ids 的结论；没有评价/价格证据时，不提前生成握法、适合人群或性价比结论。
              </p>
            </div>
          ) : null}

          {reviewSignalRows.length ? (
            <div className="rounded-lg border border-cyan-300/25 bg-cyan-400/10 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-cyan-200">Experience Signals</p>
                  <h4 className="mt-2 text-lg font-semibold text-white">真实测评 / 口碑信号</h4>
                </div>
                <StatusBadge label={`${reviewSignalRows.length} signals`} tone="success" />
              </div>
              <div className="mt-3 grid gap-2 lg:grid-cols-2">
                {reviewSignalRows.slice(0, 8).map((row, index) => {
                  const evIds = asStrings(row.signal.evidence_ids);
                  return (
                    <div className="rounded-md border border-cyan-300/20 bg-slate-950/60 p-3" key={`${row.product}-${row.dimension}-${index}`}>
                      <div className="flex flex-wrap items-center gap-2">
                        <StatusBadge label={row.product} tone="neutral" />
                        <StatusBadge label={reviewDimensionLabel(row.dimension)} tone="info" />
                        <StatusBadge label={localizedConfidence(row.signal.confidence)} tone={credibilityTone(asString(row.signal.confidence))} />
                      </div>
                      <p className="mt-2 text-sm leading-6 text-slate-200">{reviewSummaryZh(row.signal, row.dimension)}</p>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {evIds.length ? evIds.map((id) => <StatusBadge key={id} label={id} tone="success" />) : <StatusBadge label="no evidence_id" tone="danger" />}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : null}

          {dimensionEntries.length ? (
            <div className="rounded-lg border border-slate-800 bg-slate-900/45 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Comparison Matrix</p>
              <h4 className="mt-2 text-lg font-semibold text-white">对比矩阵（每格绑定证据）</h4>
              <div className="mt-3 space-y-3">
                {dimensionEntries.map(([dimension, platformMap]) => (
                  <div className="rounded-md border border-slate-800 bg-slate-950/55 p-3" key={dimension}>
                    <p className="text-sm font-semibold text-slate-100">{dimension}</p>
                    <div className="mt-2 grid gap-2 sm:grid-cols-2">
                      {Object.entries(asRecord(platformMap)).map(([platform, cell]) => {
                        const c = asRecord(cell);
                        const evIds = asStrings(c.evidence_ids);
                        return (
                          <div className="rounded border border-slate-800/80 bg-slate-900/50 p-2" key={platform}>
                            <p className="text-xs font-semibold text-cyan-200">{platform}</p>
                            <p className="mt-1 line-clamp-3 text-xs leading-5 text-slate-400">
                              {readableMatrixText(c.analysis || c.summary, dimension)}
                            </p>
                            {evIds.length ? <p className="mt-1 font-mono text-[10px] text-slate-500">{evIds.join(" · ")}</p> : null}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          <div>
            <div className="rounded-lg border border-slate-800 bg-slate-900/45 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Risk Flags</p>
              <h4 className="mt-2 text-lg font-semibold text-white">风险标记</h4>
              <div className="mt-3 space-y-2">
                {risks.length ? (
                  risks.slice(0, 5).map((risk, index) => (
                    <div className="rounded-md border border-slate-800 bg-slate-950/60 p-2" key={index}>
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-xs font-semibold text-slate-200">{asString(risk.risk_type) || "risk"}</p>
                        <StatusBadge label={asString(risk.severity) || "—"} tone={normalize(risk.severity) === "high" ? "danger" : "warning"} />
                      </div>
                      <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-400">{asString(risk.description)}</p>
                    </div>
                  ))
                ) : (
                  <EmptyAgentNote label="暂无风险标记。" />
                )}
              </div>
            </div>
          </div>
        </>
      )}

      <SwotAiPanel taskId={taskId} report={report} onDataChanged={onDataChanged} />

      <div className="hidden">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-violet-200">AI Interpretation · 预留</p>
            <h4 className="mt-2 text-lg font-semibold text-white">SWOT / AI 解读区</h4>
          </div>
          <StatusBadge label="LLM 阶段接入" tone="info" />
        </div>
        <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {["S 优势", "W 劣势", "O 机会", "T 威胁"].map((label) => (
            <div className="rounded-md border border-violet-400/25 bg-slate-950/50 p-3" key={label}>
              <p className="text-sm font-semibold text-violet-100">{label}</p>
              <p className="mt-1 text-xs leading-5 text-slate-500">LLM 基于硬件证据生成，每点绑定 evidence_id；O/T 依赖口碑 / 价格，标 pending。</p>
            </div>
          ))}
        </div>
        <p className="mt-3 text-xs leading-5 text-slate-500">
          🟣 此区由 AnalysisAgent 的 LLM 子步骤填充：SWOT、对比解读叙述、prompt 与 token 消耗。未返回时不生成假数据。
        </p>
      </div>
    </AgentDetailFrame>
  );
}

function VerificationAgentDetail({ agent, status, report }: AgentDetailProps) {
  const faithfulness = asRecord(report.faithfulness_report);
  const reviewVerification = asRecord(faithfulness.review_verification);
  const reviewRows = asRecords(reviewVerification.rows);
  const rate = asNumber(faithfulness.faithfulness_rate);
  const ratePct = typeof rate === "number" ? Math.round(rate * 100) : null;
  const claimResults = asRecords(faithfulness.claim_results);
  const matrixIssues = asRecords(faithfulness.matrix_issues);
  const humanFeedback = feedbackRecords(report.human_feedback);
  const checked = asNumber(faithfulness.checked_claim_count) ?? claimResults.length;
  const supported = asNumber(faithfulness.supported_claim_count);
  const unsupported = asNumber(faithfulness.unsupported_claim_count);
  const weak = asNumber(faithfulness.weak_claim_count);
  const hasRun = claimResults.length > 0 || reviewRows.length > 0 || humanFeedback.length > 0 || typeof rate === "number";

  return (
    <AgentDetailFrame
      agent={agent}
      status={status}
      eyebrow="Verification"
      description="事实校验员：检查每条结论是否被所引证据支撑，拦截无来源的数字（幻觉）。"
    >
      {!hasRun ? (
        <EmptyAgentNote label="VerificationAgent 还未运行。开始分析后这里会显示忠实率、逐条校验结果与矩阵数字校验。" />
      ) : (
        <>
          <div className="rounded-lg border border-slate-800 bg-slate-900/45 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Faithfulness</p>
                <h4 className="mt-2 text-lg font-semibold text-white">忠实性校验</h4>
              </div>
              <StatusBadge
                label={`忠实率 ${ratePct ?? "—"}%`}
                tone={ratePct === null ? "neutral" : ratePct >= 90 ? "success" : ratePct >= 70 ? "warning" : "danger"}
              />
            </div>
            {ratePct !== null ? (
              <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-800">
                <div
                  className={`h-full rounded-full ${ratePct >= 90 ? "bg-emerald-400" : ratePct >= 70 ? "bg-amber-400" : "bg-rose-400"}`}
                  style={{ width: `${ratePct}%` }}
                />
              </div>
            ) : null}
            <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
              <StatTile label="已检结论" value={checked} tone="info" />
              <StatTile label="支撑" value={supported ?? "—"} tone="success" />
              <StatTile label="未支撑(幻觉)" value={unsupported ?? "—"} tone={unsupported ? "danger" : "neutral"} />
              <StatTile label="弱支撑" value={weak ?? "—"} tone={weak ? "warning" : "neutral"} />
            </div>
          </div>

          {claimResults.length ? (
            <div className="rounded-lg border border-slate-800 bg-slate-900/45 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Per-claim</p>
              <h4 className="mt-2 text-lg font-semibold text-white">逐条结论校验</h4>
              <div className="mt-3 space-y-2">
                {claimResults.slice(0, 12).map((r, index) => {
                  const supportedItem = r.supported === true;
                  const weakItem = Boolean(r.weak);
                  const grounding = asNumber(r.grounding_score);
                  const missing = asStrings(r.missing_numbers);
                  return (
                    <div className="flex items-start justify-between gap-3 rounded-md border border-slate-800 bg-slate-950/60 px-3 py-2" key={asString(r.claim_id) || index}>
                      <div className="min-w-0">
                        <p className="font-mono text-xs text-slate-300">{asString(r.claim_id) || `claim-${index + 1}`}</p>
                        <p className="mt-0.5 text-xs text-slate-500">
                          {asString(r.reason) || "grounded"}
                          {missing.length ? ` · 缺失数字 ${missing.join(", ")}` : ""}
                          {typeof grounding === "number" ? ` · 词面覆盖 ${Math.round(grounding * 100)}%` : ""}
                        </p>
                      </div>
                      <StatusBadge
                        label={supportedItem ? (weakItem ? "弱支撑" : "支撑") : "未支撑"}
                        tone={supportedItem ? (weakItem ? "warning" : "success") : "danger"}
                      />
                    </div>
                  );
                })}
              </div>
            </div>
          ) : null}

          {reviewRows.length ? (
            <div className="rounded-lg border border-cyan-300/25 bg-cyan-400/10 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-cyan-200">Review Verification</p>
                  <h4 className="mt-2 text-lg font-semibold text-white">测评 / 口碑结论校验</h4>
                </div>
                <StatusBadge label={`${reviewRows.length} signals`} tone="info" />
              </div>
              <div className="mt-3 space-y-2">
                {reviewRows.slice(0, 10).map((row, index) => {
                  const rowStatus = asString(row.status);
                  const evIds = asStrings(row.evidence_ids);
                  return (
                    <div className="rounded-md border border-cyan-300/20 bg-slate-950/60 p-3" key={`${asString(row.product)}-${asString(row.dimension)}-${index}`}>
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="min-w-0">
                          <p className="text-sm font-semibold text-slate-100">
                            {asString(row.product)} · {reviewDimensionLabel(row.dimension)}
                          </p>
                          <p className="mt-1 text-xs leading-5 text-slate-400">{reviewVerificationReasonZh(row.reason)}</p>
                        </div>
                        <StatusBadge
                          label={rowStatus === "supported" ? "已支撑" : rowStatus === "weak_support" ? "弱支撑" : rowStatus === "not_supported" ? "未支撑" : "待校验"}
                          tone={rowStatus === "supported" ? "success" : rowStatus === "weak_support" ? "warning" : "danger"}
                        />
                      </div>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {evIds.length ? evIds.map((id) => <StatusBadge key={id} label={id} tone="neutral" />) : <StatusBadge label="missing evidence" tone="danger" />}
                        <StatusBadge label={localizedConfidence(row.confidence)} tone={credibilityTone(asString(row.confidence))} />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : null}

          {humanFeedback.length ? (
            <div className="rounded-lg border border-violet-400/25 bg-violet-400/10 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-violet-200">Human Feedback Verification</p>
                  <h4 className="mt-2 text-lg font-semibold text-white">人工反馈校验</h4>
                </div>
                <StatusBadge label={`${humanFeedback.length} 条人工输入`} tone="info" />
              </div>
              <div className="mt-3 grid gap-2 lg:grid-cols-2">
                {humanFeedback.map((item, index) => (
                  <div className="rounded-md border border-violet-400/20 bg-slate-950/60 p-3" key={asString(item.feedback_id) || index}>
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusBadge label={asString(item.feedback_id, `HF${index + 1}`)} tone="info" />
                      <StatusBadge label="人工 evidence" tone="warning" />
                      <StatusBadge label={feedbackStatusLabel(item.status)} tone={normalize(item.status) === "applied_to_report" ? "success" : "neutral"} />
                    </div>
                    <p className="mt-2 text-sm leading-6 text-slate-200">{asString(item.message)}</p>
                    <p className="mt-2 text-xs leading-5 text-slate-500">
                      {asString(item.product, "未指定产品")} · {asString(item.dimension, "human_feedback")}。该输入会进入 claim / evidence 校验，但不会直接覆盖最终报告。
                    </p>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-lg border border-slate-800 bg-slate-900/45 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Matrix Numbers</p>
              <h4 className="mt-2 text-lg font-semibold text-white">矩阵数字校验</h4>
              {matrixIssues.length ? (
                <div className="mt-3 space-y-2">
                  {matrixIssues.map((issue, index) => (
                    <div className="rounded-md border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-xs leading-5 text-rose-100" key={index}>
                      {asString(issue.matrix)} · {asString(issue.platform)} · {asString(issue.dimension)}：缺失数字 {asStrings(issue.missing_numbers).join(", ") || "—"}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="mt-3 rounded-md border border-emerald-400/25 bg-emerald-400/10 px-3 py-2 text-sm text-emerald-100">
                  矩阵文案中的数字均可在所引证据中找到，无幻觉数字。
                </p>
              )}
            </div>
            <div className="rounded-lg border border-cyan-300/25 bg-cyan-400/10 p-4">
              <p className="text-sm font-semibold text-cyan-100">校验规则</p>
              <ul className="mt-2 space-y-1 text-xs leading-5 text-slate-300">
                <li>· 结论里出现的数字必须出现在所引证据中，否则判「未支撑」并交质检打回。</li>
                <li>· 词面覆盖过低记为「弱支撑」（软信号，不打回），避免误杀合理改写。</li>
                <li>· 校验确定性、无依赖：无论 LLM 是否开启，行为一致。</li>
              </ul>
            </div>
          </div>
        </>
      )}
    </AgentDetailFrame>
  );
}

function QualityAgentDetail({ agent, status, report, quality }: AgentDetailProps) {
  const q = asRecord(quality);
  const checks = Object.entries(asRecord(q.checked_items));
  const passedCount = checks.filter(([, v]) => v === true).length;
  const score = asNumber(q.quality_score) ?? asNumber(q.score);
  const qStatus = asString(q.status) || asString(report.quality_status) || "pending";
  const rejectTo = asString(q.reject_to) || asString(q.target_agent);
  const required = asStrings(q.required_actions);
  const limitations = asStrings(q.limitations);
  const pendingData = asRecords(q.pending_data);
  const scoreBreakdown = asRecord(q.score_breakdown);
  const baseScore = asNumber(scoreBreakdown.base_score) ?? 90;
  const failedPenalty = asNumber(scoreBreakdown.failed_check_deductions) ?? 0;
  const weakPriceCount = asNumber(scoreBreakdown.weak_price_support_count) ?? 0;
  const weakReviewCount = asNumber(scoreBreakdown.weak_review_support_count) ?? 0;
  const weakClaimCount = asNumber(scoreBreakdown.weak_claim_count) ?? 0;
  const humanUnverifiedCount = asNumber(scoreBreakdown.human_feedback_unverified_count) ?? 0;
  const pendingPenalty = asNumber(scoreBreakdown.pending_data_deductions) ?? 0;
  const highRiskPenalty = asNumber(scoreBreakdown.high_risk_deductions) ?? 0;
  const missingDimensionPenalty = asNumber(scoreBreakdown.missing_dimension_deductions) ?? 0;
  const weakPricePenalty = asNumber(scoreBreakdown.weak_price_deductions) ?? 0;
  const weakReviewPenalty = asNumber(scoreBreakdown.weak_review_deductions) ?? 0;
  const weakClaimPenalty = asNumber(scoreBreakdown.weak_claim_deductions) ?? 0;
  const humanFeedbackPenalty = asNumber(scoreBreakdown.human_feedback_deductions) ?? 0;
  const calculatedScore = Math.max(
    0,
    baseScore -
      failedPenalty -
      pendingPenalty -
      highRiskPenalty -
      missingDimensionPenalty -
      weakPricePenalty -
      weakReviewPenalty -
      weakClaimPenalty -
      humanFeedbackPenalty,
  );
  const iteration = asNumber(asRecord(report.metrics).iteration_count) ?? 0;
  const approved = qStatus === "approved" || qStatus === "approved_with_limitations";
  const hasRun = checks.length > 0;

  return (
    <AgentDetailFrame
      agent={agent}
      status={status}
      eyebrow="Quality"
      description="质量门控员：跑规则检查，决定通过、有限通过或打回上游 Agent 重做（上限 3 次后降级有限报告）。"
    >
      {!hasRun ? (
        <EmptyAgentNote label="QualityAgent 还未运行。开始分析后这里会显示门控检查、报告可信度分与打回闭环。" />
      ) : (
        <>
          <div className="grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
            <div className="rounded-lg border border-slate-800 bg-slate-900/45 p-4 text-center">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Report Credibility</p>
              <p className={`mt-3 text-4xl font-semibold ${approved ? "text-emerald-200" : "text-amber-200"}`}>{score ?? "—"}</p>
              <p className="mt-1 text-xs text-slate-500">报告可信度 / 分析质量分</p>
              <div className="mt-3 flex justify-center">
                <StatusBadge label={qStatus} tone={qualityTone(qStatus)} />
              </div>
              <p className="mt-3 rounded-md border border-cyan-300/25 bg-cyan-300/10 px-2 py-1.5 text-[11px] leading-4 text-cyan-100">
                这里展示「报告可信度」，不是产品综合评分。
              </p>
            </div>

            <div className="rounded-lg border border-slate-800 bg-slate-900/45 p-4">
              <div className="flex items-center justify-between">
                <h4 className="text-lg font-semibold text-white">门控检查</h4>
                <StatusBadge label={`${passedCount}/${checks.length} 通过`} tone={passedCount === checks.length ? "success" : "warning"} />
              </div>
              <div className="mt-3 grid grid-cols-1 gap-1.5 sm:grid-cols-2">
                {checks.map(([key, value]) => {
                  const ok = value === true;
                  return (
                    <div className="flex items-center gap-2 rounded-md border border-slate-800 bg-slate-950/60 px-3 py-1.5 text-xs" key={key}>
                      <span className={ok ? "text-emerald-300" : "text-rose-300"}>{ok ? "✓" : "✗"}</span>
                      <span className="text-slate-300">{QUALITY_CHECK_LABEL[key] || key}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          <div className="rounded-lg border border-amber-400/30 bg-amber-400/10 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm font-semibold text-amber-100">反馈闭环</p>
              <StatusBadge label={`迭代 ${iteration} / 3`} tone={iteration >= 3 ? "danger" : "warning"} />
            </div>
            {rejectTo ? (
              <div className="mt-3 flex items-center gap-2 text-xs">
                <StatusBadge label="QualityAgent" tone="neutral" />
                <span className="text-amber-200">↩ 打回</span>
                <StatusBadge label={rejectTo} tone="warning" />
              </div>
            ) : (
              <p className="mt-3 text-xs leading-5 text-emerald-100">本轮无需打回；如有 pending 数据会降低可信度但不打回。</p>
            )}
            {required.length ? (
              <ul className="mt-3 space-y-1 text-xs leading-5 text-amber-100/90">
                {required.map((action, index) => (
                  <li key={index}>· {action}</li>
                ))}
              </ul>
            ) : null}
            <p className="mt-3 text-[11px] leading-4 text-amber-100/70">连续 3 次自动修复仍不达标时，降级为 partial_report 并披露限制，不阻塞流程。</p>
          </div>

          <div className="rounded-lg border border-slate-800 bg-slate-900/45 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Score Reason</p>
                <h4 className="mt-2 text-lg font-semibold text-white">可信度扣分原因</h4>
              </div>
              <StatusBadge label="报告可信度，不是产品分" tone="info" />
            </div>
            <div className="mt-3 rounded-lg border border-cyan-300/20 bg-cyan-300/10 p-3">
              <div className="flex flex-wrap items-end justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold text-cyan-100">计算公式</p>
                  <p className="mt-1 text-sm leading-6 text-slate-300">
                    基础 {baseScore} - 门控 {failedPenalty} - 待补 {pendingPenalty} - 风险 {highRiskPenalty} - 缺失维度 {missingDimensionPenalty}
                    - 弱价格 {weakPricePenalty} - 弱测评 {weakReviewPenalty} - 弱 claim {weakClaimPenalty} - 人工待证 {humanFeedbackPenalty}
                  </p>
                </div>
                <p className="text-2xl font-semibold text-cyan-100">= {score ?? calculatedScore}</p>
              </div>
            </div>
            <div className="mt-3 grid gap-2 sm:grid-cols-4">
              <StatTile label="待补数据扣分" value={pendingPenalty} tone={pendingPenalty ? "warning" : "neutral"} />
              <StatTile label="门控失败扣分" value={failedPenalty} tone={failedPenalty ? "danger" : "neutral"} />
              <StatTile label="风险披露扣分" value={highRiskPenalty} tone={highRiskPenalty ? "warning" : "neutral"} />
              <StatTile label="缺失维度扣分" value={missingDimensionPenalty} tone={missingDimensionPenalty ? "warning" : "neutral"} />
              <StatTile label="弱价格扣分" value={weakPricePenalty} tone={weakPricePenalty ? "warning" : "neutral"} />
              <StatTile label="弱测评扣分" value={weakReviewPenalty} tone={weakReviewPenalty ? "warning" : "neutral"} />
              <StatTile label="弱 claim 扣分" value={weakClaimPenalty} tone={weakClaimPenalty ? "warning" : "neutral"} />
              <StatTile label="人工待证扣分" value={humanFeedbackPenalty} tone={humanFeedbackPenalty ? "danger" : "neutral"} />
            </div>
            <p className="mt-3 text-xs leading-5 text-slate-400">
              当前 {score ?? calculatedScore} 分来自 QualityAgent 对 pending 数据、门控失败、风险披露、缺失维度、弱支撑与人工待验证输入的综合扣分。
              官方价格被拦截、只拿到低可信电商/搜索价格，或人工反馈缺少外部 evidence，都会直接拉低报告可信度。
            </p>
            {pendingData.length ? (
              <div className="mt-3 flex flex-wrap gap-2">
                {pendingData.slice(0, 5).map((item, index) => (
                  <StatusBadge key={index} label={asString(item.agent) || asString(item.status) || `pending ${index + 1}`} tone="warning" />
                ))}
              </div>
            ) : null}
            {(weakPriceCount || weakReviewCount || weakClaimCount || humanUnverifiedCount) ? (
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                {weakPriceCount ? (
                  <div className="rounded-md border border-amber-300/25 bg-amber-300/10 p-3">
                    <p className="text-sm font-semibold text-amber-100">价格弱支撑 × {weakPriceCount}</p>
                    <p className="mt-1 text-xs leading-5 text-amber-100/75">价格来源可信度不足时，只能参与风险披露，不能当作强性价比结论。</p>
                  </div>
                ) : null}
                {weakReviewCount ? (
                  <div className="rounded-md border border-amber-300/25 bg-amber-300/10 p-3">
                    <p className="text-sm font-semibold text-amber-100">测评弱支撑 × {weakReviewCount}</p>
                    <p className="mt-1 text-xs leading-5 text-amber-100/75">体验类结论需要用户评价或博主测评交叉印证，证据不足时只做保守表达。</p>
                  </div>
                ) : null}
                {weakClaimCount ? (
                  <div className="rounded-md border border-amber-300/25 bg-amber-300/10 p-3">
                    <p className="text-sm font-semibold text-amber-100">弱 claim × {weakClaimCount}</p>
                    <p className="mt-1 text-xs leading-5 text-amber-100/75">claim 有引用但支撑强度不足，进入限制项披露。</p>
                  </div>
                ) : null}
                {humanUnverifiedCount ? (
                  <div className="rounded-md border border-rose-300/25 bg-rose-300/10 p-3">
                    <p className="text-sm font-semibold text-rose-100">人工反馈待验证 × {humanUnverifiedCount}</p>
                    <p className="mt-1 text-xs leading-5 text-rose-100/75">人工输入不能自证为事实，需要 CollectorAgent 补充外部来源后才能进入强结论。</p>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>

          {limitations.length ? (
            <div className="rounded-lg border border-slate-800 bg-slate-900/45 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Limitations</p>
                  <h4 className="mt-2 text-lg font-semibold text-white">报告限制说明</h4>
                </div>
                <StatusBadge label={`${limitations.length} 项`} tone="warning" />
              </div>
              <div className="mt-3 grid gap-2 lg:grid-cols-3">
                {limitations.map((lim) => {
                  const copy = LIMITATION_COPY[lim] || {
                    label: lim,
                    detail: "该限制项已被 QualityAgent 披露，最终报告需要保守表达。",
                    tone: "warning" as Tone,
                  };
                  return (
                    <div className="rounded-md border border-amber-300/25 bg-amber-300/10 p-3" key={lim}>
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="text-sm font-semibold text-amber-50">{copy.label}</p>
                        <StatusBadge label={lim} tone={copy.tone} />
                      </div>
                      <p className="mt-2 text-xs leading-5 text-amber-100/75">{copy.detail}</p>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : null}
        </>
      )}
    </AgentDetailFrame>
  );
}

function ReportAgentDetail({ agent, status, report, quality: qualityResult, onNavigate }: AgentDetailProps) {
  const execSummary = asStrings(report.executive_summary);
  const rec = asRecord(report.final_recommendation);
  const metrics = asRecord(report.metrics);
  const summary = asRecord(report.summary);
  const humanFeedback = feedbackRecords(report.human_feedback);
  const humanFeedbackNote = asString(report.human_feedback_note);
  const quality = asString(report.quality_status) || "pending";
  const qualityScore =
    asNumber(asRecord(qualityResult).quality_score) ??
    asNumber(asRecord(report.quality_result).quality_score) ??
    asNumber(metrics.quality_score);
  const hasReport = execSummary.length > 0 || Object.keys(rec).length > 0;
  const pct = (value: unknown) => {
    const n = asNumber(value);
    return typeof n === "number" ? `${Math.round(n * 100)}%` : "—";
  };

  return (
    <AgentDetailFrame
      agent={agent}
      status={status}
      eyebrow="Report"
      description="报告撰写员：整合已验证的硬件事实、证据链与质量门控，输出最终竞品报告（不新增证据）。"
    >
      {!hasReport ? (
        <EmptyAgentNote label="ReportAgent 还未生成报告。工作流跑完后这里会显示执行摘要、场景化建议、可信度与追溯指标。" />
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-cyan-300/25 bg-cyan-400/10 p-4">
            <div>
              <p className="text-sm font-semibold text-cyan-100">最终报告状态：{quality}</p>
              <p className="mt-1 text-xs text-slate-400">
                证据 {formatValue(summary.evidence_count, "—")} 条 · claims {formatValue(summary.claim_count, "—")} 条 · pending {formatValue(summary.pending_count, "—")} 项
              </p>
            </div>
            {onNavigate ? (
              <button
                className="rounded-md bg-cyan-300 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-200"
                onClick={() => onNavigate("report")}
                type="button"
              >
                查看完整报告
              </button>
            ) : null}
          </div>

          {execSummary.length ? (
            <div className="rounded-lg border border-slate-800 bg-slate-900/45 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Executive Summary</p>
              <h4 className="mt-2 text-lg font-semibold text-white">执行摘要</h4>
              <ul className="mt-3 space-y-2">
                {execSummary.map((line, index) => (
                  <li className="rounded-md border border-slate-800 bg-slate-950/60 px-3 py-2 text-sm leading-6 text-slate-300" key={index}>
                    {line}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-lg border border-slate-800 bg-slate-900/45 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Final Recommendation</p>
              <h4 className="mt-2 text-lg font-semibold text-white">最终建议</h4>
              <p className="mt-2 text-sm font-semibold text-cyan-200">{asString(rec.recommended_product) || "待定"}</p>
              {asString(rec.reason) ? <p className="mt-1 text-xs leading-5 text-slate-400">{asString(rec.reason)}</p> : null}
              {asStrings(rec.top_reasons).length ? (
                <ul className="mt-2 space-y-1 text-xs leading-5 text-slate-300">
                  {asStrings(rec.top_reasons).map((reason, index) => (
                    <li key={index}>· {reason}</li>
                  ))}
                </ul>
              ) : null}
            </div>

            <div className="rounded-lg border border-slate-800 bg-slate-900/45 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Credibility Metrics</p>
              <h4 className="mt-2 text-lg font-semibold text-white">可信度与追溯指标</h4>
              <div className="mt-3 grid grid-cols-2 gap-2 lg:grid-cols-4">
                <StatTile label="报告可信度" value={qualityScore ?? "—"} tone="info" />
                <StatTile label="引用率" value={pct(metrics.citation_rate)} tone="success" />
                <StatTile label="覆盖率" value={pct(metrics.coverage_rate)} tone="info" />
                <StatTile label="忠实率" value={pct(metrics.faithfulness_rate)} tone="success" />
              </div>
              <p className="mt-2 text-[11px] leading-4 text-slate-500">这里展示报告质量，不展示产品综合分；最终结论以场景化建议和证据链为准。</p>
            </div>
          </div>

          {humanFeedback.length ? (
            <div className="rounded-lg border border-violet-400/25 bg-violet-400/10 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-violet-200">Human Correction</p>
                  <h4 className="mt-2 text-lg font-semibold text-white">人工修正已并入报告链路</h4>
                </div>
                <StatusBadge label={`${humanFeedback.length} 条`} tone="info" />
              </div>
              {humanFeedbackNote ? <p className="mt-2 text-xs leading-5 text-slate-400">{humanFeedbackNote}</p> : null}
              <div className="mt-3 grid gap-2 lg:grid-cols-2">
                {humanFeedback.slice(0, 4).map((item, index) => (
                  <div className="rounded-md border border-violet-400/20 bg-slate-950/60 p-3" key={asString(item.feedback_id) || index}>
                    <div className="flex flex-wrap items-center gap-1.5">
                      <StatusBadge label={asString(item.feedback_id, `HF${index + 1}`)} tone="info" />
                      <StatusBadge label={feedbackStatusLabel(item.status)} tone={normalize(item.status) === "applied_to_report" ? "success" : "warning"} />
                    </div>
                    <p className="mt-2 text-sm leading-6 text-slate-200">{asString(item.message)}</p>
                    <p className="mt-1 text-xs text-slate-500">
                      {asString(item.product, "未指定产品")} · {asString(item.dimension, "human_feedback")}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          <div className="hidden">
            🟣 SWOT 摘要与 AI 叙述将在 LLM 阶段由 AnalysisAgent 产出后并入本报告。
          </div>
        </>
      )}
    </AgentDetailFrame>
  );
}

function GenericAgentDetail({ agent, status, trace }: AgentDetailProps) {
  return (
    <section className="rounded-lg border border-slate-800 bg-slate-950/75 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">Agent Detail</p>
          <h3 className="mt-2 text-2xl font-semibold text-white">{agent.name}</h3>
          <p className="mt-1 text-sm text-slate-400">{agent.role}</p>
        </div>
        <StatusBadge label={STATUS_LABEL[status]} tone={STATUS_TONE[status]} />
      </div>
      <div className="mt-5 grid gap-4 md:grid-cols-3">
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">输入</p>
          <p className="mt-2 text-sm leading-6 text-slate-300">{agent.input}</p>
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">输出</p>
          <p className="mt-2 text-sm leading-6 text-slate-300">{agent.output}</p>
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">当前摘要</p>
          <p className="mt-2 text-sm leading-6 text-slate-300">
            {trace?.output_summary || "完整报告在「竞品分析报告」页查看；该 Agent 的中间产物已并入最终报告。"}
          </p>
        </div>
      </div>
    </section>
  );
}

function AgentDetailPlaceholder(props: AgentDetailProps) {
  switch (props.agent.name) {
    case "ResearchAgent":
      return (
        <ResearchAgentPlanningDetail
          agent={props.agent}
          report={props.report}
          status={props.status}
          trace={props.trace}
          unresolvedProducts={props.unresolvedProducts}
          externalProductCandidates={props.externalProductCandidates}
        />
      );
    case "CollectorAgent":
      return <CollectorAgentDetail {...props} />;
    case "EvidenceAgent":
      return <EvidenceAgentDetail {...props} />;
    case "AnalysisAgent":
      return <AnalysisAgentDetail {...props} />;
    case "VerificationAgent":
      return <VerificationAgentDetail {...props} />;
    case "QualityAgent":
      return <QualityAgentDetail {...props} />;
    case "ReportAgent":
      return <ReportAgentDetail {...props} />;
    default:
      return <GenericAgentDetail {...props} />;
  }
}

function AgentWorkbench({
  selectedAgent,
  onOpenAgent,
  currentAgent,
  agentStatuses,
  traces,
}: {
  selectedAgent: string;
  onOpenAgent: (agentName: string) => void;
  currentAgent: string;
  agentStatuses: Record<string, AgentStatus>;
  traces: Record<string, AgentTrace>;
}) {
  const selected = AGENTS.find((agent) => agent.name === selectedAgent) ?? AGENTS[0];

  return (
    <section className="mt-5 rounded-lg border border-slate-800 bg-slate-950/70 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">
            Agent Cards
          </p>
          <h3 className="mt-2 text-xl font-semibold text-white">七个 Agent 任务卡片</h3>
        </div>
        <p className="text-sm text-slate-500">
          点击左侧控制台 Agent 任务栏或下方卡片，会进入对应 Agent 的独立详情页。
        </p>
      </div>
      <div className="mt-4">
        <AgentCardGrid
          agentStatuses={agentStatuses}
          currentAgent={currentAgent}
          onSelectAgent={onOpenAgent}
          selectedAgent={selected.name}
          traces={traces}
        />
      </div>
    </section>
  );
}

function CompetitiveReportEntry({
  hasReport,
  onNavigate,
}: {
  hasReport: boolean;
  onNavigate: (key: string) => void;
}) {
  return (
    <section className="mt-5 rounded-lg border border-cyan-300/25 bg-slate-950/75 p-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">
            Competitive Report
          </p>
          <h3 className="mt-2 text-2xl font-semibold text-white">竞品分析报告</h3>
          <p className="mt-2 text-sm leading-6 text-slate-400">
            Agent 工作流完成后，最终报告会汇总硬件事实、证据限制、pending 数据和综合建议。
          </p>
        </div>
        <button
          className={`rounded-md px-4 py-2 text-sm font-semibold transition ${
            hasReport
              ? "bg-cyan-300 text-slate-950 hover:bg-cyan-200"
              : "cursor-not-allowed border border-slate-700 bg-slate-900/80 text-slate-500"
          }`}
          disabled={!hasReport}
          onClick={() => hasReport && onNavigate("report")}
          type="button"
        >
          {hasReport ? "查看最终报告" : "等待报告生成"}
        </button>
      </div>
    </section>
  );
}

function AgentDetailPage({
  taskId,
  agent,
  status,
  trace,
  report,
  evidenceList,
  claims,
  resolvedProducts,
  unresolvedProducts,
  searchMcpResults,
  externalProductCandidates,
  quality,
  onNavigate,
  onDataChanged,
  onBack,
}: {
  taskId?: string;
  agent: AgentDefinition;
  status: AgentStatus;
  trace?: AgentTrace;
  report: Record<string, unknown>;
  evidenceList: Record<string, unknown>[];
  claims: Claim[];
  resolvedProducts: Record<string, unknown>[];
  unresolvedProducts: string[];
  searchMcpResults: SearchMcpResult[];
  externalProductCandidates: ExternalProductCandidate[];
  quality?: QualityResult;
  onNavigate?: (key: string) => void;
  onDataChanged?: () => void;
  onBack: () => void;
}) {
  return (
    <section className="mx-auto max-w-7xl">
      <div className="mb-5 flex flex-col gap-3 rounded-lg border border-slate-800 bg-slate-950/75 p-5 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">
            Agent Detail Page
          </p>
          <h2 className="mt-2 text-2xl font-semibold text-white">{agent.name}</h2>
          <p className="mt-1 text-sm text-slate-400">{agent.role}</p>
        </div>
        <button
          className="rounded-md border border-slate-700 bg-slate-900/80 px-4 py-2 text-sm font-semibold text-slate-200 transition hover:border-cyan-300/50 hover:text-cyan-100"
          onClick={onBack}
          type="button"
        >
          返回 Agent 工作流
        </button>
      </div>
      <AgentDetailPlaceholder
        agent={agent}
        taskId={taskId}
        report={report}
        status={status}
        trace={trace}
        evidenceList={evidenceList}
        claims={claims}
        resolvedProducts={resolvedProducts}
        unresolvedProducts={unresolvedProducts}
        searchMcpResults={searchMcpResults}
        externalProductCandidates={externalProductCandidates}
        quality={quality}
        onNavigate={onNavigate}
        onDataChanged={onDataChanged}
      />
    </section>
  );
}

export function WorkflowPage({
  taskId,
  displayTaskId,
  agentDetailName,
  onAgentOpen,
  onAgentDetailClose,
  selectedAgent,
  onSelectedAgentChange,
  onSidebarAgentsChange,
  onNavigate,
}: WorkflowPageProps) {
  const [status, setStatus] = useState<AnalysisStatus | null>(null);
  const [traceLog, setTraceLog] = useState<AgentTrace[]>([]);
  const [quality, setQuality] = useState<QualityResult | undefined>();
  const [reportResponse, setReportResponse] = useState<ReportResponse | FinalReport | null>(null);
  const [claims, setClaims] = useState<Claim[]>([]);
  const [artifacts, setArtifacts] = useState<ArtifactsSummary | null>(null);
  const [risks, setRisks] = useState<Record<string, unknown>[]>([]);
  const [errors, setErrors] = useState<ErrorLogItem[]>([]);
  const [reviewTicket, setReviewTicket] = useState<ReviewTicket | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [manualRefreshTick, setManualRefreshTick] = useState(0);

  useEffect(() => {
    if (!taskId) return;
    const activeTaskId: string = taskId;
    let cancelled = false;
    let inFlight = false;
    let timer: number | undefined;

    async function refresh() {
      if (inFlight) return;
      inFlight = true;
      setIsRefreshing(true);
      try {
        const [nextStatus, nextTrace, nextQuality, nextReport, nextClaims, nextArtifacts, nextRisks, nextErrors] =
          await Promise.all([
            analysisApi.getStatus(activeTaskId),
            analysisApi.getTrace(activeTaskId),
            analysisApi.getQuality(activeTaskId),
            analysisApi.getReport(activeTaskId),
            analysisApi.getClaims(activeTaskId),
            analysisApi.getArtifacts(activeTaskId),
            analysisApi.getRisks(activeTaskId),
            analysisApi.getErrors(activeTaskId),
          ]);
        if (cancelled) return;
        setStatus(nextStatus);
        setTraceLog(Array.isArray(nextTrace.trace_log) ? nextTrace.trace_log : []);
        setQuality(nextQuality.quality_result);
        setReportResponse(nextReport as ReportResponse);
        setClaims(Array.isArray(nextClaims.claims) ? nextClaims.claims : []);
        setArtifacts(nextArtifacts);
        setRisks(asRecords(nextRisks.risk_flags));
        setErrors(Array.isArray(nextErrors.error_log) ? nextErrors.error_log : []);
        setReviewTicket(nextTrace.review_ticket ?? nextQuality.review_ticket ?? null);
        setError(null);
        if (nextStatus.current_agent && nextStatus.current_agent !== "ReportAgent") {
          onSelectedAgentChange(nextStatus.current_agent);
        }
        if (isFinalDone(nextStatus) && timer) {
          window.clearInterval(timer);
          timer = undefined;
        }
      } catch (refreshError) {
        if (!cancelled) {
          setError(refreshError instanceof Error ? refreshError.message : "刷新工作流失败");
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
          setIsRefreshing(false);
        }
        inFlight = false;
      }
    }

    setIsLoading(true);
    refresh();
    timer = window.setInterval(refresh, 700);
    return () => {
      cancelled = true;
      if (timer) window.clearInterval(timer);
    };
  }, [taskId, onSelectedAgentChange, manualRefreshTick]);

  const report = useMemo(() => {
    const nextReport = extractReport(reportResponse);
    const resp = asRecord(reportResponse);
    const officialSpecs = asRecords(resp.official_spec_records) as OfficialSpecRecord[];
    const reviewIntelRecords = asRecords(resp.review_intel_records) as ReviewIntelRecord[];
    const reviewIntelStatus = asRecord(resp.review_intel_status);
    const priceRecords = asRecords(resp.price_records);
    const priceStatus = asRecord(resp.price_status);
    const analysisAi = asRecord(resp.analysis_ai_interpretation);
    const humanFeedback = asRecords(resp.human_feedback) as HumanFeedbackRecord[];
    return {
      ...nextReport,
      ...(officialSpecs.length ? { official_spec_records: officialSpecs } : {}),
      ...(reviewIntelRecords.length ? { review_intel_records: reviewIntelRecords } : {}),
      ...(Object.keys(reviewIntelStatus).length ? { review_intel_status: reviewIntelStatus } : {}),
      ...(priceRecords.length ? { price_records: priceRecords } : {}),
      ...(Object.keys(priceStatus).length ? { price_status: priceStatus } : {}),
      ...(Object.keys(analysisAi).length ? { analysis_ai_interpretation: analysisAi } : {}),
      ...(humanFeedback.length ? { human_feedback: humanFeedback } : {}),
    };
  }, [reportResponse]);
  const mcpTools = useMemo(() => mcpToolsFromReport(report), [report]);
  const evidenceList = useMemo(
    () => asRecords(asRecord(reportResponse).evidence_list),
    [reportResponse],
  );
  const resolvedProducts = useMemo(
    () => asRecords(asRecord(reportResponse).resolved_products),
    [reportResponse],
  );
  const unresolvedProducts = useMemo(
    () => asStrings(asRecord(reportResponse).unresolved_products),
    [reportResponse],
  );
  const searchMcpResults = useMemo(
    () => asRecords(asRecord(reportResponse).search_mcp_results) as SearchMcpResult[],
    [reportResponse],
  );
  const externalProductCandidates = useMemo(
    () => asRecords(asRecord(reportResponse).external_product_candidates) as ExternalProductCandidate[],
    [reportResponse],
  );
  const traceByAgent = useMemo(() => traceMap(traceLog), [traceLog]);
  const qualityStatus = qualityStatusText(status, quality, reportResponse, report);
  const hasReport = Boolean(
    artifacts?.has_final_report || Object.keys(report).length > 0 || status?.current_agent === "ReportAgent",
  );
  const progress = status?.progress ?? Math.round((traceLog.length / AGENTS.length) * 100);
  const currentAgent = status?.current_agent || "等待任务";

  const agentStatuses = useMemo(() => AGENTS.reduce<Record<string, AgentStatus>>((acc, agent) => {
    acc[agent.name] = deriveStatus(agent, traceByAgent[agent.name], status, qualityStatus, hasReport);
    return acc;
  }, {}), [hasReport, qualityStatus, status, traceByAgent]);

  useEffect(() => {
    onSidebarAgentsChange?.(
      AGENTS.map((agent) => ({
        name: agent.name,
        role: agent.role,
        status: agentStatuses[agent.name] ?? "waiting",
        current: currentAgent === agent.name,
        selected: agentDetailName === agent.name,
      })),
    );

    return () => {
      onSidebarAgentsChange?.([]);
    };
  }, [agentDetailName, agentStatuses, currentAgent, onSidebarAgentsChange]);

  const detailAgent = agentDetailName
    ? (AGENTS.find((agent) => agent.name === agentDetailName) ?? null)
    : null;

  if (!taskId) {
    return (
      <section className="mx-auto max-w-5xl">
        <EmptyState
          action={
            <button
              className="rounded-md bg-cyan-300 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-200"
              onClick={() => onNavigate("product-compare")}
              type="button"
            >
              回到产品输入
            </button>
          }
          description="先输入两款电竞鼠标并点击开始分析，系统才会进入多 Agent 工作流。"
          title="暂无分析任务"
        />
      </section>
    );
  }

  if (detailAgent) {
    return (
      <section>
        {isLoading ? <LoadingState label="正在读取 Agent 详情..." /> : null}
        {error ? (
          <div className="mb-5 rounded-md border border-amber-400/35 bg-amber-400/10 px-4 py-3 text-sm text-amber-100">
            {error}
          </div>
        ) : null}
        <AgentDetailPage
          agent={detailAgent}
          taskId={taskId}
          onBack={onAgentDetailClose}
          report={report}
          status={agentStatuses[detailAgent.name] ?? "waiting"}
          trace={traceByAgent[detailAgent.name]}
          evidenceList={evidenceList}
          claims={claims}
          resolvedProducts={resolvedProducts}
          unresolvedProducts={unresolvedProducts}
          searchMcpResults={searchMcpResults}
          externalProductCandidates={externalProductCandidates}
          quality={quality}
          onNavigate={onNavigate}
          onDataChanged={() => setManualRefreshTick((value) => value + 1)}
        />
      </section>
    );
  }

  return (
    <section className="mx-auto max-w-7xl">
      <WorkflowDagCanvas
        agentStatuses={agentStatuses}
        currentAgent={currentAgent}
        displayTaskId={displayTaskId}
        hasReport={hasReport}
        mcpTools={mcpTools}
        onNavigate={onNavigate}
        onSelectAgent={onAgentOpen}
        progress={progress}
        selectedAgent={selectedAgent}
        taskId={taskId}
        taskStatus={status?.status}
      />

      {isLoading ? <LoadingState label="正在读取工作流状态..." /> : null}

      {error ? (
        <div className="mt-5 rounded-md border border-amber-400/35 bg-amber-400/10 px-4 py-3 text-sm text-amber-100">
          {error}
        </div>
      ) : null}

      <AgentWorkbench
        agentStatuses={agentStatuses}
        currentAgent={currentAgent}
        selectedAgent={selectedAgent}
        onOpenAgent={onAgentOpen}
        traces={traceByAgent}
      />
      <CompetitiveReportEntry hasReport={hasReport} onNavigate={onNavigate} />
    </section>
  );
}
