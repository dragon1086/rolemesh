"""
telegram_kanban.py — RoleMesh Telegram Kanban 명령 처리기

슬래시 명령어:
  /board              — 현재 칸반 보드 출력
  /add <제목>          — 새 태스크 추가 (TODO)
  /done <id>          — 태스크 완료 처리
  /move <id> <열>      — 태스크 이동 (todo|doing|done)
  /tasks              — 전체 태스크 목록
  /cancel <id>        — 태스크 취소

저장소: rolemesh.db task_queue 테이블 (기존 스키마 재사용)
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
import uuid
from typing import Optional

# 칸반 열 정의
COLUMNS = {
    "todo":  "📌 TODO",
    "doing": "🔄 IN PROGRESS",
    "done":  "✅ DONE",
}
COLUMN_ALIASES = {
    "todo": "todo", "할일": "todo", "대기": "todo",
    "doing": "doing", "진행": "doing", "진행중": "doing", "wip": "doing",
    "done": "done", "완료": "done", "finish": "done", "finished": "done",
}


@dataclass
class Task:
    id: str
    title: str
    status: str
    created_at: str
    done_at: Optional[str] = None


class TelegramKanban:
    """Telegram 슬래시 명령으로 task_queue 테이블을 칸반처럼 운용."""

    KANBAN_SOURCE = "telegram_kanban"

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    # ── 명령 감지 ──────────────────────────────────────────────

    @staticmethod
    def is_kanban_command(message: str) -> bool:
        """슬래시로 시작하는 칸반 명령인지 확인."""
        text = (message or "").strip()
        cmds = ("/board", "/add", "/done", "/move", "/tasks", "/cancel")
        return any(text.startswith(c) for c in cmds)

    def handle(self, message: str) -> str:
        """명령 파싱 후 처리 결과를 문자열로 반환."""
        text = message.strip()
        parts = text.split(maxsplit=2)
        cmd = parts[0].lower()

        try:
            if cmd == "/board":
                return self._cmd_board()
            elif cmd == "/tasks":
                return self._cmd_tasks()
            elif cmd == "/add":
                title = " ".join(parts[1:]).strip() if len(parts) > 1 else ""
                return self._cmd_add(title)
            elif cmd == "/done":
                task_id = parts[1] if len(parts) > 1 else ""
                return self._cmd_done(task_id)
            elif cmd == "/cancel":
                task_id = parts[1] if len(parts) > 1 else ""
                return self._cmd_cancel(task_id)
            elif cmd == "/move":
                if len(parts) < 3:
                    return "사용법: /move <id> <todo|doing|done>"
                task_id = parts[1]
                column = COLUMN_ALIASES.get(parts[2].lower())
                if not column:
                    return f"❌ 알 수 없는 열: '{parts[2]}'\n가능한 값: todo, doing, done"
                return self._cmd_move(task_id, column)
            else:
                return "❓ 알 수 없는 명령어"
        except (ValueError, IndexError):
            return f"❌ 잘못된 명령어 형식: `{text}`"
        except Exception as e:
            return f"❌ 오류: {e}"

    # ── 명령 구현 ──────────────────────────────────────────────

    def _cmd_board(self) -> str:
        """칸반 보드 출력 (todo/doing/done 열)."""
        tasks = self._fetch_active_tasks()
        board: dict[str, list[Task]] = {"todo": [], "doing": [], "done": []}
        for t in tasks:
            col = t.status if t.status in board else "todo"
            board[col].append(t)

        lines = ["📋 *RoleMesh 칸반 보드*\n"]
        for col, label in COLUMNS.items():
            items = board[col]
            lines.append(f"{label} ({len(items)})")
            if items:
                for t in items[-5:]:  # 최근 5개만
                    lines.append(f"  #{t.id} {t.title}")
            else:
                lines.append("  (없음)")
            lines.append("")

        lines.append("_명령어: /add <태스크> | /done <id> | /move <id> <열>_")
        return "\n".join(lines)

    def _cmd_tasks(self) -> str:
        """전체 태스크 목록 (완료 포함)."""
        tasks = self._fetch_all_tasks(limit=20)
        if not tasks:
            return "📋 태스크 없음"
        lines = ["📋 *전체 태스크 목록*\n"]
        for t in tasks:
            icon = {"todo": "📌", "doing": "🔄", "done": "✅"}.get(t.status, "❓")
            lines.append(f"{icon} #{t.id} [{t.status}] {t.title}")
        return "\n".join(lines)

    def _cmd_add(self, title: str) -> str:
        """새 태스크 추가."""
        if not title:
            return "사용법: /add <태스크 제목>"
        task_id = self._insert_task(title)
        return f"📌 태스크 추가됨!\n#{task_id} {title}\n\n이동: /move {task_id} doing"

    def _cmd_done(self, task_id: str) -> str:
        """태스크 완료 처리."""
        task = self._get_task(task_id)
        if not task:
            return f"❌ #{task_id} 태스크를 찾을 수 없어"
        self._update_status(task_id, "done", done=True)
        return f"✅ 완료!\n#{task_id} {task.title}"

    def _cmd_cancel(self, task_id: str) -> str:
        """태스크 취소."""
        task = self._get_task(task_id)
        if not task:
            return f"❌ #{task_id} 태스크를 찾을 수 없어"
        self._update_status(task_id, "cancelled")
        return f"🗑 취소됨\n#{task_id} {task.title}"

    def _cmd_move(self, task_id: str, column: str) -> str:
        """태스크 열 이동."""
        task = self._get_task(task_id)
        if not task:
            return f"❌ #{task_id} 태스크를 찾을 수 없어"
        done = column == "done"
        self._update_status(task_id, column, done=done)
        label = COLUMNS.get(column, column)
        return f"{label}\n#{task_id} {task.title} → {column}"

    # ── DB 헬퍼 ───────────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _fetch_active_tasks(self) -> list[Task]:
        """todo/doing/done 상태 태스크만."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, title, status, created_at, done_at FROM task_queue "
                "WHERE source = ? AND status IN ('todo','doing','done') "
                "ORDER BY id DESC LIMIT 50",
                (self.KANBAN_SOURCE,),
            ).fetchall()
        return [Task(**dict(r)) for r in rows]

    def _fetch_all_tasks(self, limit: int = 20) -> list[Task]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, title, status, created_at, done_at FROM task_queue "
                "WHERE source = ? ORDER BY id DESC LIMIT ?",
                (self.KANBAN_SOURCE, limit),
            ).fetchall()
        return [Task(**dict(r)) for r in rows]

    def _get_task(self, task_id: str) -> Optional[Task]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id, title, status, created_at, done_at FROM task_queue WHERE id = ?",
                (task_id,),
            ).fetchone()
        return Task(**dict(row)) if row else None

    def _insert_task(self, title: str) -> str:
        task_id = str(uuid.uuid4())[:8]  # 짧은 id (8자)
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO task_queue (id, title, status, source, created_at) VALUES (?, ?, 'todo', ?, ?)",
                (task_id, title, self.KANBAN_SOURCE, now),
            )
            conn.commit()
        return task_id

    def _update_status(self, task_id: str, status: str, done: bool = False) -> None:
        now = datetime.now(timezone.utc).isoformat()
        done_at = now if done else None
        with self._conn() as conn:
            conn.execute(
                "UPDATE task_queue SET status = ?, done_at = ? WHERE id = ?",
                (status, done_at, task_id),
            )
            conn.commit()
