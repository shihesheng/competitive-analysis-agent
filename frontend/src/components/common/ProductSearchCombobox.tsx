import { useEffect, useMemo, useRef, useState } from "react";
import { productApi } from "../../api/productApi";
import type { ProductSearchResult } from "../../types/product";

type Accent = "cyan" | "violet";

type AccentTheme = {
  inputFocus: string;
  cardActive: string;
  chip: string;
  dot: string;
  frame: string;
};

const ACCENT: Record<Accent, AccentTheme> = {
  cyan: {
    inputFocus: "focus:border-cyan-300",
    cardActive: "border-cyan-300/60 bg-cyan-400/10 ring-1 ring-cyan-300/40",
    chip: "border-cyan-300/40 bg-cyan-400/10 text-cyan-200",
    dot: "bg-cyan-400",
    frame: "from-cyan-400/20",
  },
  violet: {
    inputFocus: "focus:border-violet-300",
    cardActive: "border-violet-300/60 bg-violet-400/10 ring-1 ring-violet-300/40",
    chip: "border-violet-300/40 bg-violet-400/10 text-violet-200",
    dot: "bg-violet-400",
    frame: "from-violet-400/20",
  },
};

const MAX_RESULTS = 6;

const CONFIDENCE_TAG: Record<string, { label: string; cls: string }> = {
  verified: { label: "官方确认", cls: "border-emerald-400/40 bg-emerald-400/10 text-emerald-200" },
  likely: { label: "较可信", cls: "border-amber-400/40 bg-amber-400/10 text-amber-200" },
  unverified: { label: "待确认", cls: "border-rose-400/40 bg-rose-500/10 text-rose-200" },
  family: { label: "系列名", cls: "border-sky-400/40 bg-sky-400/10 text-sky-200" },
  brand: { label: "品牌名", cls: "border-slate-500/40 bg-slate-700/50 text-slate-200" },
};

// 鼠标剪影占位图：缺图或图片加载失败时显示，避免空白/破图。
function MouseGlyph({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 48" fill="none" className={className} aria-hidden>
      <rect
        x="5.5"
        y="3.5"
        width="21"
        height="41"
        rx="10.5"
        stroke="currentColor"
        strokeWidth="2"
        opacity="0.85"
      />
      <line x1="16" y1="5" x2="16" y2="20" stroke="currentColor" strokeWidth="2" opacity="0.7" />
      <rect x="14.5" y="9" width="3" height="9" rx="1.5" fill="currentColor" opacity="0.55" />
    </svg>
  );
}

// 产品缩略图：有图显示图，无图或破图回退到剪影占位。
export function ProductThumb({
  src,
  alt,
  accent,
}: {
  src: string;
  alt: string;
  accent: Accent;
}) {
  const [failed, setFailed] = useState(false);
  const showImage = Boolean(src) && !failed;
  const theme = ACCENT[accent];

  return (
    <div
      className={`relative flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-slate-700/70 bg-gradient-to-br ${theme.frame} to-slate-900/80`}
    >
      {showImage ? (
        <img
          src={src}
          alt={alt}
          loading="lazy"
          onError={() => setFailed(true)}
          className="h-full w-full object-contain"
        />
      ) : (
        <MouseGlyph className="h-7 w-7 text-slate-400" />
      )}
    </div>
  );
}

export type ProductSearchComboboxProps = {
  category: string;
  accent: Accent;
  placeholder?: string;
  onSelect: (result: ProductSearchResult) => void;
  onQueryChange?: (query: string) => void;
};

// 带图片候选卡片的产品搜索框：调用 /api/products/search，方向键 ↑↓/Enter/Esc 可操作。
export function ProductSearchCombobox({
  category,
  accent,
  placeholder = "搜索型号或简称，如 GPX2 / Viper V3 Pro",
  onSelect,
  onQueryChange,
}: ProductSearchComboboxProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<ProductSearchResult[]>([]);
  const [needsDisambig, setNeedsDisambig] = useState(false);
  const [disambigReason, setDisambigReason] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const boxRef = useRef<HTMLDivElement | null>(null);
  const theme = ACCENT[accent];

  const visible = useMemo(() => results.slice(0, MAX_RESULTS), [results]);

  // 去抖搜索
  useEffect(() => {
    const q = query.trim();
    if (q.length < 1) {
      setResults([]);
      setLoading(false);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    const timer = window.setTimeout(async () => {
      try {
        const res = await productApi.searchProducts(q, category);
        if (!cancelled) {
          setResults(res.results ?? []);
          setNeedsDisambig(Boolean(res.needs_disambiguation));
          setDisambigReason(res.disambiguation_reason ?? null);
          setActiveIndex(0);
          setOpen(true);
          setError(null);
        }
      } catch {
        if (!cancelled) setError("搜索失败，请确认后端服务已启动。");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 280);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [query, category]);

  // 点击外部关闭
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  function choose(result: ProductSearchResult) {
    onSelect(result);
    setQuery("");
    onQueryChange?.("");
    setResults([]);
    setOpen(false);
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") {
      if (open) {
        setOpen(false);
      } else {
        setQuery("");
        onQueryChange?.("");
      }
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (!open && visible.length > 0) setOpen(true);
      setActiveIndex((i) => Math.min(visible.length - 1, i + 1));
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((i) => Math.max(0, i - 1));
      return;
    }
    if (event.key === "Enter") {
      if (open && visible[activeIndex]) {
        event.preventDefault();
        choose(visible[activeIndex]);
      }
    }
  }

  const showDropdown = open && query.trim().length > 0;

  return (
    <div className="relative" ref={boxRef}>
      <input
        className={`w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none transition ${theme.inputFocus}`}
        placeholder={placeholder}
        value={query}
        onChange={(event) => {
          setQuery(event.target.value);
          onQueryChange?.(event.target.value);
        }}
        onFocus={() => visible.length > 0 && setOpen(true)}
        onKeyDown={handleKeyDown}
        type="text"
        role="combobox"
        aria-expanded={showDropdown}
        aria-controls="product-search-listbox"
        aria-autocomplete="list"
      />

      {loading ? (
        <span
          className={`absolute right-3 top-2.5 h-2.5 w-2.5 animate-pulse rounded-full ${theme.dot}`}
        />
      ) : null}

      {error ? <p className="mt-2 text-xs text-rose-300">{error}</p> : null}

      {showDropdown ? (
        <div
          id="product-search-listbox"
          role="listbox"
          className="absolute z-30 mt-1 w-full overflow-hidden rounded-xl border border-slate-700 bg-slate-950/95 p-1.5 shadow-[0_24px_60px_rgba(2,6,23,0.55)] backdrop-blur"
        >
          {needsDisambig && visible.length > 0 ? (
            <div className="mb-1.5 rounded-lg border border-amber-400/40 bg-amber-400/10 px-3 py-2 text-[11px] leading-4 text-amber-100">
              {disambigReason || "匹配到多个候选，请选择具体官方型号"}
            </div>
          ) : null}
          {visible.length === 0 && !loading ? (
            <p className="px-3 py-3 text-xs text-slate-500">没有找到匹配的产品。</p>
          ) : (
            <ul className="space-y-1.5">
              {visible.map((result, index) => {
                const isActive = index === activeIndex;
                const product = result.product;
                const conf = result.match_confidence
                  ? CONFIDENCE_TAG[result.match_confidence]
                  : undefined;
                return (
                  <li key={result.id} role="option" aria-selected={isActive}>
                    <button
                      type="button"
                      onMouseEnter={() => setActiveIndex(index)}
                      onClick={() => choose(result)}
                      className={`flex w-full items-start gap-3 rounded-lg border px-2.5 py-2 text-left transition ${
                        isActive
                          ? theme.cardActive
                          : "border-transparent hover:border-slate-700 hover:bg-white/[0.03]"
                      }`}
                    >
                      <ProductThumb
                        src={product.image_url}
                        alt={product.image_alt || `${result.brand} ${result.model}`}
                        accent={accent}
                      />
                      <span className="min-w-0 flex-1">
                        <span className="block text-[11px] uppercase tracking-[0.12em] text-slate-500">
                          {result.brand}
                        </span>
                        <span className="block truncate text-sm font-semibold text-slate-100">
                          {result.model}
                        </span>
                        <span className="mt-0.5 block truncate text-[11px] text-slate-500">
                          命中 {result.matched_by}: {result.matched_value}
                        </span>
                      </span>
                      <span className="flex shrink-0 flex-col items-end gap-1">
                        {conf ? (
                          <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${conf.cls}`}>
                            {conf.label}
                          </span>
                        ) : null}
                        <span
                          className={`max-w-[120px] truncate rounded-full border px-2 py-0.5 text-[10px] font-medium ${theme.chip}`}
                          title={`命中字段 ${result.matched_by}`}
                        >
                          {result.matched_by}: {result.matched_value}
                        </span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  );
}
