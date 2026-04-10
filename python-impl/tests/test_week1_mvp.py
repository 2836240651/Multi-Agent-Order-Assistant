from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from api.main import app


class WeekFlowTests(unittest.TestCase):
    def test_order_query_uses_selected_order_context(self):
        with TestClient(app) as client:
            client.post("/api/demo/reset")
            resp = client.post(
                "/api/chat",
                json={
                    "message": "帮我查一下这个订单",
                    "user_id": "anonymous",
                    "order_id": "ORD-20260113-0001",
                    "rollout_variant": "baseline_v1",
                },
            )
            self.assertEqual(resp.status_code, 200)
            body = resp.json()
            self.assertEqual(body["execution_status"], "executed")
            self.assertEqual(body["action"], "order_query")
            self.assertEqual(body["workflow"]["code"], "ORDER_FOUND")

    def test_refund_success_splits_execution_and_ticket_status(self):
        with TestClient(app) as client:
            client.post("/api/demo/reset")
            resp = client.post(
                "/api/chat",
                json={
                    "message": "我要退款，订单 ORD-20260206-0013，因为不想要了",
                    "user_id": "anonymous",
                    "rollout_variant": "current_v3",
                },
            )
            self.assertEqual(resp.status_code, 200)
            body = resp.json()
            self.assertEqual(body["action"], "refund_apply")
            self.assertEqual(body["execution_status"], "submitted")
            self.assertEqual(body["ticket_status"], "pending_review")
            self.assertFalse(body["risk"]["requires_manual_review"])
            self.assertIsNotNone(body["workflow"])

            tickets = client.get("/api/tickets", params={"user_id": "anonymous", "order_id": "ORD-20260206-0013"})
            self.assertEqual(tickets.status_code, 200)
            items = tickets.json()["items"]
            self.assertTrue(any(item["ticket_status"] == "pending_review" for item in items))

    def test_address_change_waits_for_user_confirmation(self):
        with TestClient(app) as client:
            client.post("/api/demo/reset")
            resp = client.post(
                "/api/chat",
                json={
                    "message": "帮我修改这个订单的地址",
                    "user_id": "anonymous",
                    "order_id": "ORD-20260324-0018",
                    "rollout_variant": "current_v3",
                },
            )
            self.assertEqual(resp.status_code, 200)
            body = resp.json()
            self.assertEqual(body["action"], "order_update_address")
            self.assertEqual(body["execution_status"], "waiting_user_input")
            self.assertEqual(body["ticket_status"], "pending_user_confirm")

    def test_high_risk_refund_requires_manual_review_with_ticket_status(self):
        with TestClient(app) as client:
            client.post("/api/demo/reset")
            resp = client.post(
                "/api/chat",
                json={
                    "message": "我要申请退款，订单号 ORD-20260402-0002，因为不想要了",
                    "user_id": "anonymous",
                    "rollout_variant": "current_v3",
                },
            )
            self.assertEqual(resp.status_code, 200)
            body = resp.json()
            self.assertTrue(body["risk"]["requires_manual_review"])
            self.assertEqual(body["execution_status"], "waiting_manual_review")
            self.assertEqual(body["ticket_status"], "pending_manual_review")
            self.assertEqual(body["workflow"]["code"], "REVIEW_REQUIRED")

            pending = client.get("/api/reviews/pending")
            self.assertEqual(pending.status_code, 200)
            items = pending.json()["items"]
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["action"], "refund_apply")

    def test_manual_review_approval_keeps_ticket_flow_closed_loop(self):
        with TestClient(app) as client:
            client.post("/api/demo/reset")
            initial = client.post(
                "/api/chat",
                json={
                    "message": "我要申请退款，订单号 ORD-20260404-0004，因为不想要了",
                    "user_id": "anonymous",
                    "rollout_variant": "current_v3",
                },
            )
            self.assertEqual(initial.status_code, 200)
            initial_body = initial.json()
            review_id = initial_body["risk"]["review_id"]
            ticket_id = initial_body["ticket_id"]

            approved = client.post(
                f"/api/reviews/{review_id}/approve",
                json={"reviewer_note": "Approved for demo."},
            )
            self.assertEqual(approved.status_code, 200)
            workflow = approved.json()["workflow"]
            self.assertEqual(workflow["action"], "refund_apply")
            self.assertEqual(workflow["execution_status"], "submitted")
            self.assertEqual(workflow["ticket_status"], "pending_review")

            ticket = client.get(f"/api/tickets/{ticket_id}", params={"user_id": "anonymous"})
            self.assertEqual(ticket.status_code, 200)
            self.assertEqual(ticket.json()["ticket_status"], "pending_review")

    def test_user_can_close_resolved_ticket(self):
        with TestClient(app) as client:
            client.post("/api/demo/reset")
            response = client.post(
                "/api/chat",
                json={
                    "message": "帮我修改地址，订单 ORD-20260130-0019 地址: Shanghai Minhang District 99",
                    "user_id": "anonymous",
                    "rollout_variant": "current_v3",
                },
            )
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["execution_status"], "executed")
            self.assertEqual(body["ticket_status"], "resolved")

            ticket_id = body["ticket_id"]
            closed = client.post(
                f"/api/tickets/{ticket_id}/transition",
                params={"user_id": "anonymous"},
                json={"status": "closed", "note": "Customer confirmed completion."},
            )
            self.assertEqual(closed.status_code, 200)
            self.assertEqual(closed.json()["ticket_status"], "closed")


if __name__ == "__main__":
    unittest.main()
