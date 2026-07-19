"""
用户模型

存储客服系统用户基础信息。
"""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class User(Base):
    __tablename__ = "user"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(
        Integer,
        ForeignKey("tenant.id"),
        nullable=False,
        index=True,
        comment="所属租户 ID",
    )
    username = Column(String(50), unique=True, nullable=False, comment="用户昵称")
    password_hash = Column(String(255), nullable=False, comment="PBKDF2密码哈希")
    role = Column(
        String(20),
        nullable=False,
        default="customer",
        comment="角色：customer/admin",
    )
    is_active = Column(Boolean, nullable=False, default=True, comment="账号是否启用")
    created_at = Column(DateTime, nullable=False, server_default=func.now(), comment="注册时间")

    tenant = relationship("Tenant", backref="users")

    def __repr__(self) -> str:
        return (
            f"<User(id={self.id}, tenant={self.tenant_id}, "
            f"username={self.username}, role={self.role})>"
        )
