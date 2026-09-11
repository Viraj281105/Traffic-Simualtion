from typing import Any, Dict

from fastapi.testclient import TestClient

from src.main import app, simulations_db

client = TestClient(app)


def test_api_simulation_new_valid() -> None:
    """Verifies that a valid configuration successfully registers a new simulation."""
    config: Dict[str, Any] = {
        "simulation": {
            "timeStep": 0.1,
            "duration": 300,
            "warmupTime": 30.0,
        },
        "geometry": {
            "intersectionType": "fixed_time_signal",
        },
        "controller": {
            "greenTime": 30,
            "yellowTime": 4,
            "allRedTime": 2,
        },
    }
    response = client.post("/api/simulation/new", json=config)
    assert response.status_code == 200
    data = response.json()
    assert "simulationId" in data
    assert "configId" in data
    assert data["status"] == "initialized"


def test_api_simulation_new_invalid_constraints() -> None:
    """Verifies that configurations violating schema/Pydantic parameter constraints fail with HTTP 422."""
    # Invalid: duration < 1, greenTime < 5, yellowTime > 8
    config_invalid: Dict[str, Any] = {
        "simulation": {
            "timeStep": 0.1,
            "duration": 0,  # invalid: minimum 1
            "warmupTime": 30.0,
        },
        "geometry": {
            "intersectionType": "fixed_time_signal",
        },
        "controller": {
            "greenTime": 2,  # invalid: minimum 5
            "yellowTime": 12,  # invalid: maximum 8
            "allRedTime": 2,
        },
    }
    response = client.post("/api/simulation/new", json=config_invalid)
    assert response.status_code == 422
    errors = response.json()["detail"]
    assert len(errors) > 0


def test_api_simulation_new_canonical_duration_fields_reach_controller() -> None:
    """Regression for the straightRightDuration/yellowDuration/allRedDuration
    mismatch: ControllerSection previously had no declared fields for these
    canonical names, so Pydantic silently dropped them and the typed
    POST /api/simulation/new path always fell back to the greenTime/
    yellowTime/allRedTime defaults regardless of what a client sent. They
    must now survive validation and reach the actual controller instance
    with the exact values submitted."""
    config: Dict[str, Any] = {
        "simulation": {"timeStep": 0.1, "duration": 300, "warmupTime": 30.0},
        "geometry": {"intersectionType": "fixed_time_signal"},
        "controller": {
            "straightRightDuration": 25.0,
            "leftDuration": 7.0,
            "yellowDuration": 6.0,
            "allRedDuration": 3.0,
        },
    }
    response = client.post("/api/simulation/new", json=config)
    assert response.status_code == 200
    sim_id = response.json()["simulationId"]

    controller = simulations_db[sim_id]["controller"]
    assert controller.straight_right_duration == 25.0
    assert controller.left_duration == 7.0
    assert controller.yellow_duration == 6.0
    assert controller.all_red_duration == 3.0


def test_api_simulations_green_duration_alias_reaches_controller() -> None:
    """The greenDuration alias, now schema-declared, must reach the
    controller via the raw-dict /api/v1/simulations path when it is the
    only green-duration key present.

    Note: greenDuration cannot take effect via the typed
    POST /api/simulation/new path even now — ControllerSection.greenTime
    has a non-Optional default (30.0), so it is always present in
    ScenarioConfiguration's dump, and FixedTimeSignalController's existing
    precedence (straightRightDuration > greenTime > greenDuration, see
    06-scenario-configuration-contract.md §2.6.1) always resolves greenTime
    first on that path. That precedence order predates this batch and is
    left unchanged — this test targets the one path where greenDuration
    alone is actually meaningful."""
    config: Dict[str, Any] = {
        "simulation": {"timeStep": 0.1, "duration": 300, "warmupTime": 30.0},
        "geometry": {"intersectionType": "fixed_time_signal"},
        "controller": {"greenDuration": 22.0},
    }
    response = client.post("/api/v1/simulations", json=config)
    assert response.status_code == 201
    sim_id = response.json()["simulationId"]

    controller = simulations_db[sim_id]["controller"]
    assert controller.straight_right_duration == 22.0


def test_api_simulation_invalid_phase_sequence_entry_returns_400() -> None:
    """An unsupported phaseSequence entry (schema-valid as a plain string,
    but not a recognized '<group>_<green|yellow>' or 'all_red' token) must
    surface as a 400, not an unhandled 500."""
    config: Dict[str, Any] = {
        "simulation": {"timeStep": 0.1, "duration": 300, "warmupTime": 30.0},
        "geometry": {"intersectionType": "fixed_time_signal"},
        "controller": {"phaseSequence": ["ns_green", "not_a_real_phase"]},
    }
    response = client.post("/api/v1/simulations", json=config)
    assert response.status_code == 400
