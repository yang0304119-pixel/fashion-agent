from decimal import Decimal
from unittest.mock import patch

from app.integrations.refund_gateway import GatewayRefundResult
from app.models import Order, RefundRequest, Ticket
from tests.api_test_support import (
    ADMIN_PASSWORD,
    CUSTOMER_PASSWORD,
    ApiTestCase,
)


class CountingGateway:
    mode = "mock"

    def __init__(self, result: str):
        self.result = result
        self.calls = 0

    def execute(self, **kwargs):
        self.calls += 1
        if self.result == "succeeded":
            return GatewayRefundResult(
                status="succeeded",
                provider_refund_id=f"api-mock-{kwargs['refund_request_id']}",
            )
        if self.result == "pending":
            return GatewayRefundResult(status="pending")
        return GatewayRefundResult(status="failed", error="API模拟渠道失败")


class RefundFlowApiTests(ApiTestCase):
    def customer_headers(self):
        token = self.login("customer_a", CUSTOMER_PASSWORD)
        return self.auth_headers(token)

    def admin_headers(self):
        token = self.login("admin_a", ADMIN_PASSWORD)
        return self.auth_headers(token)

    def post_chat(self, *, session_id: str, message: str, headers: dict):
        return self.client.post(
            "/api/chat",
            headers=headers,
            json={"session_id": session_id, "message": message},
        )

    def test_low_risk_refund_executes_once_and_duplicate_returns_original(self):
        gateway = CountingGateway("succeeded")
        headers = self.customer_headers()
        with patch(
            "app.services.refund_service.get_refund_gateway",
            return_value=gateway,
        ):
            first = self.post_chat(
                session_id="low-risk-api-session",
                message="订单10007申请退款，原因是不需要了",
                headers=headers,
            )
            second = self.post_chat(
                session_id="low-risk-api-session",
                message="订单10007申请退款，原因是不需要了",
                headers=headers,
            )

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(first.json()["message_type"], "refund_status")
        self.assertEqual(first.json()["payload"]["status"], "succeeded")
        self.assertEqual(first.json()["payload"]["order_id"], 10007)
        self.assertEqual(gateway.calls, 1)

        refund = self.client.get(
            "/api/refunds/order/10007",
            headers=headers,
        )
        self.assertEqual(refund.status_code, 200)
        refund_data = refund.json()["data"]
        self.assertEqual(refund_data["status"], "succeeded")
        self.assertEqual(refund_data["provider_refund_id"], "api-mock-1")

        db = self.Session()
        self.assertEqual(
            db.query(RefundRequest).filter(RefundRequest.order_id == 10007).count(),
            1,
        )
        self.assertEqual(db.get(Order, 10007).status, "refunded")
        db.close()

    def test_high_risk_refund_requires_admin_approval(self):
        gateway = CountingGateway("succeeded")
        customer_headers = self.customer_headers()
        with patch(
            "app.services.refund_service.get_refund_gateway",
            return_value=gateway,
        ):
            submitted = self.post_chat(
                session_id="high-risk-api-session",
                message="订单10001申请退款，原因是质量问题",
                headers=customer_headers,
            )
            self.assertEqual(submitted.status_code, 200, submitted.text)

            db = self.Session()
            refund = db.query(RefundRequest).filter_by(order_id=10001).one()
            refund_id = refund.id
            ticket_id = refund.ticket_id
            self.assertEqual(refund.status, "reviewing")
            self.assertEqual(db.get(Order, 10001).status, "shipped")
            self.assertEqual(db.get(Ticket, ticket_id).status, "pending")
            db.close()
            self.assertEqual(gateway.calls, 0)

            approved = self.client.post(
                f"/api/admin/refunds/{refund_id}/approve",
                headers=self.admin_headers(),
            )

        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()["data"]["status"], "succeeded")
        self.assertEqual(gateway.calls, 1)
        db = self.Session()
        self.assertEqual(db.get(Order, 10001).status, "refunded")
        self.assertEqual(db.get(Ticket, ticket_id).status, "approved")
        db.close()

    def test_order_is_not_refunded_when_gateway_is_not_successful(self):
        gateway = CountingGateway("pending")
        headers = self.customer_headers()
        with patch(
            "app.services.refund_service.get_refund_gateway",
            return_value=gateway,
        ):
            response = self.post_chat(
                session_id="pending-gateway-api-session",
                message="订单10007申请退款，原因是不需要了",
                headers=headers,
            )

        self.assertEqual(response.status_code, 200, response.text)
        db = self.Session()
        refund = db.query(RefundRequest).filter_by(order_id=10007).one()
        self.assertEqual(refund.status, "approved")
        self.assertEqual(db.get(Order, 10007).status, "pending")
        db.close()

    def test_bare_order_id_resumes_previous_refund_intent(self):
        gateway = CountingGateway("succeeded")
        headers = self.customer_headers()
        with patch(
            "app.services.refund_service.get_refund_gateway",
            return_value=gateway,
        ):
            first = self.post_chat(
                session_id="refund-resume-api-session",
                message="我要退款",
                headers=headers,
            )
            second = self.post_chat(
                session_id="refund-resume-api-session",
                message="10007",
                headers=headers,
            )

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["intent"], "refund_request")
        self.assertIn("订单号", first.json()["answer"])
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["intent"], "refund_request")
        self.assertIn("模拟退款", second.json()["answer"])
        self.assertEqual(gateway.calls, 1)
        db = self.Session()
        self.assertEqual(db.get(Order, 10007).status, "refunded")
        db.close()
