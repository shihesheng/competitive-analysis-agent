import { useEffect, useMemo, useState } from "react";
import { analysisApi } from "../api/analysisApi";
import type {
  LlmUsageRecord,
  McpUsageRecord,
  ObservabilityAgentTrace,
  ObservabilityPerAgent,
  ObservabilityResponse,
} from "../types/analysis";

type ObservabilityPageProps = {
  displayTaskId?: string;
  onNavigate: (page: string) => void;
  taskId?: string;
};

const agentLabels: Record<string, string> = {
  ResearchAgent: "调研规划",
  CollectorAgent: "采集与实体识别",
  EvidenceAgent: "证据结构化",
  AnalysisAgent: "分析与 SWOT",
  VerificationAgent: "事实校验",
  QualityAgent: "质量门控",
  ReportAgent: "报告生成",
};

const toolLabels: Record<string, string> = {
  official_spec_mcp: "官网规格 MCP + LLM",
  price_mcp: "实时价格 MCP + LLM",
  review_intel_mcp: "评价测评 MCP + LLM",
  swot_ai: "SWOT AI 解读",
  search_mcp: "Search MCP",
};

function number(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function formatMs(value?: number): string {
  const ms = number(value);
  if (ms <= 0) return "-";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function formatMoney(value?: number): string {
  return `$${number(value).toFixed(5)}`;
}

function statusClass(status?: string): string {
  const value = String(status || "").toLowerCase();
  if (["completed", "success", "collected", "available"].includes(value)) {
    return "border-emerald-300/30 bg-emerald-400/10 text-emerald-200";
  }
  if (["running", "partial", "partial_collected"].includes(value)) {
    return "border-cyan-300/30 bg-cyan-400/10 text-cyan-200";
  }
  if (["failed", "error", "llm_failed"].includes(value)) {
    return "border-rose-300/30 bg-rose-400/10 text-rose-200";
  }
  if (["pending", "waiting", "no_sources", "no_price_found"].includes(value)) {
    return "border-amber-300/30 bg-amber-400/10 text-amber-200";
  }
  return "border-slate-500/40 bg-slate-800/80 text-slate-300";
}

function StatusBadge({ status }: { status?: string }) {
  return (
    <span className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${statusClass(status)}`}>
      {status || "waiting"}
    </span>
  );
}

function EmptyState({ onNavigate }: { onNavigate: (page: string) => void }) {
  return (
    <section className="mx-auto mt-16 max-w-3xl rounded-xl border border-slate-700/80 bg-slate-950/65 p-10 text-center">
      <p className="text-xs font-semibold uppercase tracking-[0.35em] text-cyan-300">Agent Observability</p>
      <h1 className="mt-3 text-2xl font-bold text-slate-50">暂无可观测任务</h1>
      <p className="mt-3 text-sm text-slate-400">
        先创建一次电竞鼠标分析任务，系统会记录 Agent 时间线、MCP 调用、LLM token 和 LangSmith 状态。
      </p>
      <button
        className="mt-6 rounded-lg bg-cyan-300 px-5 py-2.5 text-sm font-bold text-slate-950 transition hover:bg-cyan-200"
        onClick={() => onNavigate("product-compare")}
        type="button"
      >
        回到产品输入
      </button>
    </section>
  );
}

function MetricCard({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-slate-700/80 bg-slate-950/70 p-4">
      <p className="text-xs uppercase tracking-[0.25em] text-slate-500">{label}</p>
      <p className="mt-2 text-2xl font-black text-slate-50">{value}</p>
      {hint ? <p className="mt-1 text-xs text-slate-500">{hint}</p> : null}
    </div>
  );
}

function AgentTimeline({ agents }: { agents: ObservabilityAgentTrace[] }) {
  return (
    <section className="rounded-xl border border-slate-700/80 bg-slate-950/60 p-5">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.35em] text-cyan-300">Agent Timeline</p>
          <h2 className="mt-2 text-xl font-bold text-slate-50">Agent 运行时间线</h2>
        </div>
        <span className="rounded-full border border-cyan-300/30 bg-cyan-400/10 px-3 py-1 text-xs font-semibold text-cyan-100">
          {agents.length} agents
        </span>
      </div>
      <div className="mt-5 grid gap-3 lg:grid-cols-7">
        {agents.map((agent) => (
          <div
            className={`rounded-lg border p-4 transition hover:-translate-y-0.5 hover:border-cyan-300/70 hover:bg-cyan-400/10 ${statusClass(agent.status)}`}
            key={agent.agent}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-semibold text-slate-400">{String(agent.order).padStart(2, "0")}</span>
              <StatusBadge status={agent.status} />
            </div>
            <h3 className="mt-3 truncate text-sm font-black text-slate-50">{agent.agent}</h3>
            <p className="mt-1 text-xs text-slate-400">{agentLabels[agent.agent] || "Agent"}</p>
            <div className="mt-4 space-y-1.5 text-xs text-slate-300">
              <p>耗时：{formatMs(agent.duration_ms)}</p>
              <p>MCP：{agent.calls_mcp ? `${agent.mcp_call_count || 1} 次` : "未调用"}</p>
              <p>LLM：{agent.calls_llm ? `${agent.llm_call_count || 1} 次` : "未调用"}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function TokenByAgent({ rows }: { rows: ObservabilityPerAgent[] }) {
  const activeRows = rows.filter((item) => number(item.total_tokens) > 0 || number(item.llm_call_count) > 0);
  return (
    <section className="rounded-xl border border-slate-700/80 bg-slate-950/60 p-5">
      <p className="text-xs font-semibold uppercase tracking-[0.35em] text-cyan-300">Token Board</p>
      <h2 className="mt-2 text-xl font-bold text-slate-50">按 Agent 拆分</h2>
      {activeRows.length ? (
        <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {activeRows.map((row) => (
            <div className="rounded-lg border border-slate-700/80 bg-slate-900/60 p-4" key={row.agent}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="font-bold text-slate-50">{row.agent}</h3>
                  <p className="text-xs text-slate-500">{agentLabels[row.agent] || "LLM 节点"}</p>
                </div>
                <span className="rounded-full border border-cyan-300/25 bg-cyan-400/10 px-2 py-1 text-xs text-cyan-100">
                  {number(row.llm_call_count)} calls
                </span>
              </div>
              <div className="mt-4 grid grid-cols-2 gap-2 text-sm">
                <span className="text-slate-500">Prompt</span>
                <span className="text-right font-semibold text-slate-200">{number(row.prompt_tokens).toLocaleString()}</span>
                <span className="text-slate-500">Completion</span>
                <span className="text-right font-semibold text-slate-200">{number(row.completion_tokens).toLocaleString()}</span>
                <span className="text-slate-500">Total</span>
                <span className="text-right font-semibold text-cyan-100">{number(row.total_tokens).toLocaleString()}</span>
                <span className="text-slate-500">费用估算</span>
                <span className="text-right font-semibold text-emerald-100">{formatMoney(row.estimated_cost_usd)}</span>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-5 rounded-lg border border-slate-700/70 bg-slate-900/50 p-4 text-sm text-slate-400">
          当前任务还没有记录到 LLM token。规则节点会显示在 Agent 时间线里，但不计入 token。
        </p>
      )}
    </section>
  );
}

function CallsTable({ llm, mcp }: { llm: LlmUsageRecord[]; mcp: McpUsageRecord[] }) {
  const rows = [
    ...llm.map((item) => ({ kind: "LLM", ...item })),
    ...mcp.map((item) => ({ kind: "MCP", ...item, model: item.provider || "", total_tokens: 0 })),
  ];
  return (
    <section className="rounded-xl border border-slate-700/80 bg-slate-950/60 p-5">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.35em] text-cyan-300">LLM / MCP Calls</p>
          <h2 className="mt-2 text-xl font-bold text-slate-50">调用明细</h2>
        </div>
        <span className="rounded-full border border-slate-600 bg-slate-900 px-3 py-1 text-xs text-slate-300">
          {rows.length} records
        </span>
      </div>
      <div className="mt-5 overflow-hidden rounded-lg border border-slate-800">
        <table className="w-full min-w-[900px] border-collapse text-left text-sm">
          <thead className="bg-slate-900/90 text-xs uppercase tracking-[0.22em] text-slate-500">
            <tr>
              <th className="px-4 py-3">类型</th>
              <th className="px-4 py-3">Agent</th>
              <th className="px-4 py-3">工具</th>
              <th className="px-4 py-3">模型 / Provider</th>
              <th className="px-4 py-3">状态</th>
              <th className="px-4 py-3">耗时</th>
              <th className="px-4 py-3">Tokens</th>
              <th className="px-4 py-3">说明</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {rows.length ? (
              rows.map((row, index) => (
                <tr className="bg-slate-950/35 text-slate-300" key={`${row.kind}-${row.tool}-${index}`}>
                  <td className="px-4 py-3 font-semibold text-cyan-100">{row.kind}</td>
                  <td className="px-4 py-3">{row.agent || "-"}</td>
                  <td className="px-4 py-3">{toolLabels[String(row.tool || "")] || row.tool || "-"}</td>
                  <td className="px-4 py-3">{row.model || "-"}</td>
                  <td className="px-4 py-3"><StatusBadge status={row.status} /></td>
                  <td className="px-4 py-3">{formatMs(row.latency_ms)}</td>
                  <td className="px-4 py-3">{number(row.total_tokens).toLocaleString()}</td>
                  <td className="max-w-[320px] truncate px-4 py-3 text-slate-500">
                    {"query" in row && row.query
                      ? row.query
                      : "error" in row && row.error
                        ? row.error
                        : "usage_source" in row && row.usage_source
                          ? row.usage_source
                          : "-"}
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td className="px-4 py-6 text-center text-slate-500" colSpan={8}>
                  暂无 LLM 或外部工具调用记录。
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function ObservabilityPage({ displayTaskId, onNavigate, taskId }: ObservabilityPageProps) {
  const [data, setData] = useState<ObservabilityResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!taskId) return;
    let cancelled = false;
    let timer: number | undefined;

    async function load() {
      try {
        setLoading(true);
        const next = await analysisApi.getObservability(taskId as string);
        if (!cancelled) {
          setData(next);
          setError("");
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "加载可观测数据失败");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    timer = window.setInterval(load, 3000);
    return () => {
      cancelled = true;
      if (timer) window.clearInterval(timer);
    };
  }, [taskId]);

  const totals = data?.totals || {};
  const agents = useMemo(() => data?.agent_trace || [], [data?.agent_trace]);
  const llm = data?.llm_usage || [];
  const mcp = data?.mcp_usage || [];
  const langsmithUrl = data?.langsmith?.trace_url || "";

  if (!taskId) return <EmptyState onNavigate={onNavigate} />;

  return (
    <div className="space-y-6 pb-12">
      <section className="rounded-xl border border-slate-700/80 bg-slate-950/60 p-6">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.35em] text-cyan-300">Agent Observability</p>
            <h1 className="mt-2 text-3xl font-black text-slate-50">运行观测</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">
              这里展示本地 trace、MCP 调用、LLM token 和 LangSmith 跳转。规则节点会记录耗时，真正调用模型的节点才计入 token。
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full border border-cyan-300/30 bg-cyan-400/10 px-3 py-1.5 text-xs font-semibold text-cyan-100">
              当前任务：{displayTaskId || data?.task_id || taskId}
            </span>
            <StatusBadge status={data?.status || (loading ? "loading" : "unknown")} />
            {langsmithUrl ? (
              <a
                className="rounded-lg bg-cyan-300 px-4 py-2 text-sm font-bold text-slate-950 transition hover:bg-cyan-200"
                href={langsmithUrl}
                rel="noreferrer"
                target="_blank"
              >
                查看 LangSmith Trace
              </a>
            ) : (
              <span className="rounded-lg border border-slate-700 bg-slate-900 px-4 py-2 text-sm text-slate-400">
                本地 trace 已记录，LangSmith 未开启或暂无 URL
              </span>
            )}
          </div>
        </div>

        {error ? (
          <div className="mt-5 rounded-lg border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
            {error}
          </div>
        ) : null}

        <div className="mt-6 grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          <MetricCard label="总耗时" value={formatMs(totals.total_duration_ms)} hint="来自本地 Agent trace" />
          <MetricCard label="Prompt Tokens" value={number(totals.prompt_tokens).toLocaleString()} />
          <MetricCard label="Completion Tokens" value={number(totals.completion_tokens).toLocaleString()} />
          <MetricCard label="Total Tokens" value={number(totals.total_tokens).toLocaleString()} />
          <MetricCard label="估算费用" value={formatMoney(totals.estimated_cost_usd)} hint="可通过环境变量调整单价" />
        </div>
      </section>

      <AgentTimeline agents={agents} />
      <TokenByAgent rows={data?.per_agent || []} />
      <CallsTable llm={llm} mcp={mcp} />
    </div>
  );
}
