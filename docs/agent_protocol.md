# Agent Protocol

## Workflow

```text
ResearchAgent
  -> CollectorAgent
  -> EvidenceAgent
  -> AnalysisAgent
  -> VerificationAgent
  -> QualityAgent
       | approved / approved_with_limitations / partial_report
       v
     ReportAgent
```

## Structured Message Contract

Agents communicate through the shared LangGraph state, not free-form chat. Key fields:

| Field | Owner | Meaning |
|---|---|---|
| `data_requirements` | ResearchAgent | What data is needed for this task |
| `resolved_products` | CollectorAgent | Entity resolution and alias disambiguation |
| `product_facts` | CollectorAgent | Local JSON hardware facts with evidence IDs |
| `pending_data` | CollectorAgent / AnalysisAgent | MCP gaps disclosed explicitly |
| `evidence_list` | EvidenceAgent | Structured, traceable evidence records |
| `claims` | AnalysisAgent | Evidence-bound claims |
| `product_matrix` | AnalysisAgent | Hardware-fact comparison matrix |
| `business_matrix` | AnalysisAgent | Conservative software/market placeholders |
| `risk_flags` | AnalysisAgent | Data gaps and reliability risks |
| `faithfulness_report` | VerificationAgent | Claim/evidence consistency results |
| `quality_result` | QualityAgent | Quality gate, limitations and retry target |
| `final_report` | ReportAgent | `GamingMouseFinalReportSchema` payload |
| `trace_log` | All agents | Observable execution trail |

## Quality Loop

QualityAgent checks whether claims cite valid evidence, whether unsupported claims exist, whether pending data is disclosed, and whether the professional report schema can be produced. Failed checks route back to the responsible upstream node. After the retry cap, the workflow produces `partial_report` instead of pretending the report is complete.

## Traceability

Every claim must cite `evidence_ids`. ReportAgent only uses supported claims and exposes:

- `used_claim_ids`
- `used_evidence_ids`
- `evidence_links`
- `unsupported_claim_ids`
- `pending_data`
- `risk_flags`

## Context Management

When LLM-backed agents are enabled, evidence context is selected by credibility, dimension coverage and content length. The prompt receives trimmed evidence, while verification still runs against full structured evidence.
