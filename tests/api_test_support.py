"""API端到端测试共享应用、JWT账号和隔离数据库。"""

import unittest
from decimal import Decimal
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base
from app.core.passwords import hash_password
from app.dependencies import get_db
from app.models import Order, Product, Tenant, User
from app.routers import (
    admin,
    auth,
    chat,
    demo_store,
    knowledge,
    memories,
    agentops,
    tenant_users,
    orders,
    refunds,
    tickets,
)


CUSTOMER_PASSWORD = "CustomerPassword123!"
ADMIN_PASSWORD = "AdminPassword123!"


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self._seed()

        self.original_jwt_secret = settings.JWT_SECRET_KEY
        self.original_jwt_expiry = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        settings.JWT_SECRET_KEY = (
            "api-test-secret-key-that-is-longer-than-thirty-two-characters"
        )
        settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 60

        api = FastAPI()
        api.include_router(auth.router, prefix="/api")
        api.include_router(demo_store.router, prefix="/api")
        api.include_router(chat.router, prefix="/api")
        api.include_router(orders.router, prefix="/api")
        api.include_router(tickets.router, prefix="/api")
        api.include_router(refunds.router, prefix="/api")
        api.include_router(admin.router, prefix="/api")
        api.include_router(knowledge.router, prefix="/api")
        api.include_router(memories.router, prefix="/api")
        api.include_router(memories.admin_router, prefix="/api")
        api.include_router(agentops.router, prefix="/api")
        api.include_router(tenant_users.router, prefix="/api")

        def override_db():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        api.dependency_overrides[get_db] = override_db
        self.session_patches = [
            patch("app.agent.nodes.router_node.SessionLocal", self.Session),
            patch(
                "app.agent.nodes.conversation_state_node.SessionLocal",
                self.Session,
            ),
            patch("app.agent.nodes.refund_node.SessionLocal", self.Session),
            patch("app.agent.nodes.refund_status_node.SessionLocal", self.Session),
            patch("app.providers.factory.SessionLocal", self.Session),
            patch(
                "app.rag.knowledge_index_resolver.SessionLocal",
                self.Session,
            ),
            patch("app.services.trace_service.SessionLocal", self.Session),
            patch("app.agent.nodes.memory_load_node.SessionLocal", self.Session),
            patch("app.agent.nodes.memory_retrieve_node.SessionLocal", self.Session),
            patch("app.agent.nodes.memory_commit_node.SessionLocal", self.Session),
        ]
        for session_patch in self.session_patches:
            session_patch.start()
        self.client = TestClient(api)

    def tearDown(self):
        self.client.close()
        for session_patch in reversed(self.session_patches):
            session_patch.stop()
        settings.JWT_SECRET_KEY = self.original_jwt_secret
        settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES = self.original_jwt_expiry
        self.engine.dispose()

    def login(self, username: str, password: str) -> str:
        response = self.client.post(
            "/api/auth/login",
            json={"username": username, "password": password},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["access_token"]

    @staticmethod
    def auth_headers(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def _seed(self):
        db = self.Session()
        db.add_all([
            Tenant(id=1, name="租户一", industry="服装"),
            Tenant(id=2, name="租户二", industry="服装"),
        ])
        db.flush()
        db.add_all([
            User(
                id=1,
                tenant_id=1,
                username="customer_a",
                password_hash=hash_password(CUSTOMER_PASSWORD),
                role="customer",
                is_active=True,
            ),
            User(
                id=2,
                tenant_id=1,
                username="customer_b",
                password_hash=hash_password(CUSTOMER_PASSWORD),
                role="customer",
                is_active=True,
            ),
            User(
                id=3,
                tenant_id=1,
                username="admin_a",
                password_hash=hash_password(ADMIN_PASSWORD),
                role="tenant_admin",
                is_active=True,
            ),
            User(
                id=4,
                tenant_id=2,
                username="customer_tenant_b",
                password_hash=hash_password(CUSTOMER_PASSWORD),
                role="customer",
                is_active=True,
            ),
            User(
                id=5,
                tenant_id=2,
                username="admin_b",
                password_hash=hash_password(ADMIN_PASSWORD),
                role="tenant_admin",
                is_active=True,
            ),
            User(
                id=6,
                tenant_id=1,
                username="service_a",
                password_hash=hash_password(ADMIN_PASSWORD),
                role="customer_service",
                is_active=True,
            ),
            User(
                id=7,
                tenant_id=1,
                username="supervisor_a",
                password_hash=hash_password(ADMIN_PASSWORD),
                role="supervisor",
                is_active=True,
            ),
            User(
                id=8,
                tenant_id=1,
                username="developer_a",
                password_hash=hash_password(ADMIN_PASSWORD),
                role="developer",
                is_active=True,
            ),
        ])
        db.add_all([
            Product(
                id=1,
                tenant_id=1,
                name="租户一羽绒服",
                category="羽绒服",
                price=Decimal("499.00"),
                colors=["黑色"],
                sizes=["M"],
                description="测试",
                materials="测试",
                care_instructions="测试",
                stock=20,
            ),
            Product(
                id=7,
                tenant_id=1,
                name="纯色羊毛围巾",
                category="配饰",
                price=Decimal("89.00"),
                colors=["驼色"],
                sizes=["均码"],
                description="测试",
                materials="测试",
                care_instructions="测试",
                stock=20,
            ),
            Product(
                id=20,
                tenant_id=2,
                name="租户二商品",
                category="服装",
                price=Decimal("299.00"),
                colors=["白色"],
                sizes=["L"],
                description="测试",
                materials="测试",
                care_instructions="测试",
                stock=20,
            ),
        ])
        db.flush()
        db.add_all([
            Order(
                id=10001,
                tenant_id=1,
                user_id=1,
                product_id=1,
                quantity=1,
                total_price=Decimal("499.00"),
                status="shipped",
            ),
            Order(
                id=10002,
                tenant_id=1,
                user_id=1,
                product_id=1,
                quantity=1,
                total_price=Decimal("598.00"),
                status="delivered",
            ),
            Order(
                id=10007,
                tenant_id=1,
                user_id=1,
                product_id=7,
                quantity=1,
                total_price=Decimal("89.00"),
                status="pending",
            ),
            Order(
                id=11001,
                tenant_id=1,
                user_id=2,
                product_id=1,
                quantity=1,
                total_price=Decimal("499.00"),
                status="shipped",
            ),
            Order(
                id=20001,
                tenant_id=2,
                user_id=4,
                product_id=20,
                quantity=1,
                total_price=Decimal("299.00"),
                status="shipped",
            ),
        ])
        db.commit()
        db.close()
