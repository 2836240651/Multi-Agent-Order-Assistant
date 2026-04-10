from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Any

from governance.ticket_status import is_terminal_ticket_status, normalize_ticket_status
from governance.webhook import WebhookEventType, emit_webhook


SLA_HOURS = {
    "high": 2,
    "medium": 8,
    "low": 24,
}


async def compute_sla_due(priority: str, created_at: str) -> str:
    hours = SLA_HOURS.get(priority.lower(), 8)
    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        created = datetime.now()
    due = created + timedelta(hours=hours)
    return due.isoformat()


async def check_overdue_tickets(get_conn, batch_size: int = 50) -> list[dict[str, Any]]:
    conn = get_conn()
    cursor = conn.execute(
        """
        SELECT ticket_id, user_id, title, priority, status, created_at, sla_due_at, updated_at
        FROM tickets
        WHERE sla_due_at IS NOT NULL AND sla_due_at != ''
        AND status NOT IN ('resolved', 'rejected', 'closed')
        ORDER BY sla_due_at ASC
        LIMIT ?
        """,
        (batch_size,),
    )
    rows = cursor.fetchall()
    conn.close()

    now = datetime.now()
    overdue_tickets = []
    for row in rows:
        ticket = {
            "ticket_id": row[0],
            "user_id": row[1],
            "title": row[2],
            "priority": row[3],
            "status": row[4],
            "created_at": row[5],
            "sla_due_at": row[6],
            "updated_at": row[7],
        }
        if ticket["sla_due_at"]:
            try:
                due = datetime.fromisoformat(ticket["sla_due_at"].replace("Z", "+00:00"))
                if now > due:
                    overdue_tickets.append(ticket)
            except (ValueError, TypeError):
                pass
    return overdue_tickets


async def send_overdue_reminder(get_conn, ticket: dict[str, Any]) -> str:
    reminder_id = f"REM-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
    now = datetime.now().isoformat()
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO ticket_reminders (reminder_id, ticket_id, remind_type, sent_to, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (reminder_id, ticket["ticket_id"], "sla_overdue", ticket.get("user_id", ""), "sent", now),
    )
    conn.commit()
    conn.close()

    payload = {
        "event": WebhookEventType.TICKET_STATUS_CHANGED.value,
        "ticket_id": ticket["ticket_id"],
        "title": ticket["title"],
        "priority": ticket["priority"],
        "status": ticket["status"],
        "sla_due_at": ticket["sla_due_at"],
        "overdue_by_minutes": int((datetime.now() - datetime.fromisoformat(ticket["sla_due_at"].replace("Z", "+00:00"))).total_seconds() / 60),
        "reminder_id": reminder_id,
        "timestamp": now,
    }
    await emit_webhook("ticket.overdue", payload)
    return reminder_id


async def rate_ticket(get_conn, ticket_id: str, user_id: str, rating: int, rating_comment: str = "") -> dict[str, Any]:
    if not (1 <= rating <= 5):
        return {"success": False, "message": "Rating must be between 1 and 5."}
    conn = get_conn()
    cursor = conn.execute("SELECT status, user_id FROM tickets WHERE ticket_id = ?", (ticket_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"success": False, "message": "Ticket not found."}
    status = normalize_ticket_status(row[0])
    ticket_user = row[1]
    if user_id != ticket_user and user_id != "admin":
        conn.close()
        return {"success": False, "message": "Not authorized to rate this ticket."}
    now = datetime.now().isoformat()
    conn.execute(
        "UPDATE tickets SET rating = ?, rating_comment = ?, rating_at = ? WHERE ticket_id = ?",
        (rating, rating_comment, now, ticket_id),
    )
    conn.commit()
    conn.close()
    return {"success": True, "message": "Rating submitted.", "data": {"ticket_id": ticket_id, "rating": rating, "rating_comment": rating_comment, "rating_at": now}}


async def log_operation(
    get_conn,
    operator_id: str,
    operator_type: str,
    target_type: str,
    target_id: str,
    action: str,
    detail: str = "",
    before_state: str = "",
    after_state: str = "",
    ip_address: str = "",
    user_agent: str = "",
) -> str:
    log_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO operational_logs (log_id, operator_id, operator_type, target_type, target_id, action, detail, before_state, after_state, ip_address, user_agent, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (log_id, operator_id, operator_type, target_type, target_id, action, detail, before_state, after_state, ip_address, user_agent, now),
    )
    conn.commit()
    conn.close()
    return log_id


async def search_operational_logs(
    get_conn,
    operator_id: str = "",
    target_type: str = "",
    target_id: str = "",
    action: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 100,
) -> list[dict[str, Any]]:
    conn = get_conn()
    query = "SELECT * FROM operational_logs WHERE 1=1"
    params: list[Any] = []
    if operator_id:
        query += " AND operator_id = ?"
        params.append(operator_id)
    if target_type:
        query += " AND target_type = ?"
        params.append(target_type)
    if target_id:
        query += " AND target_id = ?"
        params.append(target_id)
    if action:
        query += " AND action = ?"
        params.append(action)
    if date_from:
        query += " AND created_at >= ?"
        params.append(date_from)
    if date_to:
        query += " AND created_at <= ?"
        params.append(date_to)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(min(limit, 500))
    cursor = conn.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    cols = [description[0] for description in cursor.description] if cursor.description else []
    return [dict(zip(cols, row)) for row in rows]
