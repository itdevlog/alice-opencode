import os
import sqlite3
import threading
import time
from dataclasses import dataclass


@dataclass
class Pending:
    question: str
    answer: str | None

    @property
    def is_ready(self) -> bool:
        return self.answer is not None


class Storage:
    def __init__(self, db_path: str):
        directory = os.path.dirname(db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_schema()

    def _create_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created REAL NOT NULL
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_user ON messages(user_id, id)"
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pending (
                    user_id TEXT PRIMARY KEY,
                    question TEXT NOT NULL,
                    answer TEXT,
                    created REAL NOT NULL
                )
                """
            )

    def add_message(self, user_id: str, role: str, content: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO messages (user_id, role, content, created) VALUES (?, ?, ?, ?)",
                (user_id, role, content, time.time()),
            )

    def get_history(self, user_id: str, limit: int) -> list[dict[str, str]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT role, content FROM messages WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def clear_history(self, user_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))

    def save_pending(self, user_id: str, question: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO pending (user_id, question, answer, created)
                VALUES (?, ?, NULL, ?)
                ON CONFLICT(user_id) DO UPDATE SET question = excluded.question,
                    answer = NULL, created = excluded.created
                """,
                (user_id, question, time.time()),
            )

    def set_pending_answer(self, user_id: str, answer: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE pending SET answer = ? WHERE user_id = ?", (answer, user_id)
            )

    def get_pending(self, user_id: str) -> Pending | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT question, answer FROM pending WHERE user_id = ?", (user_id,)
            ).fetchone()
        if row is None:
            return None
        return Pending(question=row["question"], answer=row["answer"])

    def pop_pending(self, user_id: str) -> Pending | None:
        pending = self.get_pending(user_id)
        if pending is not None:
            with self._lock, self._conn:
                self._conn.execute("DELETE FROM pending WHERE user_id = ?", (user_id,))
        return pending

    def close(self) -> None:
        with self._lock:
            self._conn.close()
