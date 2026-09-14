"""密码哈希（bcrypt）与 JWT 令牌的签发/校验。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt
import jwt

from . import config


def hash_password(password: str) -> str:
    """使用 bcrypt 对明文密码做哈希，返回字符串形式。"""
    salt = bcrypt.gensalt()
    digest = bcrypt.hashpw(password.encode("utf-8"), salt)
    return digest.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """校验明文密码与哈希是否匹配。"""
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"), password_hash.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False


def create_access_token(subject: Dict[str, Any]) -> str:
    """根据用户公开信息签发 JWT。"""
    now = datetime.now(timezone.utc)
    payload = {
        **subject,
        "iat": now,
        "exp": now + timedelta(minutes=config.JWT_EXPIRE_MINUTES),
    }
    token = jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)
    # PyJWT >= 2 返回 str
    return token if isinstance(token, str) else token.decode("utf-8")


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """校验并解析 JWT，失败返回 None。"""
    try:
        return jwt.decode(
            token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM]
        )
    except jwt.PyJWTError:
        return None
