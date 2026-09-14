# Architecture

## Components

```text
React frontend
  -> FastAPI API
  -> LangGraph workflow
  -> GamingMouseFinalReportSchema
```

## DAG

```text
ResearchAgent
  -> CollectorAgent
  -> EvidenceAgent
  -> AnalysisAgent
  -> VerificationAgent
  -> QualityAgent
       | retry to upstream agent
       | partial_report after retry cap
       v
     ReportAgent
```

## Data Sources

- Local product facts: `data/products/gaming_mice.json`
- MCP Tool Layer: future official specs, reviews, prices and search tools
- Pending external data: official specs, reviews, creator tests, realtime price, long-term reliability

There is no simulation provider and no bundled evidence fallback.

## Hallucination Control

- Claims must cite existing `evidence_id` values.
- VerificationAgent checks claim faithfulness against cited evidence.
- ReportAgent excludes unsupported claims.
- QualityAgent lowers report credibility when data is pending or unsupported.

## Frontend Contract

The frontend should render the latest professional schema directly:

- entity recognition from `product_identification`
- hardware tables from `hardware_specs`
- data gaps from `pending_data`
- source tracing from `evidence_links`
- final recommendation from `final_recommendation`
