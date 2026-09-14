from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


def _configure_tracing() -> None:
    """默认关闭 LangSmith tracing，避免无网络/无效 key 时的报错噪音。

    需要时通过 ENABLE_LANGSMITH=true 打开（保留 .env 里的 LANGCHAIN_* 配置）。
    必须在导入 workflow（langchain）之前执行；先 load .env 再按需覆盖，
    后续 agent 内的 load_dotenv(override=False) 不会再覆盖这里已设的值。
    """
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    load_dotenv()
    enabled = os.getenv("ENABLE_LANGSMITH", "").strip().lower() in {"1", "true", "yes", "on"}
    if not enabled:
        for var in ("LANGCHAIN_TRACING_V2", "LANGCHAIN_TRACING", "LANGSMITH_TRACING"):
            os.environ[var] = "false"
        # 移除 key，避免后台上传 trace 时打印鉴权失败噪音
        for var in ("LANGCHAIN_API_KEY", "LANGSMITH_API_KEY"):
            os.environ.pop(var, None)


_configure_tracing()

from orchestration.industry_config import INDUSTRY_CONFIGS, get_state_dimensions, get_state_industry_name
from orchestration.workflow import app as workflow_app
from app.agents.quality_agent import quality_agent
from app.agents.report_agent import report_agent
from app.agents.verification_agent import verification_agent
from app.services.error_log_service import normalize_error_log
from app.services.observability_service import (
    build_observability_payload,
    make_langsmith_run_collector,
    resolve_langsmith_trace,
)
from app.services.swot_ai_service import build_human_feedback_patch, generate_swot_interpretation


app = FastAPI(title="竞品分析 Agent 系统", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# 认证模块（独立、最小侵入）。即便认证依赖缺失也不影响分析主流程。
try:
    from auth.router import router as auth_router

    app.include_router(auth_router)

    @app.on_event("startup")
    def _init_auth() -> None:
        try:
            from auth.service import ensure_initialized

            ensure_initialized()
        except Exception:
            # 数据库未就绪时不阻塞主系统启动，登录时再返回明确错误。
            pass
except Exception:  # pragma: no cover - 认证可选，失败不影响分析接口
    pass

# 产品规格事实底座只读接口（搜索/列表/详情/对比）。与分析主流程解耦，仅新增、不改 workflow。
from api.product_routes import router as product_router

app.include_router(product_router)

TASKS: Dict[str, Dict[str, Any]] = {}
TASK_LOCK = threading.Lock()

AGENT_PROGRESS = {
    "ResearchAgent": 12,
    "CollectorAgent": 28,
    "EvidenceAgent": 42,
    "AnalysisAgent": 62,
    "VerificationAgent": 76,
    "QualityAgent": 88,
    "ReportAgent": 100,
}

NEXT_AGENT_AFTER_NODE = {
    "research_agent": "CollectorAgent",
    "collector_agent": "EvidenceAgent",
    "evidence_agent": "AnalysisAgent",
    "analysis_agent": "VerificationAgent",
    "verification_agent": "QualityAgent",
    "report_agent": "ReportAgent",
    "human_review": "ReportAgent",
}

QUALITY_REPAIR_AGENTS = {
    "ResearchAgent",
    "CollectorAgent",
    "EvidenceAgent",
    "AnalysisAgent",
}


class AnalysisRequest(BaseModel):
    industry_key: str
    target_platform: str
    competitors: List[str]
    analysis_scene: str
    target_user: str
    time_range: str
    focus_dimensions: List[str]
    # 产品对比页带入的两个产品（{id, model, brand, category}）。可选，兼容旧入口。
    selected_products: Optional[List[Dict[str, Any]]] = None


class HumanFeedbackRequest(BaseModel):
    message: str
    product: Optional[str] = ""
    dimension: Optional[str] = ""


def _product_input_names(request: AnalysisRequest) -> List[str]:
    names: List[str] = []
    for value in [request.target_platform, *request.competitors]:
        text = str(value or "").strip()
        if text and text not in names:
            names.append(text)
    return names[:2]


def _build_initial_state(request: AnalysisRequest) -> Dict[str, Any]:
    state = request.model_dump()
    selected_inputs = state.pop("selected_products", None) or []
    product_input_names = _product_input_names(request)
    state["industry_name"] = get_state_industry_name(state)
    state["focus_dimensions"] = get_state_dimensions(state)

    compare_mode = bool(selected_inputs) or (
        request.industry_key == "gaming_mouse" and len(product_input_names) >= 2
    )

    state.update(
        {
            "product_compare_mode": compare_mode,
            "selected_products": selected_inputs,
            "original_product_inputs": selected_inputs or product_input_names,
            "resolved_products": [],
            "unresolved_products": [],
            "search_mcp_results": [],
            "external_product_candidates": [],
            "product_facts": [],
            "official_spec_records": [],
            "data_requirements": [],
            "official_spec_status": [],
            "review_intel_records": [],
            "review_intel_status": {},
            "price_records": [],
            "price_status": {},
            "hardware_analysis": {},
            "experience_analysis": {},
            "business_analysis": {},
            "analysis_ai_interpretation": {},
            "human_feedback": [],
            "llm_usage": [],
            "mcp_usage": [],
            "agent_contributions": [],
            "pending_data": [],
            "pending_dimensions": [],
            "score_flow": {},
            "raw_research": [],
            "evidence_list": [],
            "evidence_status": {},
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
            "degraded_report": False,
            "quality_status": "",
            "error_log": [],
        }
    )
    return state


def _get_task(task_id: str) -> Dict[str, Any]:
    task = TASKS.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task_id 不存在")
    return task


def _get_task_state(task_id: str) -> Dict[str, Any]:
    with TASK_LOCK:
        task = _get_task(task_id).copy()
        return dict(task.get("state", {}))


def _append_system_trace(state: Dict[str, Any], *, agent_name: str, output_summary: str) -> None:
    trace_log = state.setdefault("trace_log", [])
    trace_log.append(
        {
            "step_id": len(trace_log) + 1,
            "agent_name": agent_name,
            "status": "success",
            "output_summary": output_summary,
            "error": None,
        }
    )


def _task_progress(task: Dict[str, Any]) -> int:
    if task.get("status") == "completed":
        return 100
    current_agent = task.get("current_agent", "")
    return AGENT_PROGRESS.get(current_agent, 0)


def _next_running_agent(node_name: str, state: Dict[str, Any]) -> str:
    if node_name != "quality_agent":
        return NEXT_AGENT_AFTER_NODE.get(node_name, state.get("current_agent", ""))

    quality_result = state.get("quality_result", {}) or {}
    quality_status = str(quality_result.get("status") or state.get("quality_status") or "")
    if (
        quality_status in {"approved", "approved_with_limitations", "partial_report"}
        or state.get("degraded_report")
        or state.get("is_approved")
    ):
        return "ReportAgent"

    reject_to = str(quality_result.get("reject_to") or quality_result.get("target_agent") or "")
    if reject_to in QUALITY_REPAIR_AGENTS:
        return reject_to
    return "EvidenceAgent"


def _run_workflow(task_id: str, initial_state: Dict[str, Any]) -> None:
    try:
        final_state = dict(initial_state)
        langsmith_collector = make_langsmith_run_collector()
        workflow_config: Dict[str, Any] = {"recursion_limit": 50}
        if langsmith_collector is not None:
            workflow_config["callbacks"] = [langsmith_collector]
        with TASK_LOCK:
            TASKS[task_id]["current_agent"] = "ResearchAgent"

        for event in workflow_app.stream(
            initial_state,
            workflow_config,
            stream_mode="updates",
        ):
            for node_name, update in event.items():
                if not isinstance(update, dict):
                    continue
                final_state.update(update)
                current_agent = update.get("current_agent")
                with TASK_LOCK:
                    TASKS[task_id]["state"] = dict(final_state)
                    next_agent = _next_running_agent(node_name, final_state)
                    if next_agent:
                        TASKS[task_id]["current_agent"] = next_agent
                    elif current_agent:
                        TASKS[task_id]["current_agent"] = current_agent

        current_agent = final_state.get("current_agent", "ReportAgent")
        langsmith_info = resolve_langsmith_trace(langsmith_collector)
        if langsmith_info.get("trace_url"):
            final_state["langsmith_trace_url"] = langsmith_info["trace_url"]
        final_state["langsmith"] = langsmith_info

        with TASK_LOCK:
            TASKS[task_id].update(
                {
                    "status": "completed",
                    "current_agent": current_agent,
                    "state": final_state,
                    "error": "",
                }
            )
    except Exception as exc:
        with TASK_LOCK:
            task = TASKS.get(task_id)
            if task is not None:
                task.update(
                    {
                        "status": "failed",
                        "state": {**initial_state, **task.get("state", {})},
                        "error": str(exc),
                    }
                )


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/industries")
async def get_industries():
    industries = [
        {
            "key": key,
            "industry_key": key,
            "name": config.get("name", ""),
            "competitors": config.get("competitors", []),
            "representative_products": config.get("representative_products", {}),
            "dimensions": config.get("dimensions", []),
            "description": config.get("description", ""),
            "data_sources": config.get("data_sources", {}),
            "schema_id": config.get("schema_id", ""),
            "schema_model": config.get("schema_model", ""),
            "schema_fields": config.get("schema_fields", []),
        }
        for key, config in INDUSTRY_CONFIGS.items()
    ]
    return {"industries": industries}


@app.post("/api/analysis/start")
async def start_analysis(request: AnalysisRequest):
    task_id = str(uuid4())
    initial_state = _build_initial_state(request)

    with TASK_LOCK:
        TASKS[task_id] = {
            "status": "running",
            "current_agent": "",
            "state": initial_state,
            "error": "",
        }

    thread = threading.Thread(target=_run_workflow, args=(task_id, initial_state), daemon=True)
    thread.start()

    return {"task_id": task_id, "status": "running"}


@app.get("/api/analysis/{task_id}/status")
async def get_status(task_id: str):
    with TASK_LOCK:
        task = _get_task(task_id).copy()
        state = dict(task.get("state", {}))

    return {
        "task_id": task_id,
        "status": task.get("status", "failed"),
        "current_agent": task.get("current_agent", ""),
        "progress": _task_progress(task),
        "quality_status": state.get("quality_status", ""),
        "degraded_report": state.get("degraded_report", False),
        "needs_human_review": state.get("needs_human_review", False),
        "error": task.get("error", ""),
    }


@app.get("/api/analysis/{task_id}/report")
async def get_report(task_id: str):
    with TASK_LOCK:
        task = _get_task(task_id).copy()
        state = dict(task.get("state", {}))

    return {
        "task_id": task_id,
        "status": task.get("status", "failed"),
        "final_report": state.get("final_report", {}),
        "quality_result": state.get("quality_result", {}),
        "quality_status": state.get("quality_status", ""),
        "degraded_report": state.get("degraded_report", False),
        "needs_human_review": state.get("needs_human_review", False),
        "review_ticket": state.get("review_ticket", {}),
        "evidence_list": state.get("evidence_list", []),
        # CollectorAgent 的实体识别明细（命中来源 / 别名警告 / 消歧说明），供前端 Collector 详情页展示。
        "resolved_products": state.get("resolved_products", []),
        # 未命中本地库的原始输入（非该品类 / 新品等），供前端展示待 MCP 识别项。
        "unresolved_products": state.get("unresolved_products", []),
        "search_mcp_results": state.get("search_mcp_results", []),
        "external_product_candidates": state.get("external_product_candidates", []),
        "official_spec_records": state.get("official_spec_records", []),
        "review_intel_records": state.get("review_intel_records", []),
        "review_intel_status": state.get("review_intel_status", {}),
        "price_status": state.get("price_status", {}),
        "price_records": state.get("price_records", []),
        "analysis_ai_interpretation": state.get("analysis_ai_interpretation", {}),
        "human_feedback": state.get("human_feedback", []),
        "error": task.get("error", ""),
    }


@app.get("/api/analysis/{task_id}/swot")
async def get_swot_interpretation(task_id: str):
    with TASK_LOCK:
        task = _get_task(task_id)
        state = dict(task.get("state", {}))
        current = state.get("analysis_ai_interpretation", {})
        if isinstance(current, dict) and current:
            return {
                "task_id": task_id,
                "analysis_ai_interpretation": current,
                "human_feedback": state.get("human_feedback", []),
            }

    working_state = dict(state)
    interpretation = generate_swot_interpretation(working_state)
    with TASK_LOCK:
        task = _get_task(task_id)
        next_state = dict(task.get("state", {}))
        next_state["llm_usage"] = working_state.get("llm_usage", next_state.get("llm_usage", []))
        next_state["mcp_usage"] = working_state.get("mcp_usage", next_state.get("mcp_usage", []))
        next_state["analysis_ai_interpretation"] = interpretation
        final_report = dict(next_state.get("final_report", {})) if isinstance(next_state.get("final_report"), dict) else {}
        if final_report:
            final_report["analysis_ai_interpretation"] = interpretation
            next_state["final_report"] = final_report
        context_summary = dict(next_state.get("context_summary", {})) if isinstance(next_state.get("context_summary"), dict) else {}
        context_summary["AnalysisAgent.SWOT"] = interpretation.get("context_summary", {})
        next_state["context_summary"] = context_summary
        _append_system_trace(
            next_state,
            agent_name="AnalysisAgent",
            output_summary="generated SWOT AI interpretation from structured evidence",
        )
        task["state"] = next_state
    return {
        "task_id": task_id,
        "analysis_ai_interpretation": interpretation,
        "human_feedback": next_state.get("human_feedback", []),
    }


@app.get("/api/analysis/{task_id}/observability")
async def get_observability(task_id: str):
    with TASK_LOCK:
        task = _get_task(task_id).copy()
        state = dict(task.get("state", {}))

    return build_observability_payload(
        task_id,
        state,
        task_status=task.get("status", "failed"),
        current_agent=task.get("current_agent", "") or state.get("current_agent", ""),
    )


@app.post("/api/analysis/{task_id}/feedback")
async def submit_human_feedback(task_id: str, request: HumanFeedbackRequest):
    try:
        with TASK_LOCK:
            task = _get_task(task_id)
            state = dict(task.get("state", {}))

        patch = build_human_feedback_patch(
            state,
            request.message,
            product=request.product or "",
            dimension=request.dimension or "",
        )
        next_state = {
            **state,
            "human_feedback": patch["human_feedback"],
            "evidence_list": patch["evidence_list"],
            "claims": patch["claims"],
        }
        _append_system_trace(
            next_state,
            agent_name="HumanFeedback",
            output_summary=f"accepted human feedback {patch['feedback_record']['feedback_id']} and converted it into evidence",
        )

        # Re-run the deterministic post-analysis checks so Verification/Report pages
        # immediately reflect the human correction without re-crawling or re-running
        # the full LangGraph DAG.
        verified_state = verification_agent(next_state)
        quality_state = quality_agent(verified_state)
        # Mirror the DAG forward path: verification -> quality -> SWOT -> report, so the
        # refreshed report embeds the regenerated (evidence-validated) SWOT interpretation.
        refreshed_interpretation = generate_swot_interpretation(quality_state)
        quality_state["analysis_ai_interpretation"] = refreshed_interpretation
        refreshed_state = report_agent(quality_state)
        feedback_claim_id = patch["claim"].get("claim_id") if isinstance(patch.get("claim"), dict) else ""
        unsupported_claims = {
            str(item)
            for item in (refreshed_state.get("unsupported_claim_ids", []) or [])
            if str(item)
        }
        feedback_supported = bool(feedback_claim_id) and feedback_claim_id not in unsupported_claims
        feedback_status = "verified" if feedback_supported else "needs_external_evidence"
        refreshed_feedback = []
        for item in refreshed_state.get("human_feedback", []):
            if isinstance(item, dict) and item.get("feedback_id") == patch["feedback_record"]["feedback_id"]:
                refreshed_feedback.append(
                    {
                        **item,
                        "status": feedback_status,
                        "needs_verification": not feedback_supported,
                        "verification_note": (
                            "External evidence supports this feedback."
                            if feedback_supported
                            else "No non-human evidence supports this feedback yet; CollectorAgent should gather corroborating sources."
                        ),
                    }
                )
            else:
                refreshed_feedback.append(item)
        refreshed_state["human_feedback"] = refreshed_feedback
        refreshed_state["analysis_ai_interpretation"] = refreshed_interpretation
        final_report = dict(refreshed_state.get("final_report", {})) if isinstance(refreshed_state.get("final_report"), dict) else {}
        final_report["human_feedback"] = refreshed_state.get("human_feedback", [])
        final_report["human_feedback_note"] = (
            "人工补充已作为 evidence 进入校验链路；未被外部证据进一步支撑前，按人工输入披露，不直接当作最终事实。"
        )
        final_report["analysis_ai_interpretation"] = refreshed_interpretation
        refreshed_state["final_report"] = final_report

        with TASK_LOCK:
            task = _get_task(task_id)
            task["state"] = refreshed_state
            task["current_agent"] = "ReportAgent"
            if task.get("status") != "failed":
                task["status"] = "completed"

        return {
            "task_id": task_id,
            "assistant_reply": patch["assistant_reply"],
            "feedback_record": next(
                (
                    item
                    for item in refreshed_state.get("human_feedback", [])
                    if isinstance(item, dict) and item.get("feedback_id") == patch["feedback_record"]["feedback_id"]
                ),
                patch["feedback_record"],
            ),
            "evidence": patch["evidence"],
            "claim": patch["claim"],
            "human_feedback": refreshed_state.get("human_feedback", []),
            "analysis_ai_interpretation": refreshed_interpretation,
            "final_report": final_report,
            "faithfulness_report": refreshed_state.get("faithfulness_report", {}),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/analysis/{task_id}/evidence")
async def get_evidence(task_id: str):
    state = _get_task_state(task_id)
    return {
        "task_id": task_id,
        "evidence_list": state.get("evidence_list", []),
    }


@app.get("/api/analysis/{task_id}/claims")
async def get_claims(task_id: str):
    state = _get_task_state(task_id)
    return {
        "task_id": task_id,
        "claims": state.get("claims", []),
    }


@app.get("/api/analysis/{task_id}/trace")
async def get_trace(task_id: str):
    state = _get_task_state(task_id)
    return {
        "task_id": task_id,
        "trace_log": state.get("trace_log", []),
        "context_summary": state.get("context_summary", {}),
        "error_log": normalize_error_log(state.get("error_log", [])),
        "review_ticket": state.get("review_ticket", {}),
    }


@app.get("/api/analysis/{task_id}/quality")
async def get_quality(task_id: str):
    state = _get_task_state(task_id)
    return {
        "task_id": task_id,
        "quality_result": state.get("quality_result", {}),
        "is_approved": state.get("is_approved", False),
        "iteration_count": state.get("iteration_count", 0),
        "rejected_agents": state.get("rejected_agents", []),
        "needs_human_review": state.get("needs_human_review", False),
        "degraded_report": state.get("degraded_report", False),
        "quality_status": state.get("quality_status", ""),
        "review_ticket": state.get("review_ticket", {}),
    }


@app.get("/api/analysis/{task_id}/errors")
async def get_errors(task_id: str):
    state = _get_task_state(task_id)
    errors = normalize_error_log(state.get("error_log", []))
    return {
        "task_id": task_id,
        "error_log": errors,
        "error_count": len(errors),
    }


@app.get("/api/analysis/{task_id}/metrics")
async def get_metrics(task_id: str):
    state = _get_task_state(task_id)
    return {
        "task_id": task_id,
        "metrics": state.get("metrics", {}),
    }


@app.get("/api/analysis/{task_id}/risks")
async def get_risks(task_id: str):
    state = _get_task_state(task_id)
    return {
        "task_id": task_id,
        "risk_flags": state.get("risk_flags", []),
    }


@app.get("/api/analysis/{task_id}/faithfulness")
async def get_faithfulness(task_id: str):
    state = _get_task_state(task_id)
    return {
        "task_id": task_id,
        "faithfulness_report": state.get("faithfulness_report", {}),
        "unsupported_claim_ids": state.get("unsupported_claim_ids", []),
    }


@app.get("/api/analysis/{task_id}/review-ticket")
async def get_review_ticket(task_id: str):
    state = _get_task_state(task_id)
    return {
        "task_id": task_id,
        "review_ticket": state.get("review_ticket", {}),
        "needs_human_review": state.get("needs_human_review", False),
    }


@app.get("/api/analysis/{task_id}/artifacts")
async def get_artifacts(task_id: str):
    state = _get_task_state(task_id)
    raw_research = state.get("raw_research", [])
    evidence_list = state.get("evidence_list", [])
    claims = state.get("claims", [])
    risk_flags = state.get("risk_flags", [])
    trace_log = state.get("trace_log", [])
    context_summary = state.get("context_summary", {})
    if not isinstance(context_summary, dict):
        context_summary = {}
    errors = normalize_error_log(state.get("error_log", []))

    return {
        "task_id": task_id,
        "raw_research_count": len(raw_research) if isinstance(raw_research, list) else 0,
        "evidence_count": len(evidence_list) if isinstance(evidence_list, list) else 0,
        "claim_count": len(claims) if isinstance(claims, list) else 0,
        "risk_count": len(risk_flags) if isinstance(risk_flags, list) else 0,
        "trace_count": len(trace_log) if isinstance(trace_log, list) else 0,
        "context_agent_count": len(context_summary),
        "context_trimmed_evidence_count": sum(
            int(item.get("trimmed_evidence_count", 0) or 0)
            for item in context_summary.values()
            if isinstance(item, dict)
        ),
        "error_count": len(errors),
        "has_review_ticket": bool(state.get("review_ticket", {})),
        "has_product_matrix": bool(state.get("product_matrix", {})),
        "has_business_matrix": bool(state.get("business_matrix", {})),
        "has_final_report": bool(state.get("final_report", {})),
    }
