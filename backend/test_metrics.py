import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi.testclient import TestClient


os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["RESEARCH_AGENT_USE_LLM"] = "0"
os.environ["EVIDENCE_AGENT_USE_LLM"] = "0"
os.environ["QUALITY_AGENT_USE_LLM"] = "0"
os.environ["SEARCH_PROVIDER"] = "disabled"
os.environ["OFFICIAL_SPEC_USE_LLM"] = "0"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
load_dotenv(Path(__file__).resolve().parent / ".env")

from orchestration.workflow import app as workflow_app
from api.routes import app as fastapi_app


REQUIRED_METRIC_KEYS = {
    "evidence_count",
    "claim_count",
    "citation_rate",
    "coverage_rate",
    "high_credibility_ratio",
    "low_credibility_ratio",
    "faithfulness_rate",
    "unsupported_claim_count",
    "weak_claim_count",
    "matrix_issue_count",
    "context_trimmed_evidence_count",
    "error_count",
    "has_review_ticket",
    "quality_score",
    "iteration_count",
}


REQUEST_BODY = {
    "industry_key": "gaming_mouse",
    "industry_name": "电竞鼠标",
    "target_platform": "G Pro X Superlight 2",
    "competitors": ["Viper V3 Pro"],
    "analysis_scene": "电竞鼠标竞品分析",
    "target_user": "产品经理",
    "time_range": "近12个月",
    "focus_dimensions": [
        "性能参数",
        "轻量化设计",
        "无线与续航",
        "软件生态",
        "用户口碑",
        "价格定位",
        "电竞品牌影响力",
        "握持手感与人体工学",
    ],
}


def _assert_metrics(metrics: dict) -> None:
    assert metrics, "metrics 不应为空"
    assert REQUIRED_METRIC_KEYS.issubset(metrics.keys())
    assert metrics["evidence_count"] > 0
    assert metrics["claim_count"] > 0
    assert 0 <= metrics["citation_rate"] <= 1
    assert 0 <= metrics["coverage_rate"] <= 1
    assert 0 <= metrics["high_credibility_ratio"] <= 1
    assert 0 <= metrics["low_credibility_ratio"] <= 1


if __name__ == "__main__":
    initial_state = {
        **REQUEST_BODY,
        "raw_research": [],
        "evidence_list": [],
        "official_spec_records": [],
        "claims": [],
        "product_matrix": {},
        "business_matrix": {},
        "risk_flags": [],
        "faithfulness_report": {},
        "unsupported_claim_ids": [],
        "quality_result": {},
        "final_report": {},
        "context_summary": {},
        "review_ticket": {},
        "trace_log": [],
        "metrics": {},
        "used_claim_ids": [],
        "used_evidence_ids": [],
        "current_agent": "",
        "iteration_count": 0,
        "rejected_agents": [],
        "is_approved": False,
        "needs_human_review": False,
        "quality_status": "",
        "error_log": [],
    }

    final_state = workflow_app.invoke(initial_state, {"recursion_limit": 50})
    _assert_metrics(final_state.get("metrics", {}))

    client = TestClient(fastapi_app)
    start_response = client.post("/api/analysis/start", json=REQUEST_BODY)
    assert start_response.status_code == 200
    task_id = start_response.json()["task_id"]

    status_payload = {}
    for _ in range(60):
        status_response = client.get(f"/api/analysis/{task_id}/status")
        assert status_response.status_code == 200
        status_payload = status_response.json()
        if status_payload["status"] in {"completed", "failed"}:
            break
        time.sleep(0.1)

    assert status_payload.get("status") == "completed", status_payload

    metrics_response = client.get(f"/api/analysis/{task_id}/metrics")
    assert metrics_response.status_code == 200
    metrics_payload = metrics_response.json()
    assert metrics_payload.get("task_id") == task_id
    _assert_metrics(metrics_payload.get("metrics", {}))

    print("Metrics 测试通过")
