from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()


@dataclass
class ReviewItem:
    review_id: str
    session_id: str
    user_id: str
    action: str
    risk_level: str
    reason: str
    ticket_id: str = ""
    order_id: str = ""
    workflow_snapshot: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    resolution: str = ""
    reviewer_note: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    resolved_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ManualReviewManager:
    def __init__(self, db_path: str | None = None):
        if db_path is None:
            db_path = str(Path(__file__).resolve().parents[1] / "mcp" / "commerce.db")
        self._db_path = db_path
        self._use_mysql = os.getenv("MYSQL_HOST") is not None
        self._items: dict[str, ReviewItem] = {}
        self._load_from_db()

    def _get_connection(self):
        if self._use_mysql:
            import pymysql
            return pymysql.connect(
                host=os.getenv("MYSQL_HOST", "localhost"),
                port=int(os.getenv("MYSQL_PORT", 3306)),
                user=os.getenv("MYSQL_USER", "root"),
                password=os.getenv("MYSQL_PASSWORD", ""),
                database=os.getenv("MYSQL_DATABASE", "smart_cs"),
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
            )
        else:
            import sqlite3
            conn = sqlite3.connect(self._db_path, timeout=30, check_same_thread=False)
            conn.execute("PRAGMA busy_timeout = 30000")
            conn.execute("PRAGMA journal_mode = WAL")
            return conn

    def _load_from_db(self) -> None:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM manual_reviews WHERE status = 'pending'")
            rows = cursor.fetchall()
            for row in rows:
                if self._use_mysql:
                    data = dict(row)
                    data['workflow_snapshot'] = json.loads(data.get('workflow_snapshot') or '{}')
                    data['evidence'] = json.loads(data.get('evidence') or '{}')
                else:
                    keys = ['review_id', 'session_id', 'user_id', 'action', 'risk_level', 'reason', 
                           'ticket_id', 'order_id', 'workflow_snapshot', 'evidence', 'status', 
                           'resolution', 'reviewer_note', 'created_at', 'resolved_at']
                    data = dict(zip(keys, row))
                    data['workflow_snapshot'] = json.loads(data.get('workflow_snapshot') or '{}')
                    data['evidence'] = json.loads(data.get('evidence') or '{}')
                item = ReviewItem(**data)
                self._items[item.review_id] = item
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def reset(self) -> None:
        self._items = {}

    def _save_to_db(self, review: ReviewItem) -> None:
        import time

        last_error: Exception | None = None
        for _ in range(5):
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                if self._use_mysql:
                    cursor.execute('''
                        INSERT INTO manual_reviews 
                        (review_id, session_id, user_id, action, risk_level, reason, ticket_id, order_id, 
                         workflow_snapshot, evidence, status, resolution, reviewer_note, created_at, resolved_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                        status=VALUES(status), resolution=VALUES(resolution), 
                        reviewer_note=VALUES(reviewer_note), resolved_at=VALUES(resolved_at)
                    ''', (
                        review.review_id, review.session_id, review.user_id, review.action, review.risk_level,
                        review.reason, review.ticket_id, review.order_id,
                        json.dumps(review.workflow_snapshot), json.dumps(review.evidence),
                        review.status, review.resolution, review.reviewer_note, review.created_at, review.resolved_at
                    ))
                else:
                    cursor.execute('''
                        INSERT OR REPLACE INTO manual_reviews 
                        (review_id, session_id, user_id, action, risk_level, reason, ticket_id, order_id, 
                         workflow_snapshot, evidence, status, resolution, reviewer_note, created_at, resolved_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        review.review_id, review.session_id, review.user_id, review.action, review.risk_level,
                        review.reason, review.ticket_id, review.order_id,
                        json.dumps(review.workflow_snapshot), json.dumps(review.evidence),
                        review.status, review.resolution, review.reviewer_note, review.created_at, review.resolved_at
                    ))
                conn.commit()
                return
            except Exception as exc:
                last_error = exc
                if self._use_mysql:
                    import pymysql
                    if isinstance(exc, pymysql.err.OperationalError) and "locked" not in str(exc).lower():
                        raise
                else:
                    import sqlite3
                    if isinstance(exc, sqlite3.OperationalError) and "locked" not in str(exc).lower():
                        raise
                time.sleep(0.2)
            finally:
                conn.close()
        if last_error is not None:
            raise last_error

    def create_review(
        self,
        *,
        session_id: str,
        user_id: str,
        action: str,
        risk_level: str,
        reason: str,
        ticket_id: str = "",
        order_id: str = "",
        workflow_snapshot: dict[str, Any] | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> ReviewItem:
        review = ReviewItem(
            review_id=f"RV-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}",
            session_id=session_id,
            user_id=user_id,
            action=action,
            risk_level=risk_level,
            reason=reason,
            ticket_id=ticket_id,
            order_id=order_id,
            workflow_snapshot=workflow_snapshot or {},
            evidence=evidence or {},
        )
        self._items[review.review_id] = review
        self._save_to_db(review)
        return review

    def get(self, review_id: str) -> ReviewItem | None:
        return self._items.get(review_id)

    def list_pending(self) -> list[dict[str, Any]]:
        return [
            item.to_dict()
            for item in self._items.values()
            if item.status == "pending"
        ]

    def find_pending(self, order_id: str, action: str) -> ReviewItem | None:
        for item in self._items.values():
            if item.status == "pending" and item.order_id == order_id and item.action == action:
                return item
        return None

    def resolve(self, review_id: str, resolution: str, reviewer_note: str = "") -> ReviewItem | None:
        item = self._items.get(review_id)
        if item is None:
            return None
        item.status = "resolved"
        item.resolution = resolution
        item.reviewer_note = reviewer_note
        item.resolved_at = datetime.now().isoformat()
        self._save_to_db(item)
        return item
