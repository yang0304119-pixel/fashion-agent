"""
用户模型

存储客服系统用户基础信息。
"""

from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func

from app.core.database import Base


class User(Base):
    __tablename__ = "user"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, comment="用户昵称")
    created_at = Column(DateTime, nullable=False, server_default=func.now(), comment="注册时间")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username={self.username})>"
