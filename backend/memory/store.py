"""
memory/store.py
────────────────
게임 세션별 대화 메모리를 관리하는 모듈.

저장하는 것:
  1. conversation history  — 세션별 전체 대화 (role, content, npc)
  2. known_facts           — 유저가 알아낸 단서/사실 (NPC가 "이미 아시는군요" 반응 가능)
  3. summary               — 대화가 길어지면 압축한 요약

SQLite를 쓰는 이유:
  게임을 껐다 켜도 세션 기억이 남아야 하기 때문.
  (인메모리 dict는 서버 재시작하면 사라짐)
"""

import sqlite3
import json
import os
from datetime import datetime
from typing import List, Dict, Optional

# db 파일 위치: backend/memory/sessions.db
DB_PATH = os.path.join(os.path.dirname(__file__), "sessions.db")


def _connect():
    """SQLite 연결. check_same_thread=False → FastAPI 멀티스레드 대응."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row  # 컬럼명으로 접근 가능하게
    return conn


def init_db():
    """
    서버 시작 시 1회 호출. 테이블이 없으면 생성.

    테이블 구조:
      sessions  — 세션별 메타데이터 (요약 등)
      messages  — 세션별 대화 기록
      facts     — 세션별 유저가 알아낸 단서
    """
    conn = _connect()
    cur = conn.cursor()

    # 세션 메타 (요약 저장)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            summary    TEXT DEFAULT '',
            created_at TEXT,
            updated_at TEXT
        )
    """)

    # 대화 기록
    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            npc        TEXT,
            role       TEXT,     -- 'user' or 'assistant'
            content    TEXT,
            created_at TEXT
        )
    """)

    # 유저가 알아낸 단서
    cur.execute("""
        CREATE TABLE IF NOT EXISTS facts (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            fact       TEXT,
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()


def _ensure_session(session_id: str):
    """세션이 없으면 새로 만든다."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT session_id FROM sessions WHERE session_id = ?", (session_id,))
    if cur.fetchone() is None:
        now = datetime.utcnow().isoformat()
        cur.execute(
            "INSERT INTO sessions (session_id, summary, created_at, updated_at) VALUES (?, '', ?, ?)",
            (session_id, now, now),
        )
        conn.commit()
    conn.close()


def add_message(session_id: str, npc: str, role: str, content: str):
    """대화 한 줄 저장 (유저 발화 or NPC 응답)."""
    _ensure_session(session_id)
    conn = _connect()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    cur.execute(
        "INSERT INTO messages (session_id, npc, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
        (session_id, npc, role, content, now),
    )
    cur.execute("UPDATE sessions SET updated_at = ? WHERE session_id = ?", (now, session_id))
    conn.commit()
    conn.close()


def get_recent_messages(session_id: str, npc: Optional[str] = None, limit: int = 6) -> List[Dict]:
    """
    최근 대화 N개 반환 (오래된 → 최신 순).

    npc를 지정하면 해당 NPC와의 대화만 (특정 NPC와의 맥락 유지용).
    지정 안 하면 세션 전체 대화 (유저의 전반적 행동 패턴 파악용).
    """
    conn = _connect()
    cur = conn.cursor()
    if npc:
        cur.execute(
            "SELECT role, content, npc FROM messages WHERE session_id = ? AND npc = ? "
            "ORDER BY id DESC LIMIT ?",
            (session_id, npc, limit),
        )
    else:
        cur.execute(
            "SELECT role, content, npc FROM messages WHERE session_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        )
    rows = cur.fetchall()
    conn.close()
    # DESC로 가져왔으니 뒤집어서 오래된 순으로
    return [dict(r) for r in reversed(rows)]


def get_summary(session_id: str) -> str:
    """세션의 대화 요약 반환 (없으면 빈 문자열)."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT summary FROM sessions WHERE session_id = ?", (session_id,))
    row = cur.fetchone()
    conn.close()
    return row["summary"] if row else ""


def set_summary(session_id: str, summary: str):
    """세션 요약 갱신."""
    _ensure_session(session_id)
    conn = _connect()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    cur.execute(
        "UPDATE sessions SET summary = ?, updated_at = ? WHERE session_id = ?",
        (summary, now, session_id),
    )
    conn.commit()
    conn.close()


def add_fact(session_id: str, fact: str):
    """유저가 알아낸 단서 저장 (중복 방지)."""
    _ensure_session(session_id)
    conn = _connect()
    cur = conn.cursor()
    # 이미 있는 fact면 저장 안 함
    cur.execute("SELECT id FROM facts WHERE session_id = ? AND fact = ?", (session_id, fact))
    if cur.fetchone() is None:
        now = datetime.utcnow().isoformat()
        cur.execute(
            "INSERT INTO facts (session_id, fact, created_at) VALUES (?, ?, ?)",
            (session_id, fact, now),
        )
        conn.commit()
    conn.close()


def get_facts(session_id: str) -> List[str]:
    """유저가 지금까지 알아낸 단서 목록."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT fact FROM facts WHERE session_id = ? ORDER BY id", (session_id,))
    rows = cur.fetchall()
    conn.close()
    return [r["fact"] for r in rows]


def count_messages(session_id: str) -> int:
    """세션 전체 메시지 수 (요약 트리거 판단용)."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS c FROM messages WHERE session_id = ?", (session_id,))
    row = cur.fetchone()
    conn.close()
    return row["c"] if row else 0