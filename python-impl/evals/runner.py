from __future__ import annotations

import json
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from api.main import app
from evals.cases import EvalCase, build_week3_cases


@dataclass
class EvalOutcome:
    case_id: str
    action: str
    status: str
    code: str
    manual_review: bool
    latency_ms: float
    passed: bool
    expected_action: str
    expected_status: str
    expected_code: str
    expected_manual_review: bool
    risk_bucket: str
    difficulty: str
    tags: list[str]


def _normalize_status(payload: dict[str, Any]) -> str:
    risk = payload.get("risk") or {}
    if risk.get("requires_manual_review"):
        return "review_required"
    return payload.get("execution_status", "") or "unknown"


def _extract_code(payload: dict[str, Any]) -> str:
    workflow = payload.get("workflow") or {}
    if payload.get("risk", {}).get("requires_manual_review"):
        return "REVIEW_REQUIRED"
    return workflow.get("code", "")


def _baseline_v1(case: EvalCase) -> dict[str, Any]:
    message = case.message.lower()
    if "退款" in case.message or "refund" in message:
        action = "refund_apply"
    elif "订单" in case.message or "order" in message or "物流" in case.message:
        action = "order_query"
    elif "地址" in case.message:
        action = "order_query"
    else:
        action = "order_query"

    status_map = {
        "order_query": "executed",
        "refund_apply": "pending_confirmation",
        "order_update_address": "executed",
    }
    code_map = {
        "order_query": "ORDER_FOUND",
        "refund_apply": "REFUND_REQUESTED",
        "order_update_address": "ADDRESS_UPDATED",
    }
    return {
        "action": action,
        "status": status_map.get(action, "unknown"),
        "code": code_map.get(action, ""),
        "manual_review": False,
    }


def _baseline_v2(case: EvalCase) -> dict[str, Any]:
    message = case.message.lower()
    if "退款" in case.message or "refund" in message:
        action = "refund_apply"
    elif "地址" in case.message or "change address" in message:
        action = "order_update_address"
    elif "订单" in case.message or "order" in message or "物流" in case.message:
        action = "order_query"
    else:
        action = "order_query"

    if "忘了订单号" in case.message or "没带订单号" in case.message:
        status = "pending_confirmation"
        code = "ORDER_ID_REQUIRED"
    elif "用了两个月" in case.message:
        status = "failed"
        code = "REFUND_NOT_ELIGIBLE"
    elif action == "order_update_address" and "ORD-20260401-001" in case.message:
        status = "failed"
        code = "ADDRESS_CHANGE_WINDOW_EXPIRED"
    else:
        status = {
            "order_query": "executed",
            "refund_apply": "pending_confirmation",
            "order_update_address": "executed",
        }.get(action, "unknown")
        code = {
            "order_query": "ORDER_FOUND",
            "refund_apply": "REFUND_REQUESTED",
            "order_update_address": "ADDRESS_UPDATED",
        }.get(action, "")

    return {
        "action": action,
        "status": status,
        "code": code,
        "manual_review": False,
    }


def _score_predictions(
    cases: list[EvalCase],
    predictions: list[dict[str, Any]],
    *,
    latencies: list[float] | None = None,
) -> dict[str, Any]:
    total = len(cases)
    action_hits = 0
    status_hits = 0
    code_hits = 0
    manual_hits = 0
    full_hits = 0
    false_interceptions = 0
    missed_high_risk = 0
    by_risk: dict[str, Counter[str]] = defaultdict(Counter)

    for idx, case in enumerate(cases):
        pred = predictions[idx]
        action_hit = pred["action"] == case.expected_action
        status_hit = pred["status"] == case.expected_status
        code_hit = pred["code"] == case.expected_code
        manual_hit = pred["manual_review"] == case.expected_manual_review

        action_hits += int(action_hit)
        status_hits += int(status_hit)
        code_hits += int(code_hit)
        manual_hits += int(manual_hit)
        full_hits += int(action_hit and status_hit and code_hit and manual_hit)

        if pred["manual_review"] and not case.expected_manual_review:
            false_interceptions += 1
        if case.expected_manual_review and not pred["manual_review"]:
            missed_high_risk += 1

        by_risk[case.risk_bucket]["total"] += 1
        by_risk[case.risk_bucket]["passed"] += int(action_hit and status_hit and manual_hit)

    avg_latency = statistics.mean(latencies) if latencies else 0.0
    handoff_rate = sum(int(pred["manual_review"]) for pred in predictions) / total

    return {
        "dataset_size": total,
        "action_accuracy": round(action_hits / total, 4),
        "status_accuracy": round(status_hits / total, 4),
        "code_accuracy": round(code_hits / total, 4),
        "manual_review_accuracy": round(manual_hits / total, 4),
        "automation_success_rate": round(full_hits / total, 4),
        "false_interception_rate": round(false_interceptions / total, 4),
        "missed_high_risk_rate": round(missed_high_risk / total, 4),
        "human_handoff_rate": round(handoff_rate, 4),
        "avg_latency_ms": round(avg_latency, 2),
        "by_risk_bucket": {
            bucket: {
                "total": counts["total"],
                "pass_rate": round(counts["passed"] / counts["total"], 4),
            }
            for bucket, counts in by_risk.items()
        },
    }


def run_week3_evaluation(output_dir: str | Path) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    cases = build_week3_cases()

    current_predictions: list[dict[str, Any]] = []
    current_latencies: list[float] = []
    outcomes: list[EvalOutcome] = []

    with TestClient(app) as client:
        for case in cases:
            client.post("/api/demo/reset")
            started = time.perf_counter()
            response = client.post(
                "/api/chat",
                json={"message": case.message, "user_id": case.user_id},
            )
            latency_ms = (time.perf_counter() - started) * 1000
            payload = response.json()
            status = _normalize_status(payload)
            code = _extract_code(payload)
            action = payload.get("action", "")
            manual_review = bool((payload.get("risk") or {}).get("requires_manual_review", False))

            pred = {
                "action": action,
                "status": status,
                "code": code,
                "manual_review": manual_review,
            }
            current_predictions.append(pred)
            current_latencies.append(latency_ms)

            outcomes.append(
                EvalOutcome(
                    case_id=case.case_id,
                    action=action,
                    status=status,
                    code=code,
                    manual_review=manual_review,
                    latency_ms=round(latency_ms, 2),
                    passed=(
                        action == case.expected_action
                        and status == case.expected_status
                        and code == case.expected_code
                        and manual_review == case.expected_manual_review
                    ),
                    expected_action=case.expected_action,
                    expected_status=case.expected_status,
                    expected_code=case.expected_code,
                    expected_manual_review=case.expected_manual_review,
                    risk_bucket=case.risk_bucket,
                    difficulty=case.difficulty,
                    tags=case.tags,
                )
            )

    baseline_v1_predictions = [_baseline_v1(case) for case in cases]
    baseline_v2_predictions = [_baseline_v2(case) for case in cases]

    summary = {
        "baseline_v1": _score_predictions(cases, baseline_v1_predictions),
        "optimized_v2": _score_predictions(cases, baseline_v2_predictions),
        "current_v3": _score_predictions(cases, current_predictions, latencies=current_latencies),
    }

    raw_path = output_path / "week3_eval_results.json"
    raw_path.write_text(
        json.dumps(
            {
                "summary": summary,
                "cases": [case.to_dict() for case in cases],
                "outcomes": [asdict(outcome) for outcome in outcomes],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    report_lines = [
        "# Week3 Evaluation Report",
        "",
        f"- Dataset size: {len(cases)}",
        "- Baseline v1: Week1-style routing only",
        "- Optimized v2: better routing and failure handling",
        "- Current v3: live system with risk review and audit flow",
        "",
        "| Variant | Action Acc | Status Acc | Code Acc | Manual Review Acc | Auto Success | False Intercept | Missed High Risk | Handoff Rate | Avg Latency ms |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    for name in ["baseline_v1", "optimized_v2", "current_v3"]:
        row = summary[name]
        report_lines.append(
            "| "
            + " | ".join(
                [
                    name,
                    str(row["action_accuracy"]),
                    str(row["status_accuracy"]),
                    str(row["code_accuracy"]),
                    str(row["manual_review_accuracy"]),
                    str(row["automation_success_rate"]),
                    str(row["false_interception_rate"]),
                    str(row["missed_high_risk_rate"]),
                    str(row["human_handoff_rate"]),
                    str(row["avg_latency_ms"]),
                ]
            )
            + " |"
        )

    report_lines.extend(
        [
            "",
            "## By Risk Bucket",
            "",
        ]
    )

    current_by_risk = summary["current_v3"]["by_risk_bucket"]
    for bucket, values in current_by_risk.items():
        report_lines.append(f"- {bucket}: total={values['total']}, pass_rate={values['pass_rate']}")

    report_path = output_path / "week3_eval_report.md"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")

    return {
        "summary": summary,
        "results_path": str(raw_path),
        "report_path": str(report_path),
    }
