// 用户可见文案的集中映射。内部数据值保持不变，仅在 UI 层做中文化与解释。

export const sourceTypeLabels: Record<string, string> = {
  official: "官方资料",
  review: "评测内容",
  ecommerce: "电商信息",
  social: "用户口碑",
  other: "其他来源",
};

export function getSourceTypeLabel(value?: string): string {
  if (!value) {
    return "其他来源";
  }

  return sourceTypeLabels[value.toLowerCase()] ?? value;
}

export const sourceTypeExplains: Record<string, string> = {
  official: "来自品牌官网、官方规格或官方发布的资料。",
  review: "来自专业媒体或第三方评测的内容。",
  ecommerce: "来自电商平台的商品信息与销售数据。",
  social: "来自社区、论坛与社交平台的用户口碑。",
  other: "未明确归类的公开信息来源。",
};

export function getSourceTypeExplain(value?: string): string {
  if (!value) {
    return sourceTypeExplains.other;
  }

  return sourceTypeExplains[value.toLowerCase()] ?? "公开信息来源。";
}

export const credibilityLabels: Record<string, string> = {
  high: "高可信",
  medium: "中可信",
  low: "低可信",
};

export function getCredibilityLabel(value?: string): string {
  if (!value) {
    return "未知";
  }

  return credibilityLabels[value.toLowerCase()] ?? value;
}

export const credibilityExplains: Record<string, string> = {
  high: "高可信证据，适合作为核心结论依据。",
  medium: "中可信证据，需要结合其他证据判断。",
  low: "低可信证据，仅供参考。",
};

export function getCredibilityExplain(value?: string): string {
  if (!value) {
    return "可信度未标注的证据。";
  }

  return credibilityExplains[value.toLowerCase()] ?? "可信度未标注的证据。";
}

// 质量审查覆盖缺口字段的中文前缀。
export const coverageFieldLabels: Record<string, string> = {
  missing_dimensions: "缺失维度",
  missing_platforms: "缺失品牌",
  missing_evidence: "缺失证据",
  coverage_gaps: "覆盖缺口",
  high_risk_flags: "高风险标记",
  risk_flags: "风险标记",
};

export function getCoverageFieldLabel(field: string): string {
  return coverageFieldLabels[field] ?? field;
}

export type AgentMeta = {
  /** Agent 的中文作用说明。 */
  role: string;
};

// 各 Agent 的作用说明，用于节点悬停与详情展示。
export const agentMeta: Record<string, AgentMeta> = {
  ResearchAgent: { role: "规划本次竞品分析需要采集和补齐的数据" },
  CollectorAgent: { role: "完成产品识别、实体消歧、本地事实读取与后续 MCP 采集调度" },
  EvidenceAgent: { role: "把本地事实和外部采集结果转换成可追溯 evidence" },
  AnalysisAgent: { role: "只分析有证据支撑的硬件事实差异和风险" },
  VerificationAgent: { role: "忠实性校验，剔除无法被证据支撑的结论（防幻觉）" },
  QualityAgent: { role: "质量门控，决定通过、有限通过或生成 partial_report" },
  ReportAgent: { role: "生成专业电竞鼠标 final_report" },
  HumanReviewRequired: { role: "质量门控未通过时进入人工复核" },
};

export function getAgentRole(agentName: string): string {
  return agentMeta[agentName]?.role ?? "参与多 Agent 协作流程";
}

// 质量门控检查项的中文说明，用于检查项展示。
export const checkedItemLabels: Record<string, string> = {
  all_claims_have_evidence: "结论均有证据引用",
  all_evidence_ids_valid: "引用的证据 ID 均有效",
  all_claims_faithful: "结论均能被证据支撑（防幻觉）",
  all_matrix_claims_faithful: "矩阵分析均能被证据支撑（防幻觉）",
  all_competitors_covered: "覆盖全部竞品",
  all_dimensions_covered: "覆盖全部维度",
  product_entities_resolved: "产品实体已识别",
  local_or_pending_facts_disclosed: "本地事实或待补齐状态已披露",
  evidence_available_or_pending_disclosed: "证据可用或 pending 已披露",
  final_report_schema_valid: "最终报告符合电竞鼠标专业 schema",
  no_high_severity_risk: "无高危风险",
};

export function getCheckedItemLabel(name: string): string {
  return checkedItemLabels[name] ?? name;
}

// 风险类型的中文说明。
export const riskTypeLabels: Record<string, string> = {
  data_credibility: "数据可信度",
  data_timeliness: "数据时效性",
  evidence_gap: "证据缺口",
  compliance: "合规风险",
  faithfulness: "幻觉风险",
};

export function getRiskTypeLabel(value?: string): string {
  if (!value) {
    return "风险";
  }

  return riskTypeLabels[value] ?? value;
}
