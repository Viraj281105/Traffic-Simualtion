import sqlite3

from fastapi.testclient import TestClient

from src.database.db import DB_PATH, init_db
from src.database.replay_dao import ReplayDAO, _safe_json_loads
from src.main import app

client = TestClient(app)


def test_replay_dao_crud() -> None:
    """Tests save, get, list_all, and delete operations of ReplayDAO."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        config = {"simulation": {"duration": 30.0}}
        metrics = {"throughput": 50, "averageWaitTime": 5.2}

        # Save
        replay_id = ReplayDAO.save(conn, "Morning Peak Run", config, metrics)
        assert replay_id is not None

        # Get
        replay = ReplayDAO.get(conn, replay_id)
        assert replay is not None
        assert replay["id"] == replay_id
        assert replay["name"] == "Morning Peak Run"
        assert replay["config"] == config
        assert replay["metrics"] == metrics

        # Get nonexistent
        assert ReplayDAO.get(conn, "nonexistent-id") is None

        # List all
        replays = ReplayDAO.list_all(conn, limit=10, offset=0)
        assert any(r["id"] == replay_id for r in replays)

        # Delete
        assert ReplayDAO.delete(conn, replay_id) is True
        assert ReplayDAO.get(conn, replay_id) is None
        assert ReplayDAO.delete(conn, replay_id) is False

    finally:
        conn.close()


def test_replay_dao_edge_cases() -> None:
    """Tests name sanitization, pagination limits, and corrupted JSON resilience."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        # Empty or whitespace name falls back to "Saved Replay"
        r1 = ReplayDAO.save(conn, "   ", {}, {})
        loaded1 = ReplayDAO.get(conn, r1)
        assert loaded1 is not None
        assert loaded1["name"] == "Saved Replay"

        # Safe json loads resilience
        assert _safe_json_loads("{invalid json") == {}
        assert _safe_json_loads(None) == {}

        # Negative / boundary pagination doesn't crash
        results = ReplayDAO.list_all(conn, limit=-5, offset=-1)
        assert isinstance(results, list)

        # Cleanup
        ReplayDAO.delete(conn, r1)
    finally:
        conn.close()


def test_replay_api_endpoints() -> None:
    """Tests API endpoints for saving, listing, fetching by ID, and deleting replays."""
    payload = {
        "name": "API Replay Test",
        "config": {"simulation": {"duration": 10.0}},
        "metrics": {"throughput": 20},
    }

    # POST save replay
    res = client.post("/api/v1/replays", json=payload)
    assert res.status_code == 200
    replay_id = res.json()["replay_id"]

    # GET by ID
    res_get = client.get(f"/api/v1/replays/{replay_id}")
    assert res_get.status_code == 200
    assert res_get.json()["name"] == "API Replay Test"

    # GET 404
    res_404 = client.get("/api/v1/replays/nonexistent-id-999")
    assert res_404.status_code == 404

    # GET list
    res_list = client.get("/api/v1/replays")
    assert res_list.status_code == 200
    assert any(r["id"] == replay_id for r in res_list.json())

    # DELETE
    res_del = client.delete(f"/api/v1/replays/{replay_id}")
    assert res_del.status_code == 200

    # DELETE 404
    res_del_404 = client.delete(f"/api/v1/replays/{replay_id}")
    assert res_del_404.status_code == 404
