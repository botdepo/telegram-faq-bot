"""Хранилище в SQLite: владелец, приветствие, вопросы-ответы и переписка с клиентами.

На botdepo писать на диск можно только в /data — эта папка переживает
перезапуски и передеплои. Остальная файловая система только для чтения.
Локально (где /data нет) база ляжет в ./data рядом с кодом.
"""
import os
import sqlite3
from pathlib import Path

DATA_DIR = Path(os.getenv("DATA_DIR") or ("/data" if Path("/data").is_dir() else "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

_db = sqlite3.connect(DATA_DIR / "faq.db")
_db.executescript(
    """
    CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS faq (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT NOT NULL,
        answer TEXT NOT NULL
    );
    -- owner_message_id: сообщение клиента в чате владельца; по нему находим клиента, когда владелец отвечает
    CREATE TABLE IF NOT EXISTS threads (
        owner_message_id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL
    );
    """
)
_db.commit()


def get(key: str, default: str | None = None) -> str | None:
    row = _db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def put(key: str, value: str) -> None:
    _db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    _db.commit()


def claim_owner(user_id: int) -> bool:
    """Первый, кто написал /start, становится владельцем. True — если это он."""
    if get("owner_id") is None:
        put("owner_id", str(user_id))
    return get("owner_id") == str(user_id)


def owner_id() -> int | None:
    value = get("owner_id")
    return int(value) if value else None


def add_faq(question: str, answer: str) -> None:
    _db.execute("INSERT INTO faq (question, answer) VALUES (?, ?)", (question, answer))
    _db.commit()


def list_faq() -> list[tuple[int, str, str]]:
    return _db.execute("SELECT id, question, answer FROM faq ORDER BY id").fetchall()


def get_faq(faq_id: int) -> tuple[int, str, str] | None:
    return _db.execute("SELECT id, question, answer FROM faq WHERE id = ?", (faq_id,)).fetchone()


def delete_faq(faq_id: int) -> None:
    _db.execute("DELETE FROM faq WHERE id = ?", (faq_id,))
    _db.commit()


def remember_thread(owner_message_id: int, user_id: int) -> None:
    _db.execute("INSERT OR REPLACE INTO threads (owner_message_id, user_id) VALUES (?, ?)", (owner_message_id, user_id))
    _db.commit()


def client_of(owner_message_id: int) -> int | None:
    row = _db.execute("SELECT user_id FROM threads WHERE owner_message_id = ?", (owner_message_id,)).fetchone()
    return row[0] if row else None
