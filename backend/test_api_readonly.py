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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
load_dotenv(Path(__file__).resolve().parent / ".env")

from api.routes import app


REQUEST_BODY = {
    "industry_key": "gaming_mouse",
    "target_platform": "罗技",
    "competitors": ["雷蛇", "海盗船"],
    "analysis_scene": "电竞鼠标竞品分析",
    "target_user": "产品经理",
    "time_range": "近12个月",
    "focus_dimensions": ["性能参数", "轻量化设计", "无线与续航", "软件生态", "用户口碑", "价格定位", "电竞品牌影响力", "握持手感与人体工学"],
}


if __name__ == "__main__":
    client = TestClient(app)

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

    readonly_paths = [
        "/evidence",
        "/claims",
        "/trace",
        "/quality",
        "/metrics",
        "/risks",
        "/faithfulness",
        "/errors",
        "/review-ticket",
        "/artifacts",
    ]
    for path in readonly_paths:
        response = client.get(f"/api/analysis/{task_id}{path}")
        assert response.status_code == 200, path
        payload = response.json()
        assert payload.get("task_id") == task_id, path

    missing_response = client.get("/api/analysis/not-a-real-task/evidence")
    assert missing_response.status_code == 404

    print("API readonly 测试通过")
