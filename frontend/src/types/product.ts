// 产品规格事实底座（data/products/*.json）的前端类型。
// 对应后端 backend/app/services/product_catalog_service.py 的返回结构。

export type ProductMatchedBy =
  | "id"
  | "brand"
  | "model"
  | "alias"
  | "community_alias"
  | "family";

export type ProductSource = {
  source_type: string; // official / review / database ...
  publisher?: string;
  title?: string;
  url?: string;
};

export type FieldConfidence = Record<string, string>;
export type FieldConfidenceSummary = Record<string, string[]>;

export type ProductPriceRange = {
  usd?: number[];
  cny?: number[];
};

export type ProductDimensions = {
  length?: number;
  width?: number;
  height?: number;
};

// 单款电竞鼠标的结构化规格。
export type GamingMouseProduct = {
  id: string;
  brand: string;
  model: string;
  aliases: string[];
  category: string;
  release_year?: number;
  weight_g: number | null;
  dimensions_mm: ProductDimensions;
  shape: string; // "symmetrical" | "ergonomic"
  sensor: string;
  dpi_max: number | null;
  polling_rate_hz: number | null;
  connection: string[]; // ["wired","2.4ghz","bluetooth"]
  battery_hours: number | null;
  switch_type: string;
  software: string;
  onboard_memory: boolean | null;
  price_range?: ProductPriceRange;
  official_url?: string;
  // 图片字段：后端保证一定返回这三个键，缺图时为空字符串。
  image_url: string;
  image_alt: string;
  image_source_url: string;
  // 产品身份 / 变体 / 模具（后端 _ensure_identity_fields 保证存在）。
  family?: string;
  variant_name?: string;
  variant_type?: string;
  mold_id?: string;
  shape_detail?: string;
  click_system?: string;
  community_aliases?: string[];
  alias_confidence?: string; // verified / likely / unverified
  official_name_confidence?: string; // verified / likely / unknown
  data_status?: string; // verified / partial / pending_review
  field_confidence?: FieldConfidence;
  sources: ProductSource[];
  notes?: string;
  updated_at?: string;
};

// 搜索卡片用的精简身份信息（后端 _identity_summary）。
export type ProductIdentitySummary = {
  family?: string | null;
  variant_name?: string | null;
  variant_type?: string | null;
  mold_id?: string | null;
  shape?: string | null;
  shape_detail?: string | null;
  weight_g?: number | null;
  connection?: string[];
  click_system?: string | null;
  alias_confidence?: string | null;
  official_name_confidence?: string | null;
  data_status?: string | null;
  field_confidence?: FieldConfidence;
  field_confidence_summary?: FieldConfidenceSummary;
};

// GET /api/products/{category} 的信封结构。
export type ProductCatalog = {
  category: string;
  category_label?: string;
  schema_version?: string;
  updated_at?: string;
  description?: string;
  field_units?: Record<string, string>;
  enums?: Record<string, string[]>;
  count?: number;
  products: GamingMouseProduct[];
};

// GET /api/products/search 的单条结果。
export type ProductMatchConfidence =
  | "verified"
  | "likely"
  | "unverified"
  | "family"
  | "brand";

export type ProductSearchResult = {
  id: string;
  brand: string;
  model: string;
  matched_by: ProductMatchedBy;
  matched_value: string;
  match_quality?: number; // 3=完全相等 2=前缀 1=包含
  match_confidence?: ProductMatchConfidence;
  identity?: ProductIdentitySummary;
  product: GamingMouseProduct;
};

export type ProductSearchResponse = {
  query: string;
  normalized_query: string;
  category: string;
  count: number;
  needs_disambiguation?: boolean;
  disambiguation_reason?: string | null;
  results: ProductSearchResult[];
};

// GET /api/products/{category}/{product_id}
export type ProductDetailResponse = {
  category: string;
  matched_by: ProductMatchedBy;
  matched_value: string;
  product: GamingMouseProduct;
};

// ---- 对比 ----
export type SpecDiffType = "numeric" | "set" | "categorical" | "boolean";
export type SpecAdvantage = "a" | "b" | "equal" | null;
export type SpecValue = number | string | string[] | boolean | null;

export type SpecDifference = {
  field: string;
  label: string;
  type: SpecDiffType;
  a: SpecValue;
  b: SpecValue;
  comparable?: boolean;
  equal?: boolean | null;
  // numeric
  preferred?: "lower" | "higher" | null;
  diff?: number | null;
  abs_diff?: number | null;
  advantage?: SpecAdvantage;
  group?: string; // e.g. "dimensions_mm"
  // set
  common?: string[];
  only_a?: string[];
  only_b?: string[];
};

export type ProductMatchInfo = {
  input: string;
  matched_by: ProductMatchedBy;
  matched_value: string;
  resolved_id: string;
};

export type ProductSourceSummary = {
  official_url?: string;
  updated_at?: string;
  source_count: number;
  official_count: number;
  publishers: Array<string | null>;
  sources: ProductSource[];
};

// ---- 产品评分（基于硬件 JSON，独立于报告 quality_score）----
export type ProductScore = {
  product_id?: string;
  model?: string;
  brand?: string;
  hardware_specs?: {
    weight_g?: number | null;
    dimensions_mm?: ProductDimensions;
    shape?: string | null;
    sensor?: string | null;
    dpi_max?: number | null;
    polling_rate_hz?: number | null;
    connection?: string[];
    battery_hours?: number | null;
    switch_type?: string | null;
    software?: string | null;
    onboard_memory?: boolean | null;
    mold_id?: string | null;
    shape_detail?: string | null;
    click_system?: string | null;
  };
  overall_score: {
    current_score: number | null;
    full_score_with_missing_as_zero: number | null;
  };
  hardware_score: number | null;
  software_score: number | null;
  game_fit_score: number | null;
  persona_fit_score: number | null;
  // 专业维度（本轮新增）
  grip_fit_score?: number | null;
  hand_fit_score?: number | null;
  game_type_fit_score?: number | null;
  click_system_score?: number | null;
  shape_confidence?: number; // 0..1，模具置信度
  sentiment_score: number | null; // MCP 未接入 -> null
  sentiment_status?: string; // "pending"
  data_completeness: number; // 0..1
  pending_dimensions: string[];
  subscores?: Record<string, number | null>;
  game_fit?: {
    fps?: number;
    moba?: number;
    office?: number;
    best_fit?: string;
  };
  persona_fit?: {
    small_hand?: number;
    large_hand?: number;
    low_sens?: number;
    high_sens?: number;
    best_fit?: string[];
  };
  grip_fit?: {
    palm?: number;
    claw?: number;
    fingertip?: number;
    best_fit?: string;
  };
  hand_fit?: {
    small?: number;
    medium?: number;
    large?: number;
    best_fit?: string;
  };
  game_type_fit?: {
    tactical_fps?: number;
    tracking_fps?: number;
    moba?: number;
    rts?: number;
    office?: number;
    best_fit?: string;
  };
  click_system?: {
    type?: string;
    score?: number;
    pros?: string;
    risk?: string;
  };
  identity?: Record<string, unknown>;
  score_basis?: Record<string, string>;
};

export type ProductScoreVerdicts = {
  strongest_overall?: string | null;
  strongest_hardware?: string | null;
  best_software?: string | null;
  best_click_system?: string | null;
  best_for?: Record<string, string | null>;
  pending_verification?: string[];
};

// 产品识别与变体说明（report 用）。
export type ProductIdentification = {
  model?: string;
  brand?: string;
  family?: string;
  variant_name?: string;
  variant_type?: string;
  mold_id?: string;
  shape_detail?: string;
  shape_confidence?: number;
  click_system?: string;
  official_name_confidence?: string;
  alias_confidence?: string;
  data_status?: string;
  field_confidence?: FieldConfidence;
  field_confidence_summary?: FieldConfidenceSummary;
  official_fields?: string[];
  review_verified_fields?: string[];
  rule_inferred_fields?: string[];
  community_likely_fields?: string[];
  community_unverified_fields?: string[];
  hardware_based?: string;
  pending?: string;
};

export type ProductScoreboard = {
  product_a: ProductScore;
  product_b: ProductScore;
  verdicts: ProductScoreVerdicts;
  identification?: ProductIdentification[];
  scale?: string;
  score_type?: string;
  score_type_note?: string;
  price_note?: string;
  not_final?: boolean;
  pending_dimensions?: string[];
};

// POST /api/products/compare
export type ProductCompareResponse = {
  category: string;
  product_a: GamingMouseProduct;
  product_b: GamingMouseProduct;
  product_scores?: ProductScoreboard;
  matched_by: {
    product_a: ProductMatchInfo;
    product_b: ProductMatchInfo;
  };
  spec_differences: SpecDifference[];
  missing_fields: {
    product_a: string[];
    product_b: string[];
  };
  source_summary: {
    product_a: ProductSourceSummary;
    product_b: ProductSourceSummary;
  };
};

export type ProductCategoriesResponse = {
  categories: string[];
};
