import { useState } from "react";
import { analysisApi } from "../api/analysisApi";
import { DEFAULT_PRODUCT_CATEGORY } from "../api/productApi";
import {
  ProductSearchCombobox,
  ProductThumb,
} from "../components/common/ProductSearchCombobox";
import { StatusBadge } from "../components/common/StatusBadge";
import type { StartAnalysisRequest } from "../types/analysis";
import type { GamingMouseProduct, ProductSearchResult } from "../types/product";

type ProductComparePageProps = {
  displayTaskId?: string;
  onNavigate?: (key: string) => void;
  onTaskCreated?: (taskId: string) => void;
};

type Side = "a" | "b";

const SIDE_THEME: Record<
  Side,
  { label: string; accent: "cyan" | "violet"; soft: string; border: string; text: string }
> = {
  a: {
    label: "产品 A",
    accent: "cyan",
    soft: "bg-cyan-400/10",
    border: "border-cyan-300/40",
    text: "text-cyan-200",
  },
  b: {
    label: "产品 B",
    accent: "violet",
    soft: "bg-violet-400/10",
    border: "border-violet-300/40",
    text: "text-violet-200",
  },
};

const MATCH_LABEL: Record<string, string> = {
  id: "产品 ID",
  model: "官方型号",
  alias: "别名",
  community_alias: "玩家简称",
  family: "系列",
  brand: "品牌",
};

const CONFIDENCE_LABEL: Record<string, string> = {
  verified: "官方确认",
  likely: "较可信",
  unverified: "待确认",
  family: "系列匹配",
  brand: "品牌匹配",
};

const AGENT_ANALYSIS_DIMENSIONS = [
  "性能参数",
  "轻量化设计",
  "无线与续航",
  "软件生态",
  "用户口碑",
  "价格定位",
  "电竞品牌影响力",
  "握持手感与人体工学",
];

function confidenceTone(
  confidence?: string,
): "success" | "warning" | "info" | "neutral" {
  if (confidence === "verified") return "success";
  if (confidence === "unverified") return "warning";
  if (confidence === "likely" || confidence === "family" || confidence === "brand") {
    return "info";
  }
  return "neutral";
}

function productName(product: GamingMouseProduct): string {
  return `${product.brand} ${product.model}`;
}

function buildAnalysisPayload(
  productAInput: string,
  productBInput: string,
  productA?: GamingMouseProduct | null,
  productB?: GamingMouseProduct | null,
): StartAnalysisRequest {
  const productALabel = productA ? productName(productA) : productAInput;
  const productBLabel = productB ? productName(productB) : productBInput;
  const payload: StartAnalysisRequest = {
    industry_key: productA?.category || productB?.category || "gaming_mouse",
    target_platform: productALabel,
    competitors: [productALabel, productBLabel],
    analysis_scene: `电竞鼠标产品对比：${productALabel} vs ${productBLabel}`,
    target_user: "电竞外设购买决策用户",
    time_range: "近两年",
    focus_dimensions: AGENT_ANALYSIS_DIMENSIONS,
  };

  if (productA && productB) {
    payload.selected_products = [
      {
        id: productA.id,
        model: productA.model,
        brand: productA.brand,
        category: productA.category,
      },
      {
        id: productB.id,
        model: productB.model,
        brand: productB.brand,
        category: productB.category,
      },
    ];
  }

  return payload;
}

function SelectedProductCard({
  side,
  selected,
  onClear,
}: {
  side: Side;
  selected: ProductSearchResult;
  onClear: () => void;
}) {
  const theme = SIDE_THEME[side];
  const matchLabel = MATCH_LABEL[selected.matched_by] ?? selected.matched_by;
  const confidenceLabel = selected.match_confidence
    ? CONFIDENCE_LABEL[selected.match_confidence] ?? selected.match_confidence
    : "";

  return (
    <div
      className={`mt-4 flex items-start gap-3 rounded-lg border ${theme.border} ${theme.soft} p-3`}
    >
      <ProductThumb
        src={selected.product.image_url}
        alt={selected.product.image_alt || `${selected.brand} ${selected.model}`}
        accent={theme.accent}
      />
      <div className="min-w-0 flex-1">
        <p className="text-xs text-slate-400">{selected.brand}</p>
        <p className="truncate text-lg font-semibold text-white">{selected.model}</p>
        <div className="mt-2 flex flex-wrap gap-2">
          <StatusBadge label={`${matchLabel}: ${selected.matched_value}`} tone="info" />
          {confidenceLabel ? (
            <StatusBadge
              label={confidenceLabel}
              tone={confidenceTone(selected.match_confidence)}
            />
          ) : null}
        </div>
      </div>
      <button
        className="shrink-0 rounded-md border border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-300 transition hover:border-cyan-300 hover:text-cyan-100"
        onClick={onClear}
        type="button"
      >
        更换
      </button>
    </div>
  );
}

function ProductPicker({
  side,
  category,
  selected,
  rawInput,
  onSelect,
  onInputChange,
  onClear,
}: {
  side: Side;
  category: string;
  selected: ProductSearchResult | null;
  rawInput: string;
  onSelect: (result: ProductSearchResult) => void;
  onInputChange: (value: string) => void;
  onClear: () => void;
}) {
  const theme = SIDE_THEME[side];

  return (
    <section
      className={`rounded-xl border bg-slate-950/70 p-4 shadow-[0_18px_50px_rgba(2,6,23,0.18)] ${
        selected ? `${theme.border} ${theme.soft}` : "border-slate-800"
      }`}
    >
      <div className="flex items-center justify-between">
        <span
          className={`inline-flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold ${theme.soft} ${theme.text} ring-1 ${theme.border}`}
        >
          {side === "a" ? "A" : "B"}
        </span>
        <span className="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">
          {theme.label}
        </span>
      </div>

      {selected ? (
        <SelectedProductCard side={side} selected={selected} onClear={onClear} />
      ) : (
        <div className="mt-4">
          <ProductSearchCombobox
            category={category}
            accent={theme.accent}
            placeholder={`搜索${theme.label}，如 GPX2 / Viper V3 Pro`}
            onSelect={onSelect}
            onQueryChange={onInputChange}
          />
          {rawInput.trim() ? (
            <p className="mt-2 text-xs leading-5 text-slate-500">
              可以直接输入并开始分析；若未命中本地库，硬件事实会在后续 Agent 中标记为待官网 MCP 补齐。
            </p>
          ) : null}
        </div>
      )}
    </section>
  );
}

export function ProductComparePage({
  onNavigate,
  onTaskCreated,
}: ProductComparePageProps) {
  const category = DEFAULT_PRODUCT_CATEGORY;
  const [selectedA, setSelectedA] = useState<ProductSearchResult | null>(null);
  const [selectedB, setSelectedB] = useState<ProductSearchResult | null>(null);
  const [inputA, setInputA] = useState("");
  const [inputB, setInputB] = useState("");
  const [isStartingAnalysis, setIsStartingAnalysis] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

  async function handleStartAnalysis() {
    if (isStartingAnalysis) return;

    const productAInput = selectedA ? productName(selectedA.product) : inputA.trim();
    const productBInput = selectedB ? productName(selectedB.product) : inputB.trim();

    if (!productAInput || !productBInput) {
      setAnalysisError("请输入产品 A 和产品 B。");
      return;
    }

    setIsStartingAnalysis(true);
    setAnalysisError(null);

    try {
      const response = await analysisApi.startAnalysis(
        buildAnalysisPayload(
          productAInput,
          productBInput,
          selectedA?.product,
          selectedB?.product,
        ),
      );
      if (!response?.task_id) {
        throw new Error("系统未返回任务编号");
      }
      onTaskCreated?.(response.task_id);
      onNavigate?.("workflow");
    } catch (err) {
      setAnalysisError(err instanceof Error ? err.message : "启动分析失败");
    } finally {
      setIsStartingAnalysis(false);
    }
  }

  return (
    <section className="mx-auto max-w-5xl">
      <div className="mb-6">
        <p className="text-sm font-medium text-cyan-300">产品分析入口</p>
        <h2 className="mt-2 text-3xl font-semibold text-white">
          电竞外设 Agent 分析
        </h2>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <ProductPicker
          side="a"
          category={category}
          selected={selectedA}
          rawInput={inputA}
          onSelect={(result) => {
            setSelectedA(result);
            setInputA(productName(result.product));
            setAnalysisError(null);
          }}
          onInputChange={(value) => {
            setInputA(value);
            setAnalysisError(null);
          }}
          onClear={() => {
            setSelectedA(null);
            setInputA("");
          }}
        />
        <ProductPicker
          side="b"
          category={category}
          selected={selectedB}
          rawInput={inputB}
          onSelect={(result) => {
            setSelectedB(result);
            setInputB(productName(result.product));
            setAnalysisError(null);
          }}
          onInputChange={(value) => {
            setInputB(value);
            setAnalysisError(null);
          }}
          onClear={() => {
            setSelectedB(null);
            setInputB("");
          }}
        />
      </div>

      <div className="mt-6 flex flex-col items-center gap-3">
        <button
          className="rounded-lg bg-cyan-300 px-8 py-3 text-base font-semibold text-slate-950 shadow-[0_0_28px_rgba(34,211,238,0.2)] transition hover:bg-cyan-200 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400 disabled:shadow-none"
          disabled={isStartingAnalysis}
          onClick={handleStartAnalysis}
          type="button"
        >
          {isStartingAnalysis ? "启动中..." : "开始分析"}
        </button>

        {analysisError ? (
          <div className="rounded-md border border-rose-500/35 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
            {analysisError}
          </div>
        ) : null}
      </div>
    </section>
  );
}
