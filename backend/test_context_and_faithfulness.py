import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
load_dotenv(Path(__file__).resolve().parent / ".env")

from app.services.context_manager import select_evidence_for_prompt
from app.services.faithfulness import check_claim, verify_claims


def _evidence(evidence_id, credibility, confidence, content, dimension="性能", platform="罗技"):
    return {
        "evidence_id": evidence_id,
        "platform": platform,
        "related_dimension": dimension,
        "source_type": "official",
        "credibility": credibility,
        "confidence_score": confidence,
        "raw_content": content,
        "claim": content,
    }


def test_context_management():
    evidence_list = [
        _evidence(f"EV{i:03d}", "low", 0.4, "低可信内容" * 50, dimension="维度A")
        for i in range(1, 51)
    ]
    evidence_list.append(_evidence("EV900", "high", 0.95, "高可信关键内容", dimension="维度B"))

    selected = select_evidence_for_prompt(
        evidence_list, max_items=10, max_per_dimension=8, max_content_chars=40
    )

    assert len(selected) <= 10, "超出 max_items 上限"
    assert any(item["evidence_id"] == "EV900" for item in selected), "高可信证据应被优先保留"
    for item in selected:
        assert len(item["raw_content"]) <= 41, "raw_content 未被截断 (含省略号)"
    print("context management 测试通过")


def test_faithfulness_grounded():
    evidence_by_id = {
        "EV001": _evidence("EV001", "high", 0.9, "罗技在性能参数上拥有高精度传感器和稳定回报率"),
    }
    claim = {
        "claim_id": "PCL001",
        "content": "罗技在性能参数上拥有高精度传感器和稳定回报率",
        "evidence_ids": ["EV001"],
    }
    verdict = check_claim(claim, evidence_by_id)
    assert verdict["supported"] is True, f"grounded claim 应被判为支撑: {verdict}"
    print("faithfulness grounded 测试通过")


def test_faithfulness_hallucinated_number():
    evidence_by_id = {
        "EV001": _evidence("EV001", "high", 0.9, "罗技鼠标主打轻量化与高精度传感器"),
    }
    # The claim invents a market-share statistic that no cited evidence contains.
    claim = {
        "claim_id": "PCL002",
        "content": "罗技鼠标在轻量化市场占有率高达73%",
        "evidence_ids": ["EV001"],
    }
    verdict = check_claim(claim, evidence_by_id)
    assert verdict["supported"] is False, "包含未支撑数字的 claim 应被判为不支撑"
    assert "73" in verdict.get("reason", ""), "应指出未支撑的数字"
    print("faithfulness hallucinated-number 测试通过")


def test_verify_claims_report():
    evidence_list = [
        _evidence("EV001", "high", 0.9, "罗技鼠标主打轻量化与高精度传感器"),
    ]
    claims = [
        {"claim_id": "PCL001", "content": "罗技鼠标主打轻量化与高精度传感器", "evidence_ids": ["EV001"]},
        {"claim_id": "PCL002", "content": "罗技鼠标市场占有率高达73%", "evidence_ids": ["EV001"]},
    ]
    report = verify_claims(claims, evidence_list)
    assert report["checked_claim_count"] == 2
    assert report["unsupported_claim_count"] == 1
    assert "PCL002" in report["unsupported_claim_ids"]
    assert 0 <= report["faithfulness_rate"] <= 1
    print("verify_claims 报告 测试通过")


if __name__ == "__main__":
    test_context_management()
    test_faithfulness_grounded()
    test_faithfulness_hallucinated_number()
    test_verify_claims_report()
    print("Context & Faithfulness 测试通过")
