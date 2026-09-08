import json
import logging
import sqlite3
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _safe_json_loads(data: Optional[str]) -> Dict[str, Any]:
    if not data:
        return {}
    try:
        parsed = json.loads(data)
        if isinstance(parsed, dict):
            return parsed
        return {}
    except (json.JSONDecodeError, TypeError):
        logger.warning("Failed to decode JSON from database, returning empty dict")
        return {}


class ReplayDAO:
    """DAO for managing deterministic simulation replays (config + final metrics)."""

    @staticmethod
    def save(
        conn: sqlite3.Connection,
        name: str,
        config: Dict[str, Any],
        metrics: Dict[str, Any],
    ) -> str:
        replay_id = str(uuid.uuid4())
        clean_name = (name or "").strip() or "Saved Replay"
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO saved_replays (id, name, config_json, metrics_json)
            VALUES (?, ?, ?, ?);
            """,
            (replay_id, clean_name, json.dumps(config), json.dumps(metrics)),
        )
        conn.commit()
        return replay_id

    @staticmethod
    def get(conn: sqlite3.Connection, replay_id: str) -> Optional[Dict[str, Any]]:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, config_json, metrics_json, created_at FROM saved_replays WHERE id = ?;",
            (replay_id,),
        )
        row = cursor.fetchone()
        if row:
            return {
                "id": row["id"],
                "name": row["name"],
                "config": _safe_json_loads(row["config_json"]),
                "metrics": _safe_json_loads(row["metrics_json"]),
                "created_at": row["created_at"],
            }
        return None

    @staticmethod
    def list_all(
        conn: sqlite3.Connection, limit: int = 50, offset: int = 0
    ) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 200))
        safe_offset = max(0, int(offset))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, config_json, metrics_json, created_at FROM saved_replays ORDER BY created_at DESC LIMIT ? OFFSET ?;",
            (safe_limit, safe_offset),
        )
        rows = cursor.fetchall()
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "config": _safe_json_loads(r["config_json"]),
                "metrics": _safe_json_loads(r["metrics_json"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    @staticmethod
    def delete(conn: sqlite3.Connection, replay_id: str) -> bool:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM saved_replays WHERE id = ?;", (replay_id,))
        rows_affected = cursor.rowcount
        conn.commit()
        return rows_affected > 0
