"""认证模块的 ORM 模型。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from .db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(32), nullable=False, default="admin")
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_public_dict(self) -> dict:
        return {"id": self.id, "username": self.username, "role": self.role}
