from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def upgrade_db(db_path: str | Path = "mcp/commerce.db"):
    if isinstance(db_path, str):
        db_path = Path(__file__).resolve().parents[1] / db_path
    else:
        db_path = Path(db_path)

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            message_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            order_id TEXT DEFAULT '',
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            intent TEXT DEFAULT '',
            action TEXT DEFAULT '',
            is_read INTEGER DEFAULT 0,
            read_at TEXT
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_user_order ON chat_messages(user_id, order_id)")

    cursor.execute("ALTER TABLE tickets ADD COLUMN sla_due_at TEXT")
    cursor.execute("ALTER TABLE tickets ADD COLUMN rating INTEGER")
    cursor.execute("ALTER TABLE tickets ADD COLUMN rating_comment TEXT")
    cursor.execute("ALTER TABLE tickets ADD COLUMN rating_at TEXT")
    cursor.execute("ALTER TABLE tickets ADD COLUMN assigned_to TEXT DEFAULT ''")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS operational_logs (
            log_id TEXT PRIMARY KEY,
            operator_id TEXT NOT NULL,
            operator_type TEXT NOT NULL,
            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            action TEXT NOT NULL,
            detail TEXT DEFAULT '',
            before_state TEXT DEFAULT '',
            after_state TEXT DEFAULT '',
            ip_address TEXT DEFAULT '',
            user_agent TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_oplogs_target ON operational_logs(target_type, target_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_oplogs_operator ON operational_logs(operator_id, operator_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_oplogs_created ON operational_logs(created_at)")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ticket_reminders (
            reminder_id TEXT PRIMARY KEY,
            ticket_id TEXT NOT NULL,
            remind_type TEXT NOT NULL,
            sent_to TEXT NOT NULL,
            status TEXT NOT NULL,
            note TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            sent_at TEXT
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_reminders_ticket ON ticket_reminders(ticket_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_reminders_status ON ticket_reminders(status)")

    cursor.execute("CREATE TABLE IF NOT EXISTS chat_message_reads (message_id TEXT, user_id TEXT, read_at TEXT, PRIMARY KEY(message_id, user_id))")

    conn.commit()
    conn.close()
    print("Database upgrade completed successfully.")


if __name__ == "__main__":
    upgrade_db()
