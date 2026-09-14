"""Faithfulness verification - check that claims are grounded in cited evidence.

This is the second layer of hallucination suppression. The agents already enforce
that every claim references *existing* evidence_ids (citation validity). This module
adds *citation faithfulness*: it verifies that the claim text can actually be derived
from the content of the evidence it cites.

The check is deterministic and dependency-free so it behaves identically whether or
not the LLM is enabled:

- numeric grounding: every number that appears in the claim must also appear in the
  cited evidence text. A number in a conclusion that no source supports is the classic
  hallucinated statistic, so this is treated as a hard failure.
- lexical grounding: the share of meaningful claim tokens that appear in the cited
  evidence. Low overlap is reported as a weak (soft) signal but does not gate.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?%?")
_TOKEN_RE = re.compile(r"[0-9a-zA-Z一-鿿]+")
# Common connective tokens that carry no grounding signal in the templated claims.
_STOPWORDS = {
    "维度",
    "证据",
    "支持",
    "主要",
    "体现",
    "存在",
    "可用于",
    "判断",
    "分析",
    "结论",
    "表现",
    "方面",
    "相关",
}

# Below this share of grounded tokens a claim is flagged as weakly grounded (soft).
WEAK_GROUNDING_THRESHOLD = 0.3


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value)


def _evidence_text(evidence: Dict[str, Any]) -> str:
    parts = [
        evidence.get("raw_content"),
        evidence.get("content"),
        evidence.get("claim"),
        evidence.get("summary"),
        evidence.get("platform"),
        evidence.get("related_dimension") or evidence.get("dimension"),
    ]
    return " ".join(_as_text(part) for part in parts if part)


def _tokens(text: str) -> List[str]:
    return [
        token
        for token in _TOKEN_RE.findall(text or "")
        if len(token) >= 2 and token not in _STOPWORDS
    ]


def _normalize_number(token: str) -> str:
    return token.replace(",", "").replace("%", "")


def _numbers(text: str) -> set[str]:
    """All normalized numbers in a text (any length), used as the grounding pool."""
    return {_normalize_number(match) for match in _NUMBER_RE.findall(text or "")}


def _significant_numbers(text: str) -> set[str]:
    """Numbers worth checking for hallucination.

    Single-digit tokens are excluded: they are dominated by version numbers ("V3") and
    truncation artifacts (a "近12个月" cut to "近1" by a claim builder), not by the kind
    of fabricated statistic this check targets.
    """
    numbers: set[str] = set()
    for match in _NUMBER_RE.findall(text or ""):
        normalized = _normalize_number(match)
        if len(normalized.replace(".", "")) >= 2:
            numbers.add(normalized)
    return numbers


def _number_supported(claim_number: str, evidence_numbers: set[str]) -> bool:
    # Exact match, or a containment match that tolerates either side being truncated.
    return any(
        claim_number == evidence_number
        or claim_number in evidence_number
        or evidence_number in claim_number
        for evidence_number in evidence_numbers
    )


def _evidence_by_id(evidence_list: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {
        _as_text(evidence.get("evidence_id")): evidence
        for evidence in evidence_list
        if isinstance(evidence, dict) and evidence.get("evidence_id")
    }


def check_claim(claim: Dict[str, Any], evidence_by_id: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Return a faithfulness verdict for a single claim against its cited evidence."""
    content = _as_text(claim.get("content"))
    cited_ids = [_as_text(item) for item in claim.get("evidence_ids", []) if _as_text(item)]
    cited_text = " ".join(
        _evidence_text(evidence_by_id[evidence_id])
        for evidence_id in cited_ids
        if evidence_id in evidence_by_id
    )

    result: Dict[str, Any] = {
        "claim_id": _as_text(claim.get("claim_id")),
        "supported": True,
        "weak": False,
        "grounding_score": 0.0,
        "reason": "grounded",
    }

    if not cited_text.strip():
        result.update(supported=False, reason="no_cited_evidence_text")
        return result

    claim_tokens = _tokens(content)
    evidence_tokens = set(_tokens(cited_text))
    overlap = (
        sum(1 for token in claim_tokens if token in evidence_tokens) / len(claim_tokens)
        if claim_tokens
        else 0.0
    )
    result["grounding_score"] = round(overlap, 2)

    evidence_numbers = _numbers(cited_text)
    missing_numbers = sorted(
        number
        for number in _significant_numbers(content)
        if not _number_supported(number, evidence_numbers)
    )
    if missing_numbers:
        result.update(
            supported=False,
            reason="unsupported_numbers:" + ",".join(missing_numbers),
            missing_numbers=missing_numbers,
        )
        return result

    # 价格类结论（绑定 realtime_price 证据）：弱支撑与否只看证据可信度，不走词面覆盖
    # （定性中文结论 vs 英文价格 JSON，词面覆盖天然低，会误判）。被反爬拦截 / 仅低可信
    # 来源的价格证据 -> 弱支撑；官方店高可信 -> 支撑。按事实。
    cited_evidence = [evidence_by_id[evidence_id] for evidence_id in cited_ids if evidence_id in evidence_by_id]
    is_price_claim = any(
        _as_text(ev.get("source_type")).lower().startswith("price")
        or _as_text(ev.get("related_dimension")).lower() == "realtime_price"
        for ev in cited_evidence
    )
    if is_price_claim:
        weak_evidence = all(
            _as_text(ev.get("credibility")).lower() == "low"
            or _as_text(ev.get("data_status")).lower() == "weak_support"
            for ev in cited_evidence
        )
        result["weak"] = bool(weak_evidence)
        result["reason"] = "low_credibility_evidence" if weak_evidence else "grounded"
        return result

    # 人工反馈类结论：人工输入会自引用同一段文字（claim 文本即 evidence 文本），词面
    # grounding 天然必过。不能因为"自己引用自己"就当成已核实事实——只有当还有至少一条
    # 非人工证据同向支撑时，才可能算支撑；否则一律降为"弱支撑 / 待验证"，按人工线索披露。
    def _is_human_evidence(ev: Dict[str, Any]) -> bool:
        return bool(ev.get("human_provided")) or _as_text(ev.get("source_type")).lower().startswith("human")

    is_human_claim = (
        any(_is_human_evidence(ev) for ev in cited_evidence)
        or bool(claim.get("needs_verification"))
        or _as_text(claim.get("generated_by")).lower() == "humanfeedback"
    )
    if is_human_claim:
        has_external_support = any(not _is_human_evidence(ev) for ev in cited_evidence)
        if not has_external_support:
            result.update(supported=False, weak=True, reason="human_feedback_unverified")
            return result

    if overlap < WEAK_GROUNDING_THRESHOLD:
        result["weak"] = True
        result["reason"] = "weak_lexical_grounding"

    return result


def verify_claims(
    claims: List[Dict[str, Any]],
    evidence_list: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Verify all claims and return a structured faithfulness report.

    A claim is *unsupported* (hard failure, excluded from the final report and used to
    gate quality) only on hard signals - missing cited evidence text or numbers that no
    cited source contains. Low lexical overlap is surfaced as *weak* but not gated, to
    avoid rejecting legitimately paraphrased conclusions.
    """
    evidence_by_id = _evidence_by_id(evidence_list)
    claim_results: List[Dict[str, Any]] = []
    unsupported_claim_ids: List[str] = []
    weak_claim_ids: List[str] = []

    for claim in claims:
        if not isinstance(claim, dict):
            continue
        verdict = check_claim(claim, evidence_by_id)
        claim_results.append(verdict)
        claim_id = verdict.get("claim_id")
        if not verdict["supported"] and claim_id:
            unsupported_claim_ids.append(claim_id)
        elif verdict["weak"] and claim_id:
            weak_claim_ids.append(claim_id)

    total = len(claim_results)
    supported = total - len(unsupported_claim_ids)
    faithfulness_rate = round(supported / total, 4) if total else 1.0

    return {
        "checked_claim_count": total,
        "supported_claim_count": supported,
        "unsupported_claim_count": len(unsupported_claim_ids),
        "weak_claim_count": len(weak_claim_ids),
        "faithfulness_rate": faithfulness_rate,
        "unsupported_claim_ids": unsupported_claim_ids,
        "weak_claim_ids": weak_claim_ids,
        "claim_results": claim_results,
    }
