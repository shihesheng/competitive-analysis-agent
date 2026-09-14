"""初始化认证数据库并写入默认管理员。

用法（在 backend 目录下）：
    python -m auth.seed

读取 backend/.env 中的数据库配置；未配置 MySQL 时回退本地 SQLite。
"""
from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv


def main() -> None:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    load_dotenv()

    from . import config, service

    service.ensure_initialized()

    target = "SQLite 兜底库" if config.using_sqlite_fallback() else "MySQL"
    user = service.get_user_by_username(config.DEFAULT_ADMIN_USERNAME)
    print(f"[auth.seed] 初始化完成，使用 {target}")
    if user:
        print(
            f"[auth.seed] 默认账号已就绪：username={user['username']} "
            f"role={user['role']} id={user['id']}"
        )
    print(f"[auth.seed] 默认密码：{config.DEFAULT_ADMIN_PASSWORD}（请在生产环境修改）")


if __name__ == "__main__":
    main()
