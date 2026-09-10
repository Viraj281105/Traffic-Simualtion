import sqlite3

from src.database.dao import ConfigurationDAO, RunMetricsDAO, SimulationRunDAO
from src.database.db import DB_PATH, get_db_connection, init_db


def test_database_crud_operations() -> None:
    """Verifies that we can insert, select, and delete configurations, runs, and metrics from SQLite."""
    init_db()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        # 1. Config DAO Save & Get
        config_id = "test_cfg_1"
        config_data = {"test_key": "test_value"}
        ConfigurationDAO.save(conn, config_id, config_data)
        retrieved_config = ConfigurationDAO.get(conn, config_id)
        assert retrieved_config == config_data

        # 2. Run DAO Save & Get
        run_id = "test_run_1"
        SimulationRunDAO.save(conn, run_id, "completed", 12.5)
        retrieved_run = SimulationRunDAO.get(conn, run_id)
        assert retrieved_run is not None
        assert retrieved_run["status"] == "completed"
        assert retrieved_run["elapsed"] == 12.5

        # 3. Metrics DAO Save & Get
        metrics_data = {"throughput": 15, "wait_time": 4.2}
        RunMetricsDAO.save(conn, run_id, 10, metrics_data)
        retrieved_metrics = RunMetricsDAO.get_all_for_run(conn, run_id)
        assert len(retrieved_metrics) == 1
        assert retrieved_metrics[0]["tick"] == 10
        assert retrieved_metrics[0]["metrics"] == metrics_data

    finally:
        conn.close()


def test_database_save_commits_immediately() -> None:
    """Verifies DAO save() methods commit their own write (callers no longer
    need to remember to call conn.commit() themselves — see dao.py)."""
    init_db()
    conn = sqlite3.connect(DB_PATH)

    # First ensure rollback_run_1 doesn't exist
    conn.execute("DELETE FROM simulation_runs WHERE id = 'rollback_run_1';")
    conn.commit()

    try:
        # No explicit conn.commit() after this — save() must commit itself.
        SimulationRunDAO.save(conn, "rollback_run_1", "running", 0.0)
    finally:
        conn.close()

    # Verify the write is visible from a brand new connection, proving it
    # was actually committed rather than left pending on the closed one.
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        run = SimulationRunDAO.get(conn, "rollback_run_1")
        assert run is not None
        assert run["status"] == "running"
    finally:
        conn.close()


def test_database_save_rolls_back_on_failure() -> None:
    """Verifies a failed DAO save() does not leave a partially-written row."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    conn.execute("DELETE FROM configurations WHERE id = 'bad_cfg';")
    conn.commit()

    try:
        # A config value that cannot be JSON-serialized makes json.dumps()
        # raise before the INSERT is attempted; save() must not leave a
        # dangling transaction or a partial row behind.
        class Unserializable:
            pass

        try:
            ConfigurationDAO.save(conn, "bad_cfg", {"bad": Unserializable()})
            raise AssertionError("expected save() to raise")
        except TypeError:
            pass

        assert ConfigurationDAO.get(conn, "bad_cfg") is None
    finally:
        conn.close()


def test_get_db_connection_and_missing_records() -> None:
    init_db()
    with get_db_connection() as conn:
        # Missing config returns None
        missing_cfg = ConfigurationDAO.get(conn, "nonexistent_config_id_123")
        assert missing_cfg is None

        # Missing run returns None
        missing_run = SimulationRunDAO.get(conn, "nonexistent_run_id_123")
        assert missing_run is None
