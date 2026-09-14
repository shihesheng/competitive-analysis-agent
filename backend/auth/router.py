"""认证路由：POST /api/auth/login 与 GET /api/auth/me。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import service
from .security import create_access_token, decode_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


def _bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return None


@router.post("/login")
async def login(payload: LoginRequest):
    try:
        user = service.authenticate(payload.username, payload.password)
    except Exception:
        # 数据库不可用等情况，返回清晰错误而不是 500 堆栈
        return JSONResponse(
            status_code=503,
            content={
                "error": "AUTH_DB_UNAVAILABLE",
                "message": "认证服务暂不可用，请检查数据库配置",
            },
        )

    if user is None:
        return JSONResponse(
            status_code=401,
            content={
                "error": "INVALID_CREDENTIALS",
                "message": "账号或密码错误",
            },
        )

    token = create_access_token(
        {"uid": user["id"], "username": user["username"], "role": user["role"]}
    )
    return {"token": token, "user": user}


@router.get("/me")
async def me(authorization: Optional[str] = Header(default=None)):
    token = _bearer_token(authorization)
    payload = decode_token(token) if token else None
    if not payload:
        return JSONResponse(
            status_code=401,
            content={"error": "UNAUTHORIZED", "message": "未登录或登录已过期"},
        )

    user_id = payload.get("uid")
    user = service.get_user_by_id(int(user_id)) if user_id is not None else None
    if user is None:
        return JSONResponse(
            status_code=401,
            content={"error": "UNAUTHORIZED", "message": "用户不存在"},
        )

    return {"user": user}
