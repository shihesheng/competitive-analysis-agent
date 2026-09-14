"""认证业务逻辑：初始化、默认用户 seed、登录校验、按 id/用户名查询。"""
from __future__ import annotations

from typing import Optional

from . import config
from .db import init_db, session_scope
from .models import User
from .security import hash_password, verify_password

_initialized = False


def ensure_initialized() -> None:
    """确保建表，并在用户表为空时写入默认管理员（幂等）。"""
    global _initialized
    if _initialized:
        return

    init_db()
    with session_scope() as session:
        existing = (
            session.query(User)
            .filter(User.username == config.DEFAULT_ADMIN_USERNAME)
            .first()
        )
        if existing is None:
            session.add(
                User(
                    username=config.DEFAULT_ADMIN_USERNAME,
                    password_hash=hash_password(config.DEFAULT_ADMIN_PASSWORD),
                    role=config.DEFAULT_ADMIN_ROLE,
                )
            )
    _initialized = True


def authenticate(username: str, password: str) -> Optional[dict]:
    """校验账号密码，成功返回用户公开信息字典，失败返回 None。"""
    ensure_initialized()
    with session_scope() as session:
        user = session.query(User).filter(User.username == username).first()
        if user is None or not verify_password(password, user.password_hash):
            return None
        return user.to_public_dict()


def get_user_by_id(user_id: int) -> Optional[dict]:
    ensure_initialized()
    with session_scope() as session:
        user = session.query(User).filter(User.id == user_id).first()
        return user.to_public_dict() if user else None


def get_user_by_username(username: str) -> Optional[dict]:
    ensure_initialized()
    with session_scope() as session:
        user = session.query(User).filter(User.username == username).first()
        return user.to_public_dict() if user else None
