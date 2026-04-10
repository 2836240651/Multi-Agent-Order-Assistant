from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app


class Week4OpsTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.client.__enter__()
        self.client.post("/api/demo/reset")

    def tearDown(self):
        self.client.__exit__(None, None, None)

    def test_rollout_override_and_ops_metrics(self):
        response = self.client.post(
            "/api/chat",
            json={
                "message": "帮我查一下订单 ORD-20260402-002 的状态",
                "user_id": "week4-user",
                "rollout_variant": "baseline_v1",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["release"]["variant"], "baseline_v1")

        overview = self.client.get("/api/ops/overview")
        self.assertEqual(overview.status_code, 200)
        runtime = overview.json()["runtime"]
        self.assertGreaterEqual(runtime["requests"], 1)
        self.assertIn("baseline_v1", runtime["by_variant"])

    def test_rollout_update_endpoint(self):
        response = self.client.post(
            "/api/ops/rollout",
            json={"baseline_v1": 0, "optimized_v2": 0, "current_v3": 100},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["weights"]["current_v3"], 100)

    def test_root_serves_frontend_bundle_when_built(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers.get("content-type", ""))

    def test_fallback_is_used_when_primary_execution_fails(self):
        with patch("api.main._execute_variant", side_effect=RuntimeError("synthetic graph outage")):
            response = self.client.post(
                "/api/chat",
                json={
                    "message": "帮我查一下订单 ORD-20260402-002 的状态",
                    "user_id": "fallback-user",
                    "rollout_variant": "current_v3",
                },
            )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["release"]["degraded"])
        self.assertEqual(payload["workflow"]["code"], "RULE_FALLBACK_ACTIVATED")


if __name__ == "__main__":
    unittest.main()
