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


def test_generate_random_seed_does_not_consume_shared_global_random_state() -> None:
    """_generate_random_seed() is the single authority for the live
    dashboard's auto-generated seeds — previously duplicated as a bare
    `random.randint(1, 10000000)` at 5 separate call sites in main.py, all
    drawing from the shared global `random` module. It must instead use a
    private Random instance, like VehicleSpawner and
    DualSimulationOrchestrator already do for the same reason (see their
    own fixes): otherwise generating a dashboard seed silently perturbs
    the global module's sequence for any other code relying on it."""
    import random as random_module

    from src.main import _generate_random_seed

    random_module.seed(12345)
    expected_sequence = [random_module.random() for _ in range(5)]

    random_module.seed(12345)
    actual_sequence = []
    for _ in range(5):
        _generate_random_seed()
        actual_sequence.append(random_module.random())

    assert actual_sequence == expected_sequence


def test_live_session_nested_config_isolation() -> None:
    """Regression test: verify that _LiveSession receives an isolated deep copy
    of DEFAULT_CONFIG so that mutating nested configuration (e.g. injecting an
    auto-generated randomSeed during simulation initialization) does not leak
    into DEFAULT_CONFIG or other sessions."""
    from src.main import DEFAULT_CONFIG, _LiveSession
    from src.roads.network import RoadNetwork
    from src.vehicles.spawner import VehicleSpawner

    # 1. Initialize two fresh sessions without explicit configuration
    session1 = _LiveSession()
    session2 = _LiveSession()

    # 2. Verify nested configs are distinct objects (independent)
    assert session1.current_live_config is not DEFAULT_CONFIG
    assert session2.current_live_config is not DEFAULT_CONFIG
    assert session1.current_live_config is not session2.current_live_config

    assert (
        session1.current_live_config["simulation"]
        is not session2.current_live_config["simulation"]
    )
    assert (
        session1.current_live_config["simulation"]
        is not DEFAULT_CONFIG["simulation"]
    )
    assert (
        session2.current_live_config["simulation"]
        is not DEFAULT_CONFIG["simulation"]
    )

    assert (
        session1.current_live_config["controller"]
        is not session2.current_live_config["controller"]
    )
    assert (
        session1.current_live_config["vehicleGeneration"]
        is not session2.current_live_config["vehicleGeneration"]
    )

    # 3. Mutate nested simulation config in session1
    session1.current_live_config["simulation"]["randomSeed"] = 99999
    session1.current_live_config["simulation"]["duration"] = 12345.0

    # 4. Verify session2 and DEFAULT_CONFIG remain completely unmutated
    assert "randomSeed" not in DEFAULT_CONFIG["simulation"]
    assert "randomSeed" not in session2.current_live_config["simulation"]
    assert DEFAULT_CONFIG["simulation"]["duration"] == 600
    assert session2.current_live_config["simulation"]["duration"] == 600

    # 5. Verify that VehicleSpawner mutating simulation config does not pollute DEFAULT_CONFIG
    network = RoadNetwork()
    spawner_session = _LiveSession()
    assert "randomSeed" not in spawner_session.current_live_config["simulation"]
    assert "randomSeed" not in DEFAULT_CONFIG["simulation"]

    # Spawner runs without pre-set randomSeed and generates one into its config dict
    spawner = VehicleSpawner(spawner_session.current_live_config, network)
    generated_seed = spawner_session.current_live_config["simulation"].get(
        "randomSeed"
    )
    assert generated_seed is not None
    assert generated_seed == spawner.random_seed

    # Global DEFAULT_CONFIG must remain unpolluted
    assert "randomSeed" not in DEFAULT_CONFIG["simulation"]

    # A subsequent fresh session must also be unpolluted
    subsequent_session = _LiveSession()
    assert (
        "randomSeed"
        not in subsequent_session.current_live_config["simulation"]
    )
