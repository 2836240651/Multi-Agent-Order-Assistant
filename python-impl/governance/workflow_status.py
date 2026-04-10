from __future__ import annotations

from enum import Enum


class ExecutionStatus(str, Enum):
    EXECUTED = "executed"
    SUBMITTED = "submitted"
    WAITING_USER_INPUT = "waiting_user_input"
    WAITING_MANUAL_REVIEW = "waiting_manual_review"
    FAILED = "failed"
    DEGRADED_FALLBACK = "degraded_fallback"


EXECUTION_STATUS_LABELS = {
    ExecutionStatus.EXECUTED.value: "已执行",
    ExecutionStatus.SUBMITTED.value: "已提交",
    ExecutionStatus.WAITING_USER_INPUT.value: "待补充信息",
    ExecutionStatus.WAITING_MANUAL_REVIEW.value: "待人工审核",
    ExecutionStatus.FAILED.value: "执行失败",
    ExecutionStatus.DEGRADED_FALLBACK.value: "降级兜底",
}


def normalize_execution_status(status: str | None) -> str:
    if not status:
        return ExecutionStatus.EXECUTED.value
    normalized = status.strip().lower()
    if normalized not in EXECUTION_STATUS_LABELS:
        return ExecutionStatus.EXECUTED.value
    return normalized


def execution_status_label(status: str | None) -> str:
    return EXECUTION_STATUS_LABELS[normalize_execution_status(status)]
