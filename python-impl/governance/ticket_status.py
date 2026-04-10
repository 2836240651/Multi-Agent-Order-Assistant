from __future__ import annotations

from enum import Enum


class TicketStatus(str, Enum):
    CREATED = "created"
    PENDING = "pending"
    PENDING_USER_CONFIRM = "pending_user_confirm"
    PENDING_MANUAL_REVIEW = "pending_manual_review"
    PENDING_REVIEW = "pending_review"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    REJECTED = "rejected"
    CLOSED = "closed"


LEGACY_TICKET_STATUS_ALIASES = {
    "processing": TicketStatus.IN_PROGRESS.value,
}


TICKET_STATUS_LABELS = {
    TicketStatus.CREATED.value: "已创建",
    TicketStatus.PENDING.value: "待处理",
    TicketStatus.PENDING_USER_CONFIRM.value: "待用户补充",
    TicketStatus.PENDING_MANUAL_REVIEW.value: "待人工审核",
    TicketStatus.PENDING_REVIEW.value: "待业务审核",
    TicketStatus.IN_PROGRESS.value: "处理中",
    TicketStatus.RESOLVED.value: "已解决",
    TicketStatus.REJECTED.value: "已拒绝",
    TicketStatus.CLOSED.value: "已关闭",
}


TICKET_STATUS_DESCRIPTIONS = {
    TicketStatus.CREATED.value: "工单已创建，等待进入下一步处理。",
    TicketStatus.PENDING.value: "工单已入队，等待处理人接手。",
    TicketStatus.PENDING_USER_CONFIRM.value: "等待用户补充缺失信息后继续处理。",
    TicketStatus.PENDING_MANUAL_REVIEW.value: "等待人工审核员审批后继续处理。",
    TicketStatus.PENDING_REVIEW.value: "请求已提交，等待业务或售后审核。",
    TicketStatus.IN_PROGRESS.value: "工单已被接手，正在处理。",
    TicketStatus.RESOLVED.value: "工单对应诉求已处理完成。",
    TicketStatus.REJECTED.value: "工单对应诉求未通过审核或执行失败。",
    TicketStatus.CLOSED.value: "工单已归档关闭。",
}


TICKET_STATUS_NEXT_STEPS = {
    TicketStatus.CREATED.value: "等待系统分发到具体处理阶段。",
    TicketStatus.PENDING.value: "等待客服或业务侧开始处理。",
    TicketStatus.PENDING_USER_CONFIRM.value: "请补充所需信息，系统收到后会继续处理。",
    TicketStatus.PENDING_MANUAL_REVIEW.value: "等待审核员审批，审批后会继续推进。",
    TicketStatus.PENDING_REVIEW.value: "等待售后审核结果，可稍后查询最新进度。",
    TicketStatus.IN_PROGRESS.value: "工单正在处理中，请稍后查看结果。",
    TicketStatus.RESOLVED.value: "如无其他问题，可关闭工单。",
    TicketStatus.REJECTED.value: "如需继续处理，可补充信息后重新发起。",
    TicketStatus.CLOSED.value: "工单流程已结束。",
}


TICKET_TERMINAL_STATUSES = {
    TicketStatus.RESOLVED.value,
    TicketStatus.REJECTED.value,
    TicketStatus.CLOSED.value,
}


TICKET_ALLOWED_TRANSITIONS = {
    TicketStatus.CREATED.value: {
        TicketStatus.CREATED.value,
        TicketStatus.PENDING.value,
        TicketStatus.PENDING_USER_CONFIRM.value,
        TicketStatus.PENDING_MANUAL_REVIEW.value,
        TicketStatus.PENDING_REVIEW.value,
        TicketStatus.IN_PROGRESS.value,
        TicketStatus.RESOLVED.value,
        TicketStatus.REJECTED.value,
        TicketStatus.CLOSED.value,
    },
    TicketStatus.PENDING.value: {
        TicketStatus.PENDING.value,
        TicketStatus.PENDING_USER_CONFIRM.value,
        TicketStatus.PENDING_MANUAL_REVIEW.value,
        TicketStatus.PENDING_REVIEW.value,
        TicketStatus.IN_PROGRESS.value,
        TicketStatus.RESOLVED.value,
        TicketStatus.REJECTED.value,
        TicketStatus.CLOSED.value,
    },
    TicketStatus.PENDING_USER_CONFIRM.value: {
        TicketStatus.PENDING_USER_CONFIRM.value,
        TicketStatus.PENDING.value,
        TicketStatus.PENDING_MANUAL_REVIEW.value,
        TicketStatus.PENDING_REVIEW.value,
        TicketStatus.IN_PROGRESS.value,
        TicketStatus.RESOLVED.value,
        TicketStatus.REJECTED.value,
        TicketStatus.CLOSED.value,
    },
    TicketStatus.PENDING_MANUAL_REVIEW.value: {
        TicketStatus.PENDING_MANUAL_REVIEW.value,
        TicketStatus.PENDING_REVIEW.value,
        TicketStatus.IN_PROGRESS.value,
        TicketStatus.RESOLVED.value,
        TicketStatus.REJECTED.value,
        TicketStatus.CLOSED.value,
    },
    TicketStatus.PENDING_REVIEW.value: {
        TicketStatus.PENDING_REVIEW.value,
        TicketStatus.IN_PROGRESS.value,
        TicketStatus.RESOLVED.value,
        TicketStatus.REJECTED.value,
        TicketStatus.CLOSED.value,
    },
    TicketStatus.IN_PROGRESS.value: {
        TicketStatus.IN_PROGRESS.value,
        TicketStatus.RESOLVED.value,
        TicketStatus.REJECTED.value,
        TicketStatus.CLOSED.value,
    },
    TicketStatus.RESOLVED.value: {
        TicketStatus.RESOLVED.value,
        TicketStatus.CLOSED.value,
    },
    TicketStatus.REJECTED.value: {
        TicketStatus.REJECTED.value,
        TicketStatus.CLOSED.value,
    },
    TicketStatus.CLOSED.value: {
        TicketStatus.CLOSED.value,
    },
}


def normalize_ticket_status(status: str | None) -> str:
    if not status:
        return TicketStatus.PENDING.value
    normalized = status.strip().lower()
    normalized = LEGACY_TICKET_STATUS_ALIASES.get(normalized, normalized)
    if normalized not in TICKET_STATUS_LABELS:
        return TicketStatus.PENDING.value
    return normalized


def ticket_status_label(status: str | None) -> str:
    return TICKET_STATUS_LABELS[normalize_ticket_status(status)]


def ticket_status_description(status: str | None) -> str:
    return TICKET_STATUS_DESCRIPTIONS[normalize_ticket_status(status)]


def ticket_next_step(status: str | None) -> str:
    return TICKET_STATUS_NEXT_STEPS[normalize_ticket_status(status)]


def is_terminal_ticket_status(status: str | None) -> bool:
    return normalize_ticket_status(status) in TICKET_TERMINAL_STATUSES


def can_transition_ticket_status(current: str | None, target: str | None) -> bool:
    current_status = normalize_ticket_status(current)
    target_status = normalize_ticket_status(target)
    return target_status in TICKET_ALLOWED_TRANSITIONS[current_status]


def allowed_ticket_transitions(status: str | None) -> list[str]:
    current_status = normalize_ticket_status(status)
    return sorted(TICKET_ALLOWED_TRANSITIONS[current_status])


def enrich_ticket(ticket: dict) -> dict:
    status = normalize_ticket_status(ticket.get("status"))
    history = []
    for item in ticket.get("history", []) or []:
        item_status = normalize_ticket_status(item.get("status"))
        history.append(
            {
                **item,
                "status": item_status,
                "status_label": ticket_status_label(item_status),
                "next_step": item.get("next_step") or ticket_next_step(item_status),
            }
        )

    custom_next_step = history[-1].get("next_step") if history else ""
    return {
        **ticket,
        "status": status,
        "ticket_status": status,
        "ticket_status_label": ticket_status_label(status),
        "ticket_status_description": ticket_status_description(status),
        "ticket_next_step": custom_next_step if custom_next_step else ticket_next_step(status),
        "is_terminal": is_terminal_ticket_status(status),
        "allowed_transitions": allowed_ticket_transitions(status),
        "history": history,
    }
