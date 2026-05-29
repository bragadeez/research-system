"""
db/database.py — SQLite persistence layer.

init_db() is called explicitly by the FastAPI lifespan and main.py,
not at module import time.
"""
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict, List, Optional

from config import settings


@contextmanager
def _conn():
    conn = sqlite3.connect(settings.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create tables if they don't exist. Call this explicitly at startup."""
    with _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id              TEXT PRIMARY KEY,
            topic           TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'running',
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL,
            confidence      REAL,
            findings        INTEGER DEFAULT 0,
            sources         INTEGER DEFAULT 0,
            research_mode   TEXT DEFAULT 'standard'
        );
        CREATE TABLE IF NOT EXISTS reports (
            id          TEXT PRIMARY KEY,
            session_id  TEXT NOT NULL REFERENCES sessions(id),
            content     TEXT NOT NULL,
            critique    TEXT,
            fact_checks TEXT,
            word_count  INTEGER DEFAULT 0,
            created_at  TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS progress_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT NOT NULL REFERENCES sessions(id),
            agent       TEXT,
            message     TEXT,
            data        TEXT,
            created_at  TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS chat_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT NOT NULL REFERENCES sessions(id),
            role        TEXT NOT NULL,
            content     TEXT NOT NULL,
            created_at  TEXT NOT NULL
        );
        """)
        # Dynamic schema migration for existing databases
        cursor = c.execute("PRAGMA table_info(sessions)")
        columns = [row[1] for row in cursor.fetchall()]
        if "research_mode" not in columns:
            try:
                c.execute("ALTER TABLE sessions ADD COLUMN research_mode TEXT DEFAULT 'standard'")
            except Exception as e:
                import sys
                print(f"Migration error (adding research_mode): {e}", file=sys.stderr)

        # Clean up zombie sessions left in running/active pipeline statuses
        c.execute(
            "UPDATE sessions SET status='error', updated_at=? WHERE status IN ('running', 'planning', 'searching', 'extracting', 'synthesizing', 'validating')",
            (_now(),)
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_session(topic: str, research_mode: str = "standard") -> str:
    sid = str(uuid.uuid4())
    now = _now()
    with _conn() as c:
        c.execute(
            """INSERT INTO sessions 
               (id, topic, status, created_at, updated_at, confidence, findings, sources, research_mode) 
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (sid, topic, "running", now, now, None, 0, 0, research_mode),
        )
    return sid


def update_session(
    session_id: str,
    status: str,
    confidence: float = None,
    findings: int = None,
    sources: int = None,
):
    with _conn() as c:
        c.execute(
            "UPDATE sessions SET status=?, confidence=?, findings=?, sources=?, updated_at=? WHERE id=?",
            (status, confidence, findings, sources, _now(), session_id),
        )


def get_session(session_id: str) -> Optional[Dict]:
    with _conn() as c:
        row = c.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    return dict(row) if row else None


def list_sessions(limit: int = 50) -> List[Dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM sessions ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def delete_session(session_id: str):
    # Clean up Chroma vector index for the session if it exists
    try:
        from core.rag_engine import rag_engine
        rag_engine.delete_index(session_id)
    except Exception:
        pass

    with _conn() as c:
        for table in ("progress_log", "reports", "chat_history"):
            c.execute(f"DELETE FROM {table} WHERE session_id=?", (session_id,))
        c.execute("DELETE FROM sessions WHERE id=?", (session_id,))


def save_report(
    session_id: str,
    content: str,
    critique: str = None,
    fact_checks: List[Dict] = None,
) -> str:
    rid = str(uuid.uuid4())
    with _conn() as c:
        c.execute(
            "INSERT INTO reports VALUES (?,?,?,?,?,?,?)",
            (
                rid, session_id, content, critique,
                json.dumps(fact_checks or []),
                len(content.split()),
                _now(),
            ),
        )
    return rid


def get_report(session_id: str) -> Optional[Dict]:
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM reports WHERE session_id=? ORDER BY created_at DESC LIMIT 1",
            (session_id,),
        ).fetchone()
    if row:
        r = dict(row)
        r["fact_checks"] = json.loads(r.get("fact_checks") or "[]")
        return r
    return None


def log_progress(session_id: str, agent: str, message: str, data: Dict = None):
    with _conn() as c:
        c.execute(
            "INSERT INTO progress_log (session_id,agent,message,data,created_at) VALUES (?,?,?,?,?)",
            (session_id, agent, message, json.dumps(data or {}), _now()),
        )


def get_progress(session_id: str, limit: int = 100) -> List[Dict]:
    """Returns progress entries in chronological order (oldest first)."""
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM progress_log WHERE session_id=? ORDER BY id ASC LIMIT ?",
            (session_id, limit),
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["data"] = json.loads(d.get("data") or "{}")
        result.append(d)
    return result


def add_chat_message(session_id: str, role: str, content: str):
    with _conn() as c:
        c.execute(
            "INSERT INTO chat_history (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (session_id, role, content, _now())
        )


def get_chat_history(session_id: str) -> List[Dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT role, content, created_at FROM chat_history WHERE session_id=? ORDER BY id ASC",
            (session_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def clear_chat_history(session_id: str):
    with _conn() as c:
        c.execute("DELETE FROM chat_history WHERE session_id=?", (session_id,))


def import_session(session: dict, report: Optional[dict], progress: List[dict]) -> str:
    """Imports session, report, and progress log logs, returning the session ID."""
    sid = session.get("id") or str(uuid.uuid4())
    now = _now()
    with _conn() as c:
        # 1. Insert or replace session
        c.execute(
            """INSERT OR REPLACE INTO sessions 
               (id, topic, status, created_at, updated_at, confidence, findings, sources, research_mode) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                sid,
                session.get("topic", "Imported Research"),
                session.get("status", "complete"),
                session.get("created_at") or now,
                session.get("updated_at") or now,
                session.get("confidence"),
                session.get("findings") or 0,
                session.get("sources") or 0,
                session.get("research_mode") or "standard"
            )
        )
        
        # 2. Insert or replace report
        if report:
            rid = report.get("id") or str(uuid.uuid4())
            c.execute(
                """INSERT OR REPLACE INTO reports 
                   (id, session_id, content, critique, fact_checks, word_count, created_at) 
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    rid,
                    sid,
                    report.get("content", ""),
                    report.get("critique"),
                    json.dumps(report.get("fact_checks") or []),
                    report.get("word_count") or len(report.get("content", "").split()),
                    report.get("created_at") or now
                )
            )
            
        # 3. Clean and insert progress log
        c.execute("DELETE FROM progress_log WHERE session_id=?", (sid,))
        for p in progress:
            c.execute(
                """INSERT INTO progress_log 
                   (session_id, agent, message, data, created_at) 
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    sid,
                    p.get("agent", "system"),
                    p.get("message", ""),
                    json.dumps(p.get("data") or {}),
                    p.get("created_at") or now
                )
            )
    return sid