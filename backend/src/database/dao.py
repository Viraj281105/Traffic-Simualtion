import json
import sqlite3
from typing import Any, Dict, Optional, cast


class ConfigurationDAO:
    """DAO for managing simulation configuration items."""

    @staticmethod
    def save(conn: sqlite3.Connection, config_id: str, config: Dict[str, Any]) -> None:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO configurations (id, config_json) VALUES (?, ?);",
            (config_id, json.dumps(config)),
        )

    @staticmethod
    def get(conn: sqlite3.Connection, config_id: str) -> Optional[Dict[str, Any]]:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT config_json FROM configurations WHERE id = ?;", (config_id,)
        )
        row = cursor.fetchone()
        if row:
            return cast(Dict[str, Any], json.loads(row["config_json"]))
        return None


class SimulationRunDAO:
    """DAO for tracking simulation runs with rich metadata, seeds, configs, and summary metrics."""

    @staticmethod
    def save(
        conn: sqlite3.Connection,
        run_id: str,
        status: str,
        elapsed: float,
        intersection_type: str = "unknown",
        random_seed: Optional[int] = None,
        arrival_rate: float = 0.5,
        duration: Optional[float] = None,
        batch_id: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        summary_metrics: Optional[Dict[str, Any]] = None,
    ) -> None:
        cursor = conn.cursor()
        config_str = json.dumps(config) if config is not None else "{}"
        metrics_str = (
            json.dumps(summary_metrics) if summary_metrics is not None else "{}"
        )
        seed_val = random_seed if random_seed is not None else 0
        dur_val = duration if duration is not None else elapsed

        cursor.execute(
            """
            INSERT OR REPLACE INTO simulation_runs (
                id, status, elapsed, intersection_type, random_seed, arrival_rate,
                duration, batch_id, config_json, summary_metrics_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                run_id,
                status,
                elapsed,
                intersection_type,
                seed_val,
                arrival_rate,
                dur_val,
                batch_id,
                config_str,
                metrics_str,
            ),
        )

    @staticmethod
    def get(conn: sqlite3.Connection, run_id: str) -> Optional[Dict[str, Any]]:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, status, elapsed, intersection_type, random_seed, arrival_rate,
                   duration, batch_id, config_json, summary_metrics_json, created_at
            FROM simulation_runs WHERE id = ?;
            """,
            (run_id,),
        )
        row = cursor.fetchone()
        if row:
            data = dict(row)
            try:
                data["config"] = json.loads(data.get("config_json") or "{}")
            except Exception:
                data["config"] = {}
            try:
                data["summary_metrics"] = json.loads(
                    data.get("summary_metrics_json") or "{}"
                )
            except Exception:
                data["summary_metrics"] = {}
            return data
        return None

    @staticmethod
    def list_runs(
        conn: sqlite3.Connection,
        limit: int = 50,
        offset: int = 0,
        intersection_type: Optional[str] = None,
        seed: Optional[int] = None,
        batch_id: Optional[str] = None,
    ) -> list[Dict[str, Any]]:
        cursor = conn.cursor()
        query = """
            SELECT id, status, elapsed, intersection_type, random_seed, arrival_rate,
                   duration, batch_id, config_json, summary_metrics_json, created_at
            FROM simulation_runs
        """
        conditions = []
        params: list[Any] = []

        if intersection_type:
            conditions.append("intersection_type = ?")
            params.append(intersection_type)
        if seed is not None:
            conditions.append("random_seed = ?")
            params.append(seed)
        if batch_id:
            conditions.append("batch_id = ?")
            params.append(batch_id)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?;"
        params.extend([limit, offset])

        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        result = []
        for r in rows:
            item = dict(r)
            try:
                item["config"] = json.loads(item.get("config_json") or "{}")
            except Exception:
                item["config"] = {}
            try:
                item["summary_metrics"] = json.loads(
                    item.get("summary_metrics_json") or "{}"
                )
            except Exception:
                item["summary_metrics"] = {}
            result.append(item)
        return result


class RunMetricsDAO:
    """DAO for storing and retrieving time-series metrics snapshots."""

    @staticmethod
    def save(
        conn: sqlite3.Connection, run_id: str, tick: int, metrics: Dict[str, Any]
    ) -> None:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO run_metrics (run_id, tick, metrics_json) VALUES (?, ?, ?);",
            (run_id, tick, json.dumps(metrics)),
        )

    @staticmethod
    def get_all_for_run(conn: sqlite3.Connection, run_id: str) -> list[Dict[str, Any]]:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT tick, metrics_json FROM run_metrics WHERE run_id = ? ORDER BY tick ASC;",
            (run_id,),
        )
        rows = cursor.fetchall()
        return [
            {
                "tick": r["tick"],
                "metrics": cast(Dict[str, Any], json.loads(r["metrics_json"])),
            }
            for r in rows
        ]

    @staticmethod
    def get_latest_for_run(
        conn: sqlite3.Connection, run_id: str
    ) -> Optional[Dict[str, Any]]:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT tick, metrics_json FROM run_metrics WHERE run_id = ? ORDER BY tick DESC LIMIT 1;",
            (run_id,),
        )
        row = cursor.fetchone()
        if row:
            return {
                "tick": row["tick"],
                "metrics": cast(Dict[str, Any], json.loads(row["metrics_json"])),
            }
        return None


class SweepSessionDAO:
    """DAO for managing traffic volume sweep sessions and comparative benchmark experiments."""

    @staticmethod
    def save(
        conn: sqlite3.Connection,
        session_id: str,
        name: str,
        config: Dict[str, Any],
        results: Dict[str, Any],
    ) -> None:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO sweep_sessions (id, name, config_json, results_json) VALUES (?, ?, ?, ?);",
            (session_id, name, json.dumps(config), json.dumps(results)),
        )

    @staticmethod
    def get(conn: sqlite3.Connection, session_id: str) -> Optional[Dict[str, Any]]:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, config_json, results_json, created_at FROM sweep_sessions WHERE id = ?;",
            (session_id,),
        )
        row = cursor.fetchone()
        if row:
            return {
                "id": row["id"],
                "name": row["name"],
                "config": json.loads(row["config_json"]),
                "results": json.loads(row["results_json"]),
                "created_at": row["created_at"],
            }
        return None

    @staticmethod
    def list_sessions(
        conn: sqlite3.Connection, limit: int = 50, offset: int = 0
    ) -> list[Dict[str, Any]]:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, config_json, results_json, created_at FROM sweep_sessions ORDER BY created_at DESC LIMIT ? OFFSET ?;",
            (limit, offset),
        )
        rows = cursor.fetchall()
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "config": json.loads(r["config_json"]),
                "results": json.loads(r["results_json"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ]
