import threading
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.core.enums import SimulationStatus
from src.main import (
    MAX_CONCURRENT_SIMULATIONS,
    app,
    simulations_db,
    simulations_lock,
)

client = TestClient(app)


def _valid_config() -> Dict[str, Any]:
    return {
        "simulation": {"timeStep": 0.1, "duration": 300, "warmupTime": 0.0},
        "geometry": {
            "intersectionType": "fixed_time_signal",
            "intersectionCenter": {"x": 0.0, "y": 0.0},
            "boundingRadius": 15.0,
        },
        "controller": {
            "greenDuration": 30,
            "yellowDuration": 5,
            "allRedDuration": 2,
        },
        "vehicleGeneration": {
            "stopSpeedThreshold": 0.1,
            "waitSpeedThreshold": 0.5,
        },
    }


def _create_mock_entry(status: SimulationStatus, created_at: float) -> Dict[str, Any]:
    mock_engine = MagicMock()
    mock_engine.status = status
    return {
        "engine": mock_engine,
        "collector": MagicMock(),
        "controller": MagicMock(),
        "config_id": "cfg-mock",
        "buffer": MagicMock(),
        "created_at": created_at,
    }


@pytest.fixture(autouse=True)
def clean_registry() -> Any:
    """Ensure simulations_db is clean before and after each test."""
    with simulations_lock:
        simulations_db.clear()
    yield
    with simulations_lock:
        simulations_db.clear()


def test_concurrent_creates_cannot_exceed_capacity_limit() -> None:
    """Proves that concurrent creation requests synchronized via a barrier cannot
    race past the capacity check to exceed MAX_CONCURRENT_SIMULATIONS."""
    num_threads = 8
    # Pre-fill registry with 49 active simulations (only 1 slot remaining)
    with simulations_lock:
        for i in range(MAX_CONCURRENT_SIMULATIONS - 1):
            simulations_db[f"active_{i}"] = _create_mock_entry(
                SimulationStatus.RUNNING, 100.0 + i
            )

    barrier = threading.Barrier(num_threads)
    results: List[int] = []
    results_lock = threading.Lock()

    def worker() -> None:
        barrier.wait()
        # TestClient is thread-safe for ASGI requests
        res = client.post("/api/v1/simulations", json=_valid_config())
        with results_lock:
            results.append(res.status_code)

    threads = [threading.Thread(target=worker) for _ in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Exactly 1 thread must succeed (201), and all other threads must receive 429
    assert results.count(201) == 1
    assert results.count(429) == num_threads - 1
    with simulations_lock:
        assert len(simulations_db) == MAX_CONCURRENT_SIMULATIONS


def test_concurrent_creates_with_atomic_eviction() -> None:
    """Proves that when registry is full with some completed simulations, concurrent
    creates safely evict completed entries without iteration race conditions
    (RuntimeError: dictionary changed size during iteration) or exceeding capacity."""
    num_threads = 6
    # Fill registry to 50: 48 active, 2 completed
    with simulations_lock:
        for i in range(48):
            simulations_db[f"active_{i}"] = _create_mock_entry(
                SimulationStatus.RUNNING, 100.0 + i
            )
        simulations_db["completed_oldest"] = _create_mock_entry(
            SimulationStatus.COMPLETED, 10.0
        )
        simulations_db["completed_second"] = _create_mock_entry(
            SimulationStatus.COMPLETED, 20.0
        )

    barrier = threading.Barrier(num_threads)
    results: List[int] = []
    results_lock = threading.Lock()

    def worker() -> None:
        barrier.wait()
        res = client.post("/api/v1/simulations", json=_valid_config())
        with results_lock:
            results.append(res.status_code)

    threads = [threading.Thread(target=worker) for _ in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Exactly 2 completed simulations could be evicted, so exactly 2 creates succeed
    assert results.count(201) == 2
    assert results.count(429) == num_threads - 2
    with simulations_lock:
        assert len(simulations_db) == MAX_CONCURRENT_SIMULATIONS
        assert "completed_oldest" not in simulations_db
        assert "completed_second" not in simulations_db


def test_concurrent_deletes_atomic_behavior() -> None:
    """Proves that concurrent delete requests for the same simulation ID
    result in exactly one 200 and one 404, never an unhandled KeyError / 500."""
    # Create a completed simulation entry
    sim_id = "deletable_sim"
    with simulations_lock:
        simulations_db[sim_id] = _create_mock_entry(SimulationStatus.COMPLETED, 100.0)

    num_threads = 4
    barrier = threading.Barrier(num_threads)
    results: List[int] = []
    results_lock = threading.Lock()

    def worker() -> None:
        barrier.wait()
        res = client.delete(f"/api/v1/simulations/{sim_id}")
        with results_lock:
            results.append(res.status_code)

    threads = [threading.Thread(target=worker) for _ in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Exactly one delete succeeds; all others receive 404
    assert results.count(200) == 1
    assert results.count(404) == num_threads - 1
    with simulations_lock:
        assert sim_id not in simulations_db


def test_simulations_lock_not_held_during_simulation_execution() -> None:
    """Verifies that simulations_lock is released while simulations are running,
    allowing concurrent creates/lookups without lock contention."""
    res = client.post("/api/v1/simulations", json=_valid_config())
    assert res.status_code == 201
    sim_id = res.json()["simulationId"]

    # Start simulation
    res_start = client.post(f"/api/v1/simulations/{sim_id}/control", json={"action": "start"})
    assert res_start.status_code == 200

    # simulations_lock must be free (not locked) while the simulation is running
    # An RLock acquired by another thread without blocking proves it's free
    acquired = []

    def check_lock() -> None:
        can_acquire = simulations_lock.acquire(blocking=False)
        if can_acquire:
            simulations_lock.release()
            acquired.append(True)
        else:
            acquired.append(False)

    t = threading.Thread(target=check_lock)
    t.start()
    t.join()

    assert acquired == [True]

    # Stop simulation
    client.post(f"/api/v1/simulations/{sim_id}/control", json={"action": "stop"})
