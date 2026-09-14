import { useEffect, useMemo, useState } from "react";
import { analysisApi } from "../api/analysisApi";
import { EmptyState } from "../components/common/EmptyState";
import { LoadingState } from "../components/common/LoadingState";
import { StatusBadge } from "../components/common/StatusBadge";
import type {
  AgentContribution,
  ExternalProductCandidate,
  FeatureNode,
  FinalReport,
  HardwareSpec,
  HumanFeedbackRecord,
  OfficialSpecRecord,
  ProductIdentity,
  QualityResult,
  RiskFlag,
  SearchMcpResult,
} from "../types/analysis";

type ReportPageProps = {
  taskId?: string;
  displayTaskId?: string;
  onNavigate: (key: string) => void;
};

type ReportResponse = {
  final_report?: FinalReport;
  quality_result?: QualityResult;
  quality_status?: string;
  degraded_report?: boolean;
  needs_human_review?: boolean;
  risk_flags?: RiskFlag[];
  search_mcp_results?: SearchMcpResult[];
  external_product_candidates?: ExternalProductCandidate[];
  official_spec_records?: OfficialSpecRecord[];
  human_feedback?: HumanFeedbackRecord[];
};

type Tone = "neutral" | "success" | "warning" | "danger" | "info";

const FEATURE_LABELS: Record<string, string> = {
  performance: "性能参数",
  shape_and_weight: "模具与轻量化",
  wireless_and_battery: "无线与续航",
  click_system: "点击系统",
  software_ecosystem: "驱动生态",
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

function asStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => asString(item)).filter(Boolean);
}

function normalize(value: unknown): string {
  return asString(value).toLowerCase();
}

function extractReport(response: ReportResponse | FinalReport | null): FinalReport {
  if (!response) return {};
  const record = asRecord(response);
  return asRecord(record.final_report ?? response) as FinalReport;
}

function qualityFrom(response: ReportResponse | FinalReport | null, report: FinalReport) {
  const record = asRecord(response);
  return asRecord(record.quality_result ?? report.quality_result);
}

function qualityTone(status: string): Tone {
  const value = normalize(status);
  if (value === "approved") return "success";
  if (value === "approved_with_limitations" || value === "partial_report") return "warning";
  if (value.includes("reject") || value.includes("fail")) return "danger";
  return "neutral";
}

function statusTone(status?: string): Tone {
  const value = normalize(status);
  if (["available", "complete", "success", "official"].includes(value)) return "success";
  if (["partial", "reference_only", "approved_with_limitations"].includes(value)) return "warning";
  if (["failed", "rejected"].includes(value)) return "danger";
  if (value.includes("pending") || value.includes("not_connected") || value === "insufficient_evidence") {
    return "warning";
  }
  return "neutral";
}

function riskTypeLabel(value: unknown): string {
  const type = normalize(value);
  const labels: Record<string, string> = {
    data_credibility: "数据可信度风险",
    data_timeliness: "实时性待补齐",
    evidence_gap: "数据缺口",
    compliance: "合规风险",
    faithfulness: "事实支撑风险",
  };
  return labels[type] ?? asString(value, "风险提示");
}

function formatValue(value: unknown, unit = "", fallback = "待补齐") {
  if (value === null || value === undefined || value === "" || (Array.isArray(value) && !value.length)) {
    return fallback;
  }
  if (Array.isArray(value)) return value.join(" / ");
  return `${value}${unit}`;
}

function pendingData(report: FinalReport, quality: Record<string, unknown>) {
  const fromReport = asRecords(report.pending_data);
  if (fromReport.length) return fromReport;
  const links = asRecord(report.evidence_links);
  const fromLinks = asRecords(links.pending_data);
  if (fromLinks.length) return fromLinks;
  return asRecords(quality.pending_data);
}

function compactPending(item: Record<string, unknown>) {
  const agent = asString(item.agent);
  const status = asString(item.status, "pending");
  const fields = asStringList(item.fields);
  const note = asString(item.note);
  const label = agent || asString(item.dimension) || asString(item.field) || "待补充数据";
  if (fields.length) return `${label}：${fields.slice(0, 5).join("、")}（${status}）`;
  return `${label}（${status}${note ? `，${note}` : ""}）`;
}

function Section({
  children,
  title,
  subtitle,
}: {
  children: React.ReactNode;
  title: string;
  subtitle?: string;
}) {
  return (
    <section className="rounded-lg border border-slate-800 bg-slate-950/72 p-5">
      <div className="mb-4">
        <h3 className="text-lg font-semibold text-white">{title}</h3>
        {subtitle ? <p className="mt-1 text-sm leading-6 text-slate-400">{subtitle}</p> : null}
      </div>
      {children}
    </section>
  );
}

function Metric({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="rounded-md border border-slate-800 bg-slate-900/45 p-4">
      <p className="text-xs uppercase tracking-[0.16em] text-slate-500">{label}</p>
      <p className="mt-2 text-xl font-semibold text-slate-100">{value}</p>
      {note ? <p className="mt-1 text-xs leading-5 text-slate-500">{note}</p> : null}
    </div>
  );
}

function IdTags({ ids, tone = "neutral" }: { ids: string[]; tone?: Tone }) {
  if (!ids.length) return <span className="text-sm text-slate-500">暂无</span>;
  return (
    <div className="flex flex-wrap gap-2">
      {ids.slice(0, 16).map((id) => (
        <StatusBadge key={id} label={id} tone={tone} />
      ))}
    </div>
  );
}

type ScenarioTone = "success" | "info" | "warning" | "neutral";

function scenarioStatusMeta(status: string): { label: string; tone: ScenarioTone } {
  if (status === "recommended") return { label: "可推荐", tone: "success" };
  if (status === "tie") return { label: "均可 / 持平", tone: "info" };
  if (status === "data_missing") return { label: "数据缺失", tone: "warning" };
  return { label: "等待测评数据", tone: "warning" }; // pending_review
}

const SCENARIO_CONF_LABEL: Record<string, string> = {
  high: "高可信",
  medium: "中可信",
  low: "低可信",
  pending: "待采集",
};

function scenarioConfTone(conf: string): ScenarioTone {
  if (conf === "high") return "success";
  if (conf === "medium") return "info";
  if (conf === "low") return "warning";
  return "neutral";
}

function feedbackStatusLabel(value: unknown): string {
  const key = normalize(value);
  if (key === "applied_to_report") return "已并入报告";
  if (key === "pending_verification") return "待校验";
  if (key === "verified") return "已校验";
  return asString(value, "待校验");
}

function Recommendation({ report }: { report: FinalReport }) {
  const raw = report.scenario_recommendations;
  const scenarios = Array.isArray(raw)
    ? raw.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object")
    : [];

  if (!scenarios.length) {
    return (
      <Section
        subtitle="按购买诉求分场景给结论，而不是只给一个赢家。"
        title="按场景推荐"
      >
        <div className="rounded-lg border border-slate-800 bg-slate-900/45 p-5 text-sm leading-6 text-slate-400">
          暂无场景推荐：需要两款已解析产品和硬件 / 价格事实，工作流完成后这里会按场景给出建议。
        </div>
      </Section>
    );
  }

  return (
    <Section
      subtitle="不给单一赢家：按购买诉求分场景。硬件 / 价格基于已验证事实直接给结论；体验类（FPS、手感、长期可靠性）等待真实测评数据。"
      title="按场景推荐"
    >
      <div className="grid gap-3 lg:grid-cols-2">
        {scenarios.map((scenario, index) => {
          const status = asString(scenario.status);
          const meta = scenarioStatusMeta(status);
          const recommended = asString(scenario.recommended_product);
          const conf = asString(scenario.confidence);
          const pending = status === "pending_review";
          return (
            <article
              className={`rounded-lg border p-4 ${
                pending ? "border-dashed border-amber-400/30 bg-amber-400/5" : "border-slate-800 bg-slate-900/45"
              }`}
              key={asString(scenario.key) || index}
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h4 className="text-base font-semibold text-white">{asString(scenario.scenario) || `场景 ${index + 1}`}</h4>
                <StatusBadge label={meta.label} tone={meta.tone} />
              </div>
              {recommended ? (
                <p className="mt-2 text-lg font-semibold text-cyan-200">推荐：{recommended}</p>
              ) : null}
              <p className="mt-1 text-sm leading-6 text-slate-200">{asString(scenario.verdict)}</p>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <StatusBadge label={SCENARIO_CONF_LABEL[conf] || conf || "—"} tone={scenarioConfTone(conf)} />
                <span className="text-xs leading-5 text-slate-500">{asString(scenario.reason)}</span>
              </div>
            </article>
          );
        })}
      </div>
    </Section>
  );
}

function ProductIdentitySection({ items }: { items: ProductIdentity[] }) {
  if (!items.length) return null;
  return (
    <Section
      subtitle="这里对应 ProductResolver 与本地事实库的实体消歧结果。"
      title="产品识别与变体"
    >
      <div className="grid gap-3 lg:grid-cols-2">
        {items.map((item, index) => (
          <article
            className="rounded-lg border border-slate-800 bg-slate-900/45 p-4"
            key={`${item.official_model || item.model || index}`}
          >
            <div className="flex flex-wrap items-center gap-2">
              <h4 className="text-base font-semibold text-white">
                {item.brand} {item.official_model || item.model || "待识别产品"}
              </h4>
              <StatusBadge label={item.data_status || "pending"} tone={statusTone(item.data_status)} />
              {item.alias_confidence ? (
                <StatusBadge label={`别名 ${item.alias_confidence}`} tone={statusTone(item.alias_confidence)} />
              ) : null}
            </div>
            <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-slate-500">系列 / 变体</dt>
                <dd className="mt-1 text-slate-200">
                  {item.family || "待补齐"} / {item.variant_name || "标准或待识别"}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">变体类型</dt>
                <dd className="mt-1 text-slate-200">{item.variant_type || "待补齐"}</dd>
              </div>
              <div>
                <dt className="text-slate-500">点击系统</dt>
                <dd className="mt-1 text-slate-200">{item.click_system || "待补齐"}</dd>
              </div>
            </dl>
            <div className="mt-4 flex flex-wrap gap-2">
              {(item.community_aliases || []).slice(0, 6).map((alias) => (
                <StatusBadge key={alias} label={alias} tone="neutral" />
              ))}
            </div>
          </article>
        ))}
      </div>
    </Section>
  );
}

function HardwareSpecsSection({ specs }: { specs: HardwareSpec[] }) {
  if (!specs.length) {
    return (
      <Section title="硬件规格" subtitle="本地事实库未命中时，这里会等待官网规格 MCP 补齐。">
        <div className="rounded-md border border-dashed border-amber-300/35 bg-amber-300/10 p-4 text-sm leading-6 text-amber-100">
          当前没有可展示的本地硬件事实。后续接入搜索/官网 MCP 后，将先识别官方型号，再补齐硬件参数。
        </div>
      </Section>
    );
  }

  const rows = [
    ["重量", (item: HardwareSpec) => formatValue(item.weight_g, "g")],
    ["传感器", (item: HardwareSpec) => formatValue(item.sensor)],
    ["最高 DPI", (item: HardwareSpec) => formatValue(item.dpi_max)],
    ["回报率", (item: HardwareSpec) => formatValue(item.polling_rate_hz, "Hz")],
    ["连接方式", (item: HardwareSpec) => formatValue(item.connection)],
    ["续航", (item: HardwareSpec) => formatValue(item.battery_hours, "h")],
    ["微动", (item: HardwareSpec) => formatValue(item.switch_type)],
    ["点击系统", (item: HardwareSpec) => formatValue(item.click_system)],
    ["驱动 / 软件", (item: HardwareSpec) => formatValue(item.software)],
    ["板载内存", (item: HardwareSpec) => (item.onboard_memory === undefined || item.onboard_memory === null ? "待补齐" : item.onboard_memory ? "支持" : "不支持")],
  ];

  return (
    <Section
      subtitle="只展示相对稳定的硬件事实。手感、握法、适合人群和实时价格不在这里伪造结论。"
      title="硬件规格"
    >
      <div className="overflow-hidden rounded-lg border border-slate-800">
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead className="bg-slate-900/80 text-xs uppercase tracking-[0.14em] text-slate-500">
            <tr>
              <th className="w-44 px-4 py-3">字段</th>
              {specs.map((spec, index) => (
                <th className="px-4 py-3" key={`${spec.product_id || spec.model || index}`}>
                  {spec.brand} {spec.model}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800 bg-slate-950/55">
            {rows.map(([label, getter]) => (
              <tr key={label as string}>
                <td className="px-4 py-3 text-slate-500">{label as string}</td>
                {specs.map((spec, index) => (
                  <td className="px-4 py-3 font-medium text-slate-200" key={`${label}-${spec.product_id || index}`}>
                    {(getter as (item: HardwareSpec) => string)(spec)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  );
}

function FeatureTreeSection({ report }: { report: FinalReport }) {
  const tree = asRecord(report.feature_tree);
  const entries = Object.entries(FEATURE_LABELS)
    .map(([key, label]) => ({ key, label, node: asRecord(tree[key]) as FeatureNode }))
    .filter((item) => Object.keys(item.node).length);
  if (!entries.length) return null;

  return (
    <Section
      subtitle="专业电竞鼠标 schema 把报告拆成固定能力树，方便评委看到字段完整性和 pending 状态。"
      title="电竞鼠标能力树"
    >
      <div className="grid gap-3 lg:grid-cols-2">
        {entries.map(({ key, label, node }) => (
          <article className="rounded-lg border border-slate-800 bg-slate-900/45 p-4" key={key}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h4 className="font-semibold text-white">{node.name || label}</h4>
              <StatusBadge label={node.status || "pending"} tone={statusTone(node.status)} />
            </div>
            <p className="mt-2 text-sm leading-6 text-slate-400">
              {node.summary || "等待对应 Agent 或 MCP 补齐后形成摘要。"}
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {(node.fields || []).map((field) => (
                <span className="rounded-full border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-300" key={field}>
                  {field}
                </span>
              ))}
            </div>
          </article>
        ))}
      </div>
    </Section>
  );
}

function ScoreFlowSection({ report }: { report: FinalReport }) {
  const flow = asRecord(report.score_flow);
  const baseline = asRecord(flow.baseline_score);
  const finalScore = asRecord(flow.final_score);
  const adjustments = asRecords(flow.agent_adjustments);
  if (!Object.keys(flow).length) return null;

  return (
    <Section
      subtitle="这里展示报告是如何从基础硬件事实进入 Agent 质量门控和最终建议的。"
      title="基础事实 -> Agent 修正 -> 最终评分"
    >
      <div className="grid gap-3 md:grid-cols-3">
        <Metric
          label={asString(baseline.label, "基础硬件事实")}
          note={asString(baseline.note, "来自本地 JSON 或官网规格 MCP。")}
          value={asString(baseline.value ?? baseline.score, "待计算")}
        />
        <Metric
          label="Agent 修正"
          note="评价、价格、风险和证据缺口会影响最终可信度。"
          value={`${adjustments.length} 项`}
        />
        <Metric
          label={asString(finalScore.label, "最终综合结果")}
          note={asString(finalScore.note, "由 ReportAgent 汇总生成。")}
          value={asString(finalScore.value ?? finalScore.score, "待生成")}
        />
      </div>
      {adjustments.length ? (
        <div className="mt-4 space-y-2">
          {adjustments.map((item, index) => (
            <div className="rounded-md border border-slate-800 bg-slate-900/50 px-3 py-2 text-sm text-slate-300" key={index}>
              <span className="font-semibold text-slate-100">{asString(item.agent, `Agent ${index + 1}`)}</span>
              <span className="text-slate-500">：{asString(item.reason || item.summary, "已参与最终修正。")}</span>
            </div>
          ))}
        </div>
      ) : null}
    </Section>
  );
}

function PendingAndEvidence({ report, quality }: { report: FinalReport; quality: Record<string, unknown> }) {
  const pending = pendingData(report, quality);
  const evidenceLinks = asRecord(report.evidence_links);
  const usedClaimIds = asStringList(report.used_claim_ids).length
    ? asStringList(report.used_claim_ids)
    : asStringList(evidenceLinks.used_claim_ids);
  const usedEvidenceIds = asStringList(report.used_evidence_ids).length
    ? asStringList(report.used_evidence_ids)
    : asStringList(evidenceLinks.used_evidence_ids);
  const unsupported = asStringList(evidenceLinks.unsupported_claim_ids);

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
      <Section
        subtitle="pending 会降低报告可信度，但不会被当作失败，也不会伪造成已采集。"
        title="待 MCP 补齐的数据"
      >
        {pending.length ? (
          <ul className="space-y-2 text-sm leading-6 text-slate-300">
            {pending.map((item, index) => (
              <li className="flex gap-2" key={`${compactPending(item)}-${index}`}>
                <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-300" />
                <span>{compactPending(item)}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-slate-400">暂无 pending 数据。</p>
        )}
      </Section>

      <Section title="证据引用">
        <div className="space-y-4">
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
              Used claims
            </p>
            <IdTags ids={usedClaimIds} />
          </div>
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
              Used evidence
            </p>
            <IdTags ids={usedEvidenceIds} tone="info" />
          </div>
          {unsupported.length ? (
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                Unsupported claims
              </p>
              <IdTags ids={unsupported} tone="warning" />
            </div>
          ) : null}
        </div>
      </Section>
    </div>
  );
}

function HumanFeedbackSection({ report }: { report: FinalReport }) {
  const feedback = asRecords(report.human_feedback) as HumanFeedbackRecord[];
  const note = asString(report.human_feedback_note);
  if (!feedback.length) return null;
  return (
    <Section
      subtitle={note || "人工输入作为 human_feedback evidence 进入 VerificationAgent，不会绕过证据校验直接覆盖报告。"}
      title="人工修正记录"
    >
      <div className="grid gap-3 lg:grid-cols-2">
        {feedback.map((item, index) => (
          <article className="rounded-lg border border-violet-400/25 bg-violet-400/10 p-4" key={asString(item.feedback_id) || index}>
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge label={asString(item.feedback_id, `HF${index + 1}`)} tone="info" />
              <StatusBadge label={feedbackStatusLabel(item.status)} tone={normalize(item.status) === "applied_to_report" ? "success" : "warning"} />
              <StatusBadge label={asString(item.dimension, "human_feedback")} tone="neutral" />
            </div>
            <p className="mt-3 text-sm leading-6 text-slate-200">{asString(item.message)}</p>
            <p className="mt-2 text-xs text-slate-500">{asString(item.product, "未指定产品")}</p>
          </article>
        ))}
      </div>
    </Section>
  );
}

function PersonaAndPrice({ report }: { report: FinalReport }) {
  const persona = report.user_persona;
  const pricing = report.pricing_model;
  if (!persona && !pricing) return null;

  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Section title="用户体验适配" subtitle="握法、手型、游戏适配必须等待真实评价/测评证据。">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge label={persona?.status || "pending"} tone={statusTone(persona?.status)} />
          <StatusBadge label={persona?.evidence_status || "review_intel_pending"} tone="warning" />
        </div>
        <p className="mt-3 text-sm leading-6 text-slate-400">
          {persona?.limitation || "当前不输出握法、手型或适合游戏结论，等待 ReviewIntel MCP 补齐。"}
        </p>
      </Section>

      <Section title="价格与性价比" subtitle="价格随时间变化，不使用本地写死价格做最终判断。">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge label={pricing?.status || "pending"} tone={statusTone(pricing?.status)} />
          <StatusBadge label={pricing?.realtime_price_status || "mcp_not_connected"} tone="warning" />
        </div>
        <p className="mt-3 text-sm leading-6 text-slate-400">
          {pricing?.note || "实时价格、折扣和区域可买性等待 Price MCP 补齐。"}
        </p>
      </Section>
    </div>
  );
}

function AgentContributions({ items = [] }: { items?: AgentContribution[] }) {
  if (!items.length) return null;
  return (
    <Section subtitle="每个 Agent 对最终报告的贡献，来自 final_report.agent_contributions。" title="Agent 贡献">
      <div className="grid gap-3 lg:grid-cols-2">
        {items.map((item) => (
          <article className="rounded-lg border border-slate-800 bg-slate-900/45 p-4" key={item.agent}>
            <div className="flex flex-wrap items-center gap-2">
              <h4 className="font-semibold text-white">{item.agent}</h4>
              <StatusBadge label={item.status || "applied"} tone={statusTone(item.status)} />
            </div>
            <p className="mt-2 text-sm font-medium text-slate-300">{item.role}</p>
            <p className="mt-2 text-sm leading-6 text-slate-400">{item.summary}</p>
          </article>
        ))}
      </div>
    </Section>
  );
}

function RisksSection({ risks }: { risks: Record<string, unknown>[] }) {
  return (
    <Section subtitle="风险会直接影响 QualityAgent 的报告可信度。" title="风险披露">
      {risks.length ? (
        <div className="grid gap-3 lg:grid-cols-2">
          {risks.map((risk, index) => {
            const severity = normalize(risk.severity);
            const tone: Tone =
              severity === "high" ? "danger" : severity === "medium" ? "warning" : "success";
            return (
              <article className="rounded-lg border border-slate-800 bg-slate-900/45 p-4" key={`${asString(risk.risk_type)}-${index}`}>
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge label={asString(risk.severity, "unknown")} tone={tone} />
                  <span className="font-semibold text-white">{riskTypeLabel(risk.risk_type)}</span>
                </div>
                <p className="mt-3 text-sm leading-6 text-slate-300">
                  {asString(risk.description, "暂无风险说明")}
                </p>
              </article>
            );
          })}
        </div>
      ) : (
        <p className="text-sm text-slate-400">暂无风险标记。</p>
      )}
    </Section>
  );
}

export function ReportPage({ taskId, displayTaskId, onNavigate }: ReportPageProps) {
  const [response, setResponse] = useState<ReportResponse | FinalReport | null>(null);
  const [risks, setRisks] = useState<Record<string, unknown>[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!taskId) return;
    const activeTaskId: string = taskId;
    let cancelled = false;
    async function load() {
      setIsLoading(true);
      try {
        const [reportResult, risksResult] = await Promise.all([
          analysisApi.getReport(activeTaskId),
          analysisApi.getRisks(activeTaskId).catch(() => ({ risk_flags: [] })),
        ]);
        if (cancelled) return;
        setResponse(reportResult as ReportResponse);
        setRisks(asRecords(risksResult.risk_flags));
        setError(null);
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "加载报告失败");
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [taskId]);

  const report = useMemo(() => extractReport(response), [response]);
  const quality = qualityFrom(response, report);
  const qualityStatus =
    asString(quality.status) ||
    asString(asRecord(response).quality_status) ||
    asString(report.quality_status) ||
    "pending";
  const qualityScore = asNumber(quality.quality_score) ?? asNumber(quality.score);
  const pending = pendingData(report, quality);
  const reportRisks = risks.length ? risks : asRecords(report.risk_flags ?? report.risk_disclosure);
  const hasReport = Object.keys(report).length > 0;

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
          description="最终报告需要先启动一次 Agent 分析任务。"
          title="暂无最终报告"
        />
      </section>
    );
  }

  return (
    <section className="mx-auto max-w-7xl">
      <header className="mb-5 flex flex-col gap-4 rounded-lg border border-slate-800 bg-slate-950/75 p-5 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-cyan-300">
            Gaming Mouse Final Report
          </p>
          <h2 className="mt-2 text-2xl font-semibold text-white">
            电竞鼠标专业竞品报告
          </h2>
          <p className="mt-2 max-w-3xl break-all text-sm leading-6 text-slate-400">
            当前任务：{displayTaskId || taskId}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <StatusBadge label={report.schema_name || "gaming_mouse_competitive_report"} tone="info" />
          <StatusBadge label={qualityStatus} tone={qualityTone(qualityStatus)} />
          <StatusBadge label={`报告可信度 ${qualityScore ?? "待计算"}`} tone="info" />
          <button
            className="rounded-md border border-slate-700 bg-slate-900/80 px-3 py-2 text-sm font-medium text-slate-200 transition hover:border-cyan-300/50 hover:text-cyan-100"
            onClick={() => onNavigate("workflow")}
            type="button"
          >
            返回工作流
          </button>
        </div>
      </header>

      {isLoading ? <LoadingState label="正在加载最终报告..." /> : null}

      {error ? (
        <div className="mb-5 rounded-md border border-rose-500/35 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
          {error}
        </div>
      ) : null}

      {!isLoading && !error && !hasReport ? (
        <EmptyState
          action={
            <button
              className="rounded-md bg-cyan-300 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-200"
              onClick={() => onNavigate("workflow")}
              type="button"
            >
              查看 Agent 工作流
            </button>
          }
          description="ReportAgent 生成 final_report 后，这里会展示专业 schema 报告。"
          title="报告尚未生成"
        />
      ) : null}

      {hasReport ? (
        <div className="space-y-5">
          <div className="grid gap-3 md:grid-cols-4">
            <Metric label="报告状态" value={qualityStatus} />
            <Metric
              label="报告可信度"
              note="不是产品综合评分"
              value={qualityScore === undefined ? "待计算" : qualityScore.toFixed(1)}
            />
            <Metric label="pending 数据" value={`${pending.length}`} />
            <Metric label="风险数量" value={`${reportRisks.length}`} />
          </div>

          <Recommendation report={report} />
          <ProductIdentitySection items={report.product_identification || []} />
          <HardwareSpecsSection specs={report.hardware_specs || []} />
          <FeatureTreeSection report={report} />
          <PersonaAndPrice report={report} />
          <ScoreFlowSection report={report} />
          <PendingAndEvidence report={report} quality={quality} />
          <HumanFeedbackSection report={report} />
          <AgentContributions items={report.agent_contributions} />
          <RisksSection risks={reportRisks} />
        </div>
      ) : null}
    </section>
  );
}
