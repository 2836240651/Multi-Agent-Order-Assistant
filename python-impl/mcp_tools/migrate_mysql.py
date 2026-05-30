"""
MySQL schema migration - add new columns and tables
"""
from __future__ import annotations

import os
from datetime import datetime

try:
    import pymysql
except ImportError:
    print("PyMySQL not installed.")
    exit(1)

from dotenv import load_dotenv
load_dotenv()


def get_conn():
    return pymysql.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        port=int(os.getenv("MYSQL_PORT", 3306)),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        database=os.getenv("MYSQL_DATABASE", "smart_cs"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def migrate():
    conn = get_conn()
    cursor = conn.cursor()

    # Add columns to tickets table
    ticket_cols = [
        ("sla_due_at", "VARCHAR(64) DEFAULT ''"),
        ("rating", "INT DEFAULT NULL"),
        ("rating_comment", "TEXT"),
        ("rating_at", "VARCHAR(64) DEFAULT ''"),
        ("assigned_to", "VARCHAR(128) DEFAULT ''"),
    ]
    for col_name, col_type in ticket_cols:
        try:
            cursor.execute(f"ALTER TABLE tickets ADD COLUMN {col_name} {col_type}")
            conn.commit()
            print(f"Added column: tickets.{col_name}")
        except Exception as e:
            if "Duplicate column" in str(e):
                print(f"Column already exists: tickets.{col_name}")
            else:
                print(f"Error adding {col_name}: {e}")

    # Add columns to chat_messages
    chat_cols = [
        ("is_read", "INT DEFAULT 0"),
        ("read_at", "VARCHAR(64) DEFAULT ''"),
    ]
    for col_name, col_type in chat_cols:
        try:
            cursor.execute(f"ALTER TABLE chat_messages ADD COLUMN {col_name} {col_type}")
            conn.commit()
            print(f"Added column: chat_messages.{col_name}")
        except Exception as e:
            if "Duplicate column" in str(e):
                print(f"Column already exists: chat_messages.{col_name}")
            else:
                print(f"Error adding {col_name}: {e}")

    # Create chat_messages table if not exists
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                message_id VARCHAR(64) PRIMARY KEY,
                user_id VARCHAR(128) NOT NULL,
                order_id VARCHAR(64) DEFAULT '',
                session_id VARCHAR(64) NOT NULL,
                role VARCHAR(32) NOT NULL,
                content TEXT NOT NULL,
                created_at VARCHAR(64) NOT NULL,
                intent VARCHAR(64) DEFAULT '',
                action VARCHAR(64) DEFAULT '',
                is_read INT DEFAULT 0,
                read_at VARCHAR(64) DEFAULT '',
                INDEX idx_chat_session (session_id),
                INDEX idx_chat_user_order (user_id, order_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.commit()
        print("Created table: chat_messages")
    except Exception as e:
        if "already exists" in str(e).lower():
            print("Table already exists: chat_messages")
        else:
            print(f"Error creating chat_messages: {e}")

    # Create operational_logs table
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS operational_logs (
                log_id VARCHAR(64) PRIMARY KEY,
                operator_id VARCHAR(128) NOT NULL,
                operator_type VARCHAR(32) NOT NULL,
                target_type VARCHAR(32) NOT NULL,
                target_id VARCHAR(128) NOT NULL,
                action VARCHAR(128) NOT NULL,
                detail TEXT,
                before_state TEXT,
                after_state TEXT,
                ip_address VARCHAR(64) DEFAULT '',
                user_agent TEXT,
                created_at VARCHAR(64) NOT NULL,
                INDEX idx_oplogs_target (target_type, target_id),
                INDEX idx_oplogs_operator (operator_id, operator_type),
                INDEX idx_oplogs_created (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.commit()
        print("Created table: operational_logs")
    except Exception as e:
        if "already exists" in str(e).lower():
            print("Table already exists: operational_logs")
        else:
            print(f"Error creating operational_logs: {e}")

    # Create ticket_reminders table
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ticket_reminders (
                reminder_id VARCHAR(64) PRIMARY KEY,
                ticket_id VARCHAR(64) NOT NULL,
                remind_type VARCHAR(32) NOT NULL,
                sent_to VARCHAR(128) NOT NULL,
                status VARCHAR(32) NOT NULL,
                note TEXT,
                created_at VARCHAR(64) NOT NULL,
                sent_at VARCHAR(64),
                INDEX idx_reminders_ticket (ticket_id),
                INDEX idx_reminders_status (status)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.commit()
        print("Created table: ticket_reminders")
    except Exception as e:
        if "already exists" in str(e).lower():
            print("Table already exists: ticket_reminders")
        else:
            print(f"Error creating ticket_reminders: {e}")

    # Create order_status_history table
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS order_status_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                order_id VARCHAR(64) NOT NULL,
                old_status VARCHAR(32) NOT NULL,
                new_status VARCHAR(32) NOT NULL,
                changed_at VARCHAR(64) NOT NULL,
                changed_by VARCHAR(64) DEFAULT '',
                reason TEXT,
                INDEX idx_osh_order (order_id),
                INDEX idx_osh_changed_at (changed_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.commit()
        print("Created table: order_status_history")
    except Exception as e:
        if "already exists" in str(e).lower():
            print("Table already exists: order_status_history")
        else:
            print(f"Error creating order_status_history: {e}")

    conn.close()
    print("Migration completed.")


if __name__ == "__main__":
    migrate()
