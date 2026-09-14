"""Verification Agent - faithfulness check over claims and matrix conclusions.

Runs after AnalysisAgent and before QualityAgent. It does not create or edit
claims (the ``merge_claims`` reducer keeps the first version of each claim_id, so edits
would be ignored). Instead it produces a separate ``faithfulness_report`` and a list of
``unsupported_claim_ids`` that downstream agents consume:

- QualityAgent gates on ``unsupported_claim_ids`` (routes back to the owning agent),
- ReportAgent excludes unsupported claims from the final report,
- QualityAgent lowers report credibility for unsupported claims,
- metrics expose ``faithfulness_rate``.
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.services.faithfulness import verify_claims


def _matrix_issues(state: dict, report: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Surface matrix cells whose prose contains numbers not present in their evidence."""
    import re

    from app.services.faithfulness import _evidence_by_id, _numbers, _significant_numbers, _evidence_text

    def _strip_evidence_ids(text: str) -> str:
        return re.sub(r"(?<![A-Za-z0-9])EV\d{3,}(?![A-Za-z0-9])", "", text or "")

    evidence_by_id = _evidence_by_id(
        [item for item in state.get("evidence_list", []) if isinstance(item, dict)]
    )
    issues: List[Dict[str, Any]] = []

    for matrix_name in ("product_matrix", "business_matrix"):
        matrix = state.get(matrix_name, {})
        dimensions = matrix.get("dimensions", {}) if isinstance(matrix, dict) else {}
        if not isinstance(dimensions, dict):
            continue
        for dimension, platform_map in dimensions.items():
            if not isinstance(platform_map, dict):
                continue
            for platform, cell in platform_map.items():
                if not isinstance(cell, dict):
                    continue
                analysis = str(cell.get("analysis") or cell.get("summary") or "")
                cited_ids = [str(i) for i in cell.get("evidence_ids", []) if str(i)]
                cited_text = " ".join(
                    _evidence_text(evidence_by_id[i]) for i in cited_ids if i in evidence_by_id
                )
                cleaned_analysis = _strip_evidence_ids(analysis).replace(str(platform), "")
                analysis_numbers = _significant_numbers(cleaned_analysis)
                evidence_numbers = _numbers(_strip_evidence_ids(cited_text))
                missing = sorted(n for n in analysis_numbers if n not in evidence_numbers)
                if missing:
                    issues.append(
                        {
                            "matrix": matrix_name,
                            "platform": platform,
                            "dimension": dimension,
                            "missing_numbers": missing,
                        }
                    )
    return issues


def _append_trace(state: dict, report: Dict[str, Any]) -> None:
    trace_log = state.setdefault("trace_log", [])
    trace_log.append(
        {
            "step_id": len(trace_log) + 1,
            "agent_name": "VerificationAgent",
            "status": "success",
            "output_summary": (
                f"verified {report['checked_claim_count']} claims, "
                f"{report['unsupported_claim_count']} unsupported, "
                f"faithfulness_rate={report['faithfulness_rate']}"
            ),
            "error": None,
        }
    )


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _price_verification(state: dict) -> Dict[str, Any]:
    records = [item for item in state.get("price_records", []) if isinstance(item, dict)]
    rows: List[Dict[str, Any]] = []
    for record in records:
        quotes = [item for item in record.get("quotes", []) if isinstance(item, dict)]
        usable_quotes = [
            quote
            for quote in quotes
            if quote.get("price") is not None and _as_text(quote.get("source_url"))
        ]
        usable_quotes.sort(
            key=lambda quote: (
                3 if _as_text(quote.get("source_type")) == "official_store" else 1,
                {"high": 3, "medium": 2, "low": 1}.get(_as_text(quote.get("confidence")), 0),
            ),
            reverse=True,
        )
        fallback_links = [item for item in record.get("fallback_links", []) if isinstance(item, dict)]
        model = _as_text(record.get("model") or record.get("input")) or "unknown product"
        evidence_id = _as_text(record.get("evidence_id"))
        if usable_quotes:
            best = usable_quotes[0]
            official = _as_text(best.get("source_type")) == "official_store"
            rows.append(
                {
                    "product": model,
                    "status": "supported" if official else "weak_support",
                    "support_level": "strong" if official else "weak",
                    "reason": (
                        "Realtime price is backed by an official-store URL."
                        if official
                        else "Realtime price comes from a non-official commerce/search source; usable for comparison with low confidence."
                    ),
                    "evidence_id": evidence_id,
                    "source_url": best.get("source_url"),
                    "price": best.get("price"),
                    "currency": best.get("currency"),
                    "source_type": best.get("source_type"),
                    "confidence": best.get("confidence"),
                }
            )
        elif record.get("official_price_blocked") or fallback_links:
            link = fallback_links[0] if fallback_links else {}
            rows.append(
                {
                    "product": model,
                    "status": "weak_support",
                    "support_level": "weak",
                    "reason": "Official price was blocked or no reliable quote was extracted; fallback link is traceability only.",
                    "evidence_id": evidence_id,
                    "source_url": link.get("url") or "",
                    "price": None,
                    "currency": record.get("currency"),
                    "source_type": link.get("source_kind") or "fallback",
                    "confidence": "low",
                }
            )
        else:
            rows.append(
                {
                    "product": model,
                    "status": "not_supported",
                    "support_level": "none",
                    "reason": _as_text(record.get("note")) or "No reliable realtime price source was collected.",
                    "evidence_id": evidence_id,
                    "source_url": "",
                    "price": None,
                    "currency": record.get("currency"),
                    "source_type": "",
                    "confidence": "none",
                }
            )
    return {
        "checked_price_records": len(rows),
        "supported_price_records": len([item for item in rows if item["status"] == "supported"]),
        "weak_price_records": len([item for item in rows if item["status"] == "weak_support"]),
        "unsupported_price_records": len([item for item in rows if item["status"] == "not_supported"]),
        "rows": rows,
    }


def _review_verification(state: dict) -> Dict[str, Any]:
    records = [item for item in state.get("review_intel_records", []) if isinstance(item, dict)]
    rows: List[Dict[str, Any]] = []
    for record in records:
        model = _as_text(record.get("model") or record.get("input")) or "unknown product"
        signals = record.get("signals") if isinstance(record.get("signals"), dict) else {}
        for dimension, signal in signals.items():
            if not isinstance(signal, dict):
                continue
            evidence_ids = [
                _as_text(item)
                for item in signal.get("evidence_ids", [])
                if _as_text(item)
            ] if isinstance(signal.get("evidence_ids"), list) else []
            confidence = _as_text(signal.get("confidence")).lower()
            if evidence_ids and confidence in {"high", "medium"}:
                status = "supported"
                support_level = "strong" if confidence == "high" else "medium"
                reason = "Review signal cites ReviewIntel evidence and has sufficient source confidence."
            elif evidence_ids:
                status = "weak_support"
                support_level = "weak"
                reason = "Review signal has traceable evidence but only low-confidence/community/search support."
            else:
                status = "not_supported"
                support_level = "none"
                reason = "Review signal has no evidence_id and must not be used for scenario recommendations."
            rows.append(
                {
                    "product": model,
                    "dimension": dimension,
                    "status": status,
                    "support_level": support_level,
                    "reason": reason,
                    "evidence_ids": evidence_ids,
                    "confidence": confidence or "none",
                }
            )
    return {
        "checked_review_signals": len(rows),
        "supported_review_signals": len([item for item in rows if item["status"] == "supported"]),
        "weak_review_signals": len([item for item in rows if item["status"] == "weak_support"]),
        "unsupported_review_signals": len([item for item in rows if item["status"] == "not_supported"]),
        "rows": rows,
    }


def verification_agent(state: dict) -> Dict[str, Any]:
    """Verify claim/matrix faithfulness and expose a report for downstream agents."""
    claims = [item for item in state.get("claims", []) if isinstance(item, dict)]
    evidence_list = [item for item in state.get("evidence_list", []) if isinstance(item, dict)]

    report = verify_claims(claims, evidence_list)
    report["matrix_issues"] = _matrix_issues(state, report)
    report["price_verification"] = _price_verification(state)
    report["review_verification"] = _review_verification(state)

    next_state = {
        **state,
        "current_agent": "VerificationAgent",
        "faithfulness_report": report,
        "unsupported_claim_ids": report["unsupported_claim_ids"],
    }
    _append_trace(next_state, report)

    print(
        f"[VerificationAgent] 忠实性校验完成，"
        f"忠实率 {report['faithfulness_rate']}，未支撑 claim {report['unsupported_claim_count']} 条"
    )
    return next_state
