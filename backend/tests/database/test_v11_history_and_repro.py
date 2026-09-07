import sqlite3

import pytest
from fastapi.testclient import TestClient

import src.database.db as db_module
from src.database.dao import SimulationRunDAO
from src.database.db import get_db_connection, init_db
from src.main import app


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    """Provides a fresh isolated SQLite database with v1.1 schema."""
    db_file = str(tmp_path / "test_v11.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_file)
    init_db()
    return db_file


def test_sqlite_pragmas_and_wal(test_db):
    """Verifies that SQLite WAL mode, foreign keys, and busy timeout are active."""
    for conn in get_db_connection():
        # Journal mode should be WAL
        mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        assert mode.lower() == "wal"

        # Foreign keys should be ON
        fk = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
        assert fk == 1

        # Busy timeout should be 5000
        timeout = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
        assert timeout == 5000


def test_schema_migration_safe_upgrade(tmp_path, monkeypatch):
    """Simulates an existing legacy database and verifies safe schema migration."""
    legacy_db_file = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(legacy_db_file)
    # Create old-style simulation_runs table missing new columns
    conn.execute(
        """
        CREATE TABLE simulation_runs (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            elapsed REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    conn.execute(
        "INSERT INTO simulation_runs (id, status, elapsed) VALUES ('legacy_1', 'completed', 30.0);"
    )
    conn.commit()
    conn.close()

    # Point DB_PATH to legacy DB and run init_db()
    monkeypatch.setattr(db_module, "DB_PATH", legacy_db_file)
    init_db()

    for migrated_conn in get_db_connection():
        cursor = migrated_conn.execute("PRAGMA table_info(simulation_runs);")
        cols = {row[1] for row in cursor.fetchall()}
        assert "intersection_type" in cols
        assert "random_seed" in cols
        assert "arrival_rate" in cols
        assert "duration" in cols
        assert "batch_id" in cols
        assert "config_json" in cols
        assert "summary_metrics_json" in cols

        # Verify old record survived untouched
        row = migrated_conn.execute(
            "SELECT id, status, elapsed FROM simulation_runs WHERE id = 'legacy_1';"
        ).fetchone()
        assert row["id"] == "legacy_1"
        assert row["status"] == "completed"


def test_dao_enriched_persistence_and_filtering(test_db):
    """Tests saving and filtering runs with exact seed, type, config, and metrics."""
    for conn in get_db_connection():
        cfg_sig = {
            "simulation": {"duration": 10.0, "timeStep": 0.1, "randomSeed": 777},
            "geometry": {"intersectionType": "fixed_time_signal"},
            "traffic": {"arrivalRate": 0.4},
        }
        metrics_sig = {"averageDelay": 12.5, "throughput": 85.0, "totalStops": 10}

        SimulationRunDAO.save(
            conn,
            run_id="run_sig_777",
            status="completed",
            elapsed=10.0,
            intersection_type="fixed_time_signal",
            random_seed=777,
            arrival_rate=0.4,
            duration=10.0,
            batch_id="batch_alpha",
            config=cfg_sig,
            summary_metrics=metrics_sig,
        )

        cfg_rnd = {
            "simulation": {"duration": 10.0, "timeStep": 0.1, "randomSeed": 777},
            "geometry": {"intersectionType": "roundabout"},
            "traffic": {"arrivalRate": 0.4},
        }
        metrics_rnd = {"averageDelay": 8.0, "throughput": 95.0, "totalStops": 3}

        SimulationRunDAO.save(
            conn,
            run_id="run_rnd_777",
            status="completed",
            elapsed=10.0,
            intersection_type="roundabout",
            random_seed=777,
            arrival_rate=0.4,
            duration=10.0,
            batch_id="batch_alpha",
            config=cfg_rnd,
            summary_metrics=metrics_rnd,
        )
        conn.commit()

        # 1. Retrieve single run
        fetched = SimulationRunDAO.get(conn, "run_sig_777")
        assert fetched is not None
        assert fetched["random_seed"] == 777
        assert fetched["intersection_type"] == "fixed_time_signal"
        assert fetched["config"]["geometry"]["intersectionType"] == "fixed_time_signal"
        assert fetched["summary_metrics"]["averageDelay"] == 12.5

        # 2. Filter by intersection_type
        signals = SimulationRunDAO.list_runs(
            conn, intersection_type="fixed_time_signal"
        )
        assert len(signals) == 1
        assert signals[0]["id"] == "run_sig_777"

        roundabouts = SimulationRunDAO.list_runs(conn, intersection_type="roundabout")
        assert len(roundabouts) == 1
        assert roundabouts[0]["id"] == "run_rnd_777"

        # 3. Filter by seed
        seed_runs = SimulationRunDAO.list_runs(conn, seed=777)
        assert len(seed_runs) == 2

        # 4. Filter by batch_id
        batch_runs = SimulationRunDAO.list_runs(conn, batch_id="batch_alpha")
        assert len(batch_runs) == 2


def test_api_runs_compare_and_history(test_db):
    """Tests the /api/v1/study/history/runs and /compare endpoints."""
    client = TestClient(app)

    # Populate two runs with identical seed for A/B comparison
    for conn in get_db_connection():
        SimulationRunDAO.save(
            conn,
            run_id="comp_sig_1",
            status="completed",
            elapsed=20.0,
            intersection_type="fixed_time_signal",
            random_seed=999,
            arrival_rate=0.5,
            duration=20.0,
            batch_id="comp_batch",
            config={"simulation": {"randomSeed": 999}},
            summary_metrics={
                "averageDelay": 20.0,
                "throughput": 100.0,
                "totalStops": 15,
            },
        )
        SimulationRunDAO.save(
            conn,
            run_id="comp_rnd_1",
            status="completed",
            elapsed=20.0,
            intersection_type="roundabout",
            random_seed=999,
            arrival_rate=0.5,
            duration=20.0,
            batch_id="comp_batch",
            config={"simulation": {"randomSeed": 999}},
            summary_metrics={
                "averageDelay": 12.0,
                "throughput": 120.0,
                "totalStops": 4,
            },
        )
        conn.commit()

    # 1. Test filtered history endpoint
    res_history = client.get(
        "/api/v1/study/history/runs?intersection_type=fixed_time_signal"
    )
    assert res_history.status_code == 200
    runs = res_history.json()
    assert len(runs) >= 1
    assert runs[0]["id"] == "comp_sig_1"
    assert runs[0]["random_seed"] == 999

    # 2. Test compare endpoint
    res_comp = client.post(
        "/api/v1/study/history/runs/compare",
        json={"runIdA": "comp_sig_1", "runIdB": "comp_rnd_1"},
    )
    assert res_comp.status_code == 200
    comp_data = res_comp.json()
    assert comp_data["identicalSeed"] is True
    assert comp_data["seed"] == 999
    assert comp_data["comparison"]["winner"] == "roundabout"
    assert comp_data["comparison"]["delayDelta"] == -8.0
    assert comp_data["comparison"]["delayDeltaPercent"] == -40.0
    assert comp_data["comparison"]["throughputDelta"] == 20.0

    # 3. Compare with nonexistent run
    res_404 = client.post(
        "/api/v1/study/history/runs/compare",
        json={"runIdA": "comp_sig_1", "runIdB": "nonexistent_run_id"},
    )
    assert res_404.status_code == 404


def test_api_run_reproduce(test_db):
    """Tests that a stored run can be reproduced headlessly with deterministic output matching."""
    client = TestClient(app)

    # 1. Create a minimal deterministic scenario configuration
    repro_config = {
        "simulation": {
            "timeStep": 0.1,
            "duration": 5.0,
            "warmupTime": 1.0,
            "randomSeed": 54321,
        },
        "roads": {
            "approachLength": 100.0,
            "laneWidth": 3.5,
            "lanesPerApproach": {"north": 1, "south": 1, "east": 1, "west": 1},
        },
        "traffic": {
            "arrivalRate": 0.3,
            "arrivalDistribution": "poisson",
        },
        "geometry": {
            "intersectionType": "fixed_time_signal",
            "intersectionCenter": {"x": 0.0, "y": 0.0},
        },
        "controller": {
            "greenDuration": 15,
            "yellowDuration": 3,
            "allRedDuration": 2,
        },
        "vehicleGeneration": {
            "stopSpeedThreshold": 0.1,
            "waitSpeedThreshold": 0.5,
        },
    }

    # First run reproduction once to get baseline metrics
    for conn in get_db_connection():
        SimulationRunDAO.save(
            conn,
            run_id="repro_test_run",
            status="completed",
            elapsed=5.0,
            intersection_type="fixed_time_signal",
            random_seed=54321,
            arrival_rate=0.3,
            duration=5.0,
            config=repro_config,
            summary_metrics={},  # initially empty
        )
        conn.commit()

    # Call reproduce endpoint
    res_first = client.post("/api/v1/study/history/runs/repro_test_run/reproduce")
    assert res_first.status_code == 200
    first_data = res_first.json()
    metrics_generated = first_data["reproducedMetrics"]

    # Now update run with the known metrics and reproduce again to verify bit-exact determinism
    for conn in get_db_connection():
        SimulationRunDAO.save(
            conn,
            run_id="repro_test_run",
            status="completed",
            elapsed=5.0,
            intersection_type="fixed_time_signal",
            random_seed=54321,
            arrival_rate=0.3,
            duration=5.0,
            config=repro_config,
            summary_metrics=metrics_generated,
        )
        conn.commit()

    res_second = client.post("/api/v1/study/history/runs/repro_test_run/reproduce")
    assert res_second.status_code == 200
    second_data = res_second.json()
    assert second_data["isDeterministic"] is True
    assert len(second_data["discrepancies"]) == 0
    assert second_data["seed"] == 54321


def test_user_seed_preservation(test_db):
    """Verifies that an explicit user seed is never clobbered when setting config or resetting."""
    client = TestClient(app)

    # Send config with an explicit user seed
    res_cfg = client.post(
        "/api/simulation/config",
        json={
            "intersectionType": "fixed_time_signal",
            "intersectionSize": 15.0,
            "laneWidth": 3.5,
            "lanesNorth": 2,
            "lanesSouth": 2,
            "lanesEast": 2,
            "lanesWest": 2,
            "randomSeed": 88888,
        },
    )
    assert res_cfg.status_code == 200
    assert res_cfg.json()["randomSeed"] == 88888

    # Reset dual simulation — seed must NOT be clobbered
    res_reset = client.post("/api/simulation/dual/reset")
    assert res_reset.status_code == 200
    assert res_reset.json()["randomSeed"] == 88888
