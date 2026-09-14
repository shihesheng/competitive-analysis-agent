export type Industry = {
  industry_key?: string;
  key?: string;
  name: string;
  competitors: string[];
  dimensions: string[];
  description?: string;
  representative_products?: Record<string, string[]>;
  schema_id?: string;
  schema_model?: string;
  schema_fields?: string[];
};

export type SelectedProductRef = {
  id: string;
  model?: string;
  brand?: string;
  category?: string;
};

export type StartAnalysisRequest = {
  target_platform: string;
  competitors: string[];
  analysis_scene: string;
  target_user: string;
  time_range: string;
  focus_dimensions: string[];
  industry_key: string;
  // 产品对比页带入的两个产品；普通新建分析入口可省略。
  selected_products?: SelectedProductRef[];
};

export type StartAnalysisResponse = {
  task_id: string;
};

export type AnalysisStatus = {
  task_id?: string;
  status?: string;
  progress?: number;
  current_agent?: string;
  quality_status?: string;
  degraded_report?: boolean;
  needs_human_review?: boolean;
  message?: string;
  error?: string;
};

export type EvidenceItem = {
  evidence_id: string;
  platform: string;
  claim: string;
  source_type: string;
  source_title: string;
  source_url: string;
  publish_time?: string;
  collected_time?: string;
  credibility: "high" | "medium" | "low" | string;
  related_dimension: string;
  raw_content: string;
  confidence_score?: number;
};

export type Claim = {
  claim_id: string;
  content: string;
  dimension: string;
  related_platforms: string[];
  evidence_ids: string[];
  confidence_score: number;
  generated_by: string;
};

export type AgentTrace = {
  step_id?: number;
  agent_name: string;
  status: string;
  input_summary?: string;
  output_summary?: string;
  evidence_added?: number;
  pending_fields?: string[];
  substeps?: Array<Record<string, unknown>>;
  duration_ms?: number;
  context_selected_evidence_count?: number;
  context_trimmed_evidence_count?: number;
  review_ticket_id?: string;
  error?: string | null;
};

export type MatrixIssue = {
  matrix?: string;
  platform?: string;
  dimension?: string;
  missing_numbers?: string[];
};

export type ContextSummary = {
  agent_name?: string;
  total_evidence_count?: number;
  selected_evidence_count?: number;
  trimmed_evidence_count?: number;
  selected_evidence_ids?: string[];
  trimmed_evidence_ids?: string[];
  dimension_counts?: Record<string, number>;
  limits?: {
    max_items?: number;
    max_per_dimension?: number;
    max_content_chars?: number;
  };
};

export type ErrorLogItem = {
  error_id?: string;
  agent_name?: string;
  error_type?: string;
  message?: string;
  recover_action?: string;
  retry_count?: number;
  created_at?: string;
};

export type ReviewTicket = {
  ticket_id?: string;
  status?: "open" | "resolved" | string;
  reason?: string;
  target_agent?: string | null;
  failed_checks?: string[];
  required_actions?: string[];
  unsupported_claim_ids?: string[];
  matrix_issues?: MatrixIssue[];
  missing_dimensions?: string[];
  missing_platforms?: string[];
  risk_flags?: Array<Record<string, unknown>>;
  suggested_next_steps?: string[];
  created_at?: string;
};

export type QualityResult = {
  approved?: boolean;
  score?: number;
  status?: string;
  report_status?: string;
  quality_score?: number;
  score_type?: string;
  score_meaning?: string;
  reason?: string;
  reject_to?: string | null;
  target_agent?: string | null;
  reject_reason?: string | null;
  missing_dimensions?: string[];
  missing_platforms?: string[];
  matrix_issues?: MatrixIssue[];
  matrix_issues_disclosed?: MatrixIssue[];
  required_actions?: string[];
  required_fix?: string;
  checked_items?: Record<string, boolean>;
  passed_checks?: string[];
  failed_checks?: string[];
  approved_with_limitations?: boolean;
  partial_report?: boolean;
  auto_degraded?: boolean;
  limitations?: string[];
  pending_data?: Array<Record<string, unknown>>;
  evidence_gap_note?: string;
  degradation_reason?: string;
  excluded_claim_ids?: string[];
};

export type Metrics = {
  evidence_count?: number;
  claim_count?: number;
  citation_rate?: number;
  coverage_rate?: number;
  high_credibility_ratio?: number;
  low_credibility_ratio?: number;
  faithfulness_rate?: number;
  unsupported_claim_count?: number;
  weak_claim_count?: number;
  matrix_issue_count?: number;
  context_trimmed_evidence_count?: number;
  error_count?: number;
  has_review_ticket?: boolean;
  quality_score?: number;
  iteration_count?: number;
};

export type FaithfulnessClaimResult = {
  claim_id: string;
  supported: boolean;
  weak?: boolean;
  grounding_score?: number;
  reason?: string;
  missing_numbers?: string[];
};

export type FaithfulnessReport = {
  checked_claim_count?: number;
  supported_claim_count?: number;
  unsupported_claim_count?: number;
  weak_claim_count?: number;
  faithfulness_rate?: number;
  unsupported_claim_ids?: string[];
  weak_claim_ids?: string[];
  claim_results?: FaithfulnessClaimResult[];
  matrix_issues?: MatrixIssue[];
};

export type RiskFlag = {
  risk_type: string;
  description: string;
  severity: "low" | "medium" | "high" | string;
  related_platforms?: string[];
  related_dimensions?: string[];
};

export type ArtifactsSummary = {
  task_id: string;
  raw_research_count?: number;
  evidence_count?: number;
  claim_count?: number;
  risk_count?: number;
  trace_count?: number;
  context_agent_count?: number;
  context_trimmed_evidence_count?: number;
  error_count?: number;
  has_review_ticket?: boolean;
  has_final_report?: boolean;
};

export type ObservabilityAgentTrace = {
  order: number;
  agent: string;
  status: string;
  duration_ms?: number;
  calls_mcp?: boolean;
  calls_llm?: boolean;
  mcp_call_count?: number;
  llm_call_count?: number;
  summary?: string;
};

export type LlmUsageRecord = {
  agent?: string;
  tool?: string;
  model?: string;
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  estimated_cost_usd?: number;
  latency_ms?: number;
  status?: string;
  error?: string;
  trace_url?: string;
  usage_source?: string;
  called_at?: string;
  metadata?: Record<string, unknown>;
};

export type McpUsageRecord = {
  agent?: string;
  tool?: string;
  provider?: string;
  status?: string;
  latency_ms?: number;
  query?: string;
  result_count?: number;
  uses_llm?: boolean;
  external_call_count?: number;
  called_at?: string;
  metadata?: Record<string, unknown>;
};

export type ObservabilityPerAgent = {
  agent: string;
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  estimated_cost_usd?: number;
  llm_call_count?: number;
};

export type ObservabilityResponse = {
  task_id: string;
  status?: string;
  current_agent?: string;
  agent_trace?: ObservabilityAgentTrace[];
  llm_usage?: LlmUsageRecord[];
  mcp_usage?: McpUsageRecord[];
  per_agent?: ObservabilityPerAgent[];
  totals?: {
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
    estimated_cost_usd?: number;
    mcp_call_count?: number;
    llm_call_count?: number;
    total_duration_ms?: number;
  };
  langsmith?: {
    enabled?: boolean;
    project?: string;
    trace_url?: string;
  };
};

export type ConfidenceLabel =
  | "official"
  | "review_verified"
  | "rule_inferred"
  | "community_likely"
  | "community_unverified"
  | "pending"
  | string;

export type DimensionsMm = {
  length?: number | null;
  width?: number | null;
  height?: number | null;
};

export type PriceRange = {
  usd?: number[];
  cny?: number[];
  status?: string;
  note?: string;
};

export type ProductIdentity = {
  official_model?: string;
  model?: string;
  brand?: string;
  family?: string;
  variant_name?: string;
  variant_type?: string;
  aliases?: string[];
  community_aliases?: string[];
  alias_confidence?: ConfidenceLabel;
  official_name_confidence?: ConfidenceLabel;
  shape_detail?: string;
  click_system?: string;
  data_status?: string;
  field_confidence?: Record<string, ConfidenceLabel>;
  official_fields?: string[];
  review_verified_fields?: string[];
  rule_inferred_fields?: string[];
  community_unverified_fields?: string[];
  pending?: string[] | string;
};

export type HardwareSpec = {
  product_id?: string;
  brand?: string;
  model?: string;
  weight_g?: number | null;
  sensor?: string;
  dpi_max?: number | null;
  polling_rate_hz?: number | null;
  connection?: string[];
  battery_hours?: number | null;
  switch_type?: string;
  click_system?: string;
  software?: string;
  onboard_memory?: boolean | null;
  shape?: string;
  price_range?: PriceRange | null;
  field_confidence?: Record<string, ConfidenceLabel>;
  sources?: Array<Record<string, unknown>>;
};

export type MatrixCell = {
  score?: number | null;
  summary?: string;
  analysis?: string;
  evidence_ids?: string[];
  confidence_score?: number;
  data_status?: string;
};

export type CompetitiveMatrix = {
  dimensions?: Record<string, Record<string, MatrixCell>>;
  generated_at?: string;
};

export type FeatureNode = {
  name: string;
  status?: "available" | "partial" | "pending" | "insufficient_evidence" | string;
  summary?: string;
  evidence_ids?: string[];
  source?: string;
  fields?: string[];
};

export type FeatureTree = {
  schema_name?: "gaming_mouse_feature_tree" | string;
  performance?: FeatureNode;
  shape_and_weight?: FeatureNode;
  wireless_and_battery?: FeatureNode;
  click_system?: FeatureNode;
  software_ecosystem?: FeatureNode;
};

export type PricingModel = {
  schema_name?: "gaming_mouse_pricing_model" | string;
  status?: "pending" | "reference_only" | "available" | string;
  realtime_price_status?: "mcp_not_connected" | "pending" | "available" | string;
  price_range_reference?: Array<Record<string, unknown>>;
  value_score_status?: "pending" | "available" | string;
  note?: string;
};

export type UserPersona = {
  schema_name?: "gaming_mouse_user_persona" | string;
  status?: "pending" | "insufficient_evidence" | "available" | string;
  grip_style_fit?: Record<string, string>;
  hand_size_fit?: Record<string, string>;
  game_type_fit?: Record<string, string>;
  target_persona?: string[];
  evidence_status?: string;
  limitation?: string;
};

export type EvidenceLinks = {
  used_claim_ids?: string[];
  used_evidence_ids?: string[];
  evidence_status?: Record<string, unknown>;
  unsupported_claim_ids?: string[];
  pending_data?: Array<Record<string, unknown>>;
  risk_flags?: Array<Record<string, unknown>>;
};

export type ScoreFlow = {
  baseline_score?: Record<string, unknown>;
  agent_adjustments?: Array<Record<string, unknown>>;
  final_score?: Record<string, unknown>;
  products?: Array<Record<string, unknown>>;
};

export type AgentContribution = {
  agent: string;
  role?: string;
  summary?: string;
  status?: string;
};

export type SearchMcpCandidate = {
  title?: string;
  url?: string;
  domain?: string;
  snippet?: string;
  source_type?: string;
  provider_score?: number;
  confidence_hint?: number;
};

export type SearchMcpResult = {
  status?: string;
  provider?: string;
  query?: string;
  executed_query?: string;
  category?: string;
  intent?: string;
  candidates?: SearchMcpCandidate[];
  candidate_count?: number;
  needs_llm_disambiguation?: boolean;
  latency_ms?: number;
  cache_hit?: boolean;
  note?: string;
};

export type ExternalProductCandidate = {
  original_input?: string;
  candidate_status?: string;
  provider?: string;
  executed_query?: string;
  best_candidate?: SearchMcpCandidate | null;
  official_candidates?: SearchMcpCandidate[];
  review_candidates?: SearchMcpCandidate[];
  usable_candidate_count?: number;
  rejected_candidate_count?: number;
  needs_llm_disambiguation?: boolean;
  next_action?: string;
  note?: string;
  consumable_by_next_agent?: boolean;
};

export type OfficialSpecRecord = {
  input?: string;
  brand_hint?: string;
  model_hint?: string;
  category?: string;
  source?: string;
  source_url?: string;
  source_domain?: string;
  status?: string;
  record?: Partial<HardwareSpec> & {
    official_model?: string;
    source_title?: string;
    official_url?: string;
    missing_fields?: string[];
    evidence_snippets?: string[];
    confidence?: string;
    extraction_method?: string;
    [key: string]: unknown;
  };
  missing_fields?: string[];
  confidence?: string;
  field_confidence?: Record<string, ConfidenceLabel | string>;
  latency_ms?: number;
  note?: string;
  collected_at?: string;
};

export type ReviewIntelSignal = {
  dimension?: string;
  summary?: string;
  sentiment?: string;
  confidence?: string;
  support_level?: string;
  source_ids?: string[];
  source_urls?: string[];
  source_kinds?: string[];
  corroborating_sources?: number;
  evidence_ids?: string[];
  evidence_snippets?: string[];
  [key: string]: unknown;
};

export type ReviewIntelRecord = {
  input?: string;
  product_id?: string;
  brand?: string;
  model?: string;
  status?: string;
  signals?: Record<string, ReviewIntelSignal>;
  fit_recommendations?: Array<Record<string, unknown>>;
  common_complaints?: string[];
  limitations?: string[];
  sources?: Array<Record<string, unknown>>;
  source_summary?: Record<string, number>;
  fetch_summary?: Record<string, number>;
  source_urls?: string[];
  blocked_sources?: Array<Record<string, unknown>>;
  search_result?: SearchMcpResult | Record<string, unknown>;
  confidence_level?: string;
  review_dimensions_pending?: string[];
  note?: string;
  extraction_method?: string;
  source_route?: string;
  llm_model?: string;
  llm_error?: string;
  collected_at?: string;
  evidence_ids?: string[];
  [key: string]: unknown;
};

export type FinalReport = {
  schema_name?: "gaming_mouse_competitive_report" | string;
  schema_version?: string;
  report_kind?: "gaming_mouse_product_comparison" | string;
  report_type?: "agent_final_report" | string;
  title?: string;
  summary?: Record<string, unknown> | string | string[];
  executive_summary?: string | string[];
  product_identification?: ProductIdentity[];
  hardware_specs?: HardwareSpec[];
  official_spec_records?: OfficialSpecRecord[];
  review_intel_records?: ReviewIntelRecord[];
  review_intel_status?: Record<string, unknown>;
  hardware_fact_comparison?: Record<string, unknown>;
  product_matrix?: CompetitiveMatrix;
  business_matrix?: CompetitiveMatrix;
  feature_tree?: FeatureTree;
  pricing_model?: PricingModel;
  user_persona?: UserPersona;
  evidence_links?: EvidenceLinks;
  score_flow?: ScoreFlow;
  agent_contributions?: AgentContribution[];
  pending_data?: Array<Record<string, unknown>>;
  risk_disclosure?: Array<Record<string, unknown>>;
  risk_flags?: Array<Record<string, unknown>>;
  quality_status?: string;
  report_status?: string;
  approved_with_limitations?: boolean;
  partial_report?: boolean;
  auto_degraded?: boolean;
  limitations?: string[];
  final_recommendation?: Record<string, unknown>;
  final_score?: Array<Record<string, unknown>>;
  used_claim_ids?: string[];
  used_evidence_ids?: string[];
  generated_at?: string;
  [key: string]: unknown;
};

export type SwotPoint = {
  point?: string;
  product?: string;
  evidence_ids?: string[];
  confidence?: string;
  grounded?: boolean;
};

export type AnalysisAiInterpretation = {
  status?: string;
  model?: string;
  overall_reading?: string;
  swot?: {
    strengths?: SwotPoint[];
    weaknesses?: SwotPoint[];
    opportunities?: SwotPoint[];
    threats?: SwotPoint[];
  };
  data_gaps?: string[];
  human_feedback_questions?: string[];
  used_claim_ids?: string[];
  used_evidence_ids?: string[];
  generated_at?: string;
  llm_error?: string;
  [key: string]: unknown;
};

export type HumanFeedbackRecord = {
  feedback_id?: string;
  type?: string;
  product?: string;
  dimension?: string;
  message?: string;
  status?: string;
  needs_verification?: boolean;
  created_at?: string;
  [key: string]: unknown;
};
