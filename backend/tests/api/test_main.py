import pytest

try:
    from fastapi.testclient import TestClient

    from src.main import app

    client = TestClient(app)
except ImportError:
    pytest.skip("FastAPI or app module not available yet", allow_module_level=True)


def test_get_single_vehicle() -> None:
    """Test that the single-vehicle endpoint responds correctly and advances state."""
    # Reset and start the simulation first
    client.post("/api/simulation/reset")
    client.post("/api/simulation/start")

    # First request
    response = client.get("/api/simulation/single-vehicle")
    assert response.status_code == 200
    data = response.json()
    assert data["vehicle_id"] == "vehicle_1"
    assert "position" in data
    assert "speed" in data
    assert "acceleration" in data
    assert "x" in data
    assert "y" in data
    assert "heading" in data
    assert "state" in data
    assert "lane_id" in data

    # Second request should advance the vehicle position
    response2 = client.get("/api/simulation/single-vehicle")
    assert response2.status_code == 200
    data2 = response2.json()
    assert data2["position"] > data["position"]

    # Reset simulation state
    client.post("/api/simulation/reset")


def test_simulation_history() -> None:
    """Test that simulation creations record history snapshots and permit history scrubbing."""
    import time

    config = {
        "simulation": {"timeStep": 0.1, "duration": 10, "warmupTime": 0.0},
        "geometry": {
            "intersectionType": "fixed_time_signal",
            "intersectionCenter": {"x": 0.0, "y": 0.0},
            "boundingRadius": 15.0,
        },
        "controller": {"greenDuration": 30, "yellowDuration": 5, "allRedDuration": 2},
        "vehicleGeneration": {"stopSpeedThreshold": 0.1, "waitSpeedThreshold": 0.5},
    }
    # 1. Create simulation
    response = client.post("/api/v1/simulations", json=config)
    assert response.status_code == 201
    sim_id = response.json()["simulationId"]

    # 2. Control start
    response_start = client.post(
        f"/api/v1/simulations/{sim_id}/control", json={"action": "start"}
    )
    assert response_start.status_code == 200

    # 3. Wait for background ticks
    time.sleep(0.5)

    # 4. Stop simulation
    client.post(f"/api/v1/simulations/{sim_id}/control", json={"action": "stop"})

    # 5. Fetch history
    history_res = client.get(f"/api/v1/simulations/{sim_id}/history")
    assert history_res.status_code == 200
    history = history_res.json()
    assert len(history) > 0

    # 6. Fetch specific frame
    first_tick = history[0]["tick"]
    frame_res = client.get(f"/api/v1/simulations/{sim_id}/history/{first_tick}")
    assert frame_res.status_code == 200
    assert frame_res.json()["tick"] == first_tick
