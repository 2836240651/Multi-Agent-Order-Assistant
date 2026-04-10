from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class EvalCase:
    case_id: str
    message: str
    user_id: str
    expected_action: str
    expected_status: str
    expected_code: str
    expected_manual_review: bool
    risk_bucket: str
    difficulty: str
    tags: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_week3_cases() -> list[EvalCase]:
    cases: list[EvalCase] = []

    order_templates = [
        "帮我查一下订单 {order_id} 的状态",
        "订单 {order_id} 现在到哪了",
        "请帮我看下 {order_id} 的物流",
        "order {order_id} status please",
    ]
    refund_low_templates = [
        "我要退款，订单 {order_id}，因为不想要了",
        "帮我申请退款，订单号 {order_id}，原因是不需要了",
        "refund order {order_id} because I changed my mind",
        "订单 {order_id} 想申请退款，不想买了",
    ]
    refund_high_templates = [
        "我要申请退款，订单号 {order_id}，因为不想要了",
        "请退掉订单 {order_id}，我改变主意了",
        "refund order {order_id} right now",
        "帮我处理 {order_id} 的退款申请",
    ]
    refund_fail_templates = [
        "我要退款，订单 {order_id}，因为用了两个月了",
        "订单 {order_id} 现在还能退款吗，我用了很久",
        "refund order {order_id}, I have already used it for months",
    ]
    address_success_templates = [
        "帮我修改地址，订单 {order_id} 地址: {address}",
        "我要改地址，订单 {order_id} 地址: {address}",
        "change address for order {order_id} address: {address}",
        "订单 {order_id} 收货地址改成 {address}",
    ]
    address_fail_templates = [
        "帮我修改地址，订单 {order_id} 地址: {address}",
        "订单 {order_id} 现在还能改地址吗，改成 {address}",
        "change address for order {order_id} address: {address}",
    ]
    pii_templates = [
        "我要退款，订单 {order_id}，我的手机号是 13812345678",
        "订单 {order_id} 要退款，我身份证号是 110101199003076419",
        "refund order {order_id}, my email is test_user@example.com",
    ]
    missing_order_templates = [
        "帮我查一下订单状态",
        "我要退款，但是我忘了订单号",
        "帮我改地址，我没带订单号",
    ]

    addresses = [
        "Shanghai Minhang District 99",
        "Beijing Chaoyang District 66",
        "Hangzhou Binjiang District 18",
        "Suzhou Industrial Park 9",
    ]

    index = 1

    def add_cases(
        templates: list[str],
        *,
        count: int,
        order_id: str,
        expected_action: str,
        expected_status: str,
        expected_code: str,
        expected_manual_review: bool,
        risk_bucket: str,
        difficulty: str,
        tags: list[str],
        address_required: bool = False,
    ) -> None:
        nonlocal index
        for i in range(count):
            template = templates[i % len(templates)]
            address = addresses[i % len(addresses)]
            message = template.format(order_id=order_id, address=address)
            cases.append(
                EvalCase(
                    case_id=f"case-{index:03d}",
                    message=message,
                    user_id="anonymous",
                    expected_action=expected_action,
                    expected_status=expected_status,
                    expected_code=expected_code,
                    expected_manual_review=expected_manual_review,
                    risk_bucket=risk_bucket,
                    difficulty=difficulty,
                    tags=list(tags),
                )
            )
            index += 1

    add_cases(
        order_templates,
        count=40,
        order_id="ORD-20260402-002",
        expected_action="order_query",
        expected_status="executed",
        expected_code="ORDER_FOUND",
        expected_manual_review=False,
        risk_bucket="low",
        difficulty="easy",
        tags=["order_query", "known_order"],
    )
    add_cases(
        refund_low_templates,
        count=40,
        order_id="ORD-20260401-001",
        expected_action="refund_apply",
        expected_status="pending_confirmation",
        expected_code="REFUND_REQUESTED",
        expected_manual_review=False,
        risk_bucket="medium",
        difficulty="medium",
        tags=["refund", "eligible"],
    )
    add_cases(
        refund_high_templates,
        count=40,
        order_id="ORD-20260402-002",
        expected_action="refund_apply",
        expected_status="review_required",
        expected_code="REVIEW_REQUIRED",
        expected_manual_review=True,
        risk_bucket="high",
        difficulty="hard",
        tags=["refund", "high_value"],
    )
    add_cases(
        refund_fail_templates,
        count=30,
        order_id="ORD-20260403-003",
        expected_action="refund_apply",
        expected_status="failed",
        expected_code="REFUND_NOT_ELIGIBLE",
        expected_manual_review=False,
        risk_bucket="low",
        difficulty="medium",
        tags=["refund", "policy_fail"],
    )
    add_cases(
        address_success_templates,
        count=30,
        order_id="ORD-20260402-002",
        expected_action="order_update_address",
        expected_status="executed",
        expected_code="ADDRESS_UPDATED",
        expected_manual_review=False,
        risk_bucket="low",
        difficulty="medium",
        tags=["address_change", "mutable"],
        address_required=True,
    )
    add_cases(
        address_fail_templates,
        count=20,
        order_id="ORD-20260401-001",
        expected_action="order_update_address",
        expected_status="failed",
        expected_code="ADDRESS_CHANGE_WINDOW_EXPIRED",
        expected_manual_review=False,
        risk_bucket="low",
        difficulty="medium",
        tags=["address_change", "expired"],
        address_required=True,
    )
    add_cases(
        pii_templates,
        count=10,
        order_id="ORD-20260401-001",
        expected_action="refund_apply",
        expected_status="review_required",
        expected_code="REVIEW_REQUIRED",
        expected_manual_review=True,
        risk_bucket="high",
        difficulty="hard",
        tags=["refund", "pii"],
    )

    missing_variants = [
        ("帮我查一下订单状态", "order_query", "pending_confirmation", "ORDER_ID_REQUIRED", False, "low", "easy", ["missing_id", "order_query"]),
        ("我要退款，但是我忘了订单号", "refund_apply", "pending_confirmation", "ORDER_ID_REQUIRED", False, "low", "easy", ["missing_id", "refund"]),
        ("帮我改地址，我没带订单号", "order_update_address", "pending_confirmation", "ORDER_ID_REQUIRED", False, "low", "easy", ["missing_id", "address_change"]),
    ]
    for i in range(10):
        message, action, status, code, manual, risk_bucket, difficulty, tags = missing_variants[i % len(missing_variants)]
        cases.append(
            EvalCase(
                case_id=f"case-{index:03d}",
                message=message,
                user_id="anonymous",
                expected_action=action,
                expected_status=status,
                expected_code=code,
                expected_manual_review=manual,
                risk_bucket=risk_bucket,
                difficulty=difficulty,
                tags=tags,
            )
        )
        index += 1

    return cases
