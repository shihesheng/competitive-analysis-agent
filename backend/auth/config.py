"""认证模块配置：从环境变量读取数据库与 JWT 配置，不在代码中写死密码。"""
from __future__ import annotations

import os
from pathlib import Path


def _get(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return value if value is not None else default


# 默认管理员（仅用于首次初始化 seed，可通过环境变量覆盖）。
DEFAULT_ADMIN_USERNAME = _get("DEFAULT_ADMIN_USERNAME", "admin")
DEFAULT_ADMIN_PASSWORD = _get("DEFAULT_ADMIN_PASSWORD", "123456")
DEFAULT_ADMIN_ROLE = _get("DEFAULT_ADMIN_ROLE", "admin")

# JWT 配置
JWT_SECRET = _get(
    "JWT_SECRET", "dev-only-change-this-jwt-secret-please-override-32chars"
)
JWT_ALGORITHM = _get("JWT_ALGORITHM", "HS256")
try:
    JWT_EXPIRE_MINUTES = int(_get("JWT_EXPIRE_MINUTES", "1440"))
except ValueError:
    JWT_EXPIRE_MINUTES = 1440


def build_db_url() -> str:
    """构造数据库连接串。

    优先级：
    1. 显式 AUTH_DB_URL
    2. 配置了 MYSQL_DATABASE -> 使用 MySQL (pymysql)
    3. 兜底使用本地 SQLite 文件，保证零配置也能登录演示
    """
    explicit = os.getenv("AUTH_DB_URL")
    if explicit:
        return explicit

    mysql_db = os.getenv("MYSQL_DATABASE")
    if mysql_db:
        host = _get("MYSQL_HOST", "localhost")
        port = _get("MYSQL_PORT", "3306")
        user = _get("MYSQL_USER", "root")
        password = _get("MYSQL_PASSWORD", "")
        return f"mysql+pymysql://{user}:{password}@{host}:{port}/{mysql_db}?charset=utf8mb4"

    # 兜底：本地 SQLite，文件放在 backend/auth/auth.db
    sqlite_path = Path(__file__).resolve().parent / "auth.db"
    return f"sqlite:///{sqlite_path.as_posix()}"


def using_sqlite_fallback() -> bool:
    return build_db_url().startswith("sqlite")
