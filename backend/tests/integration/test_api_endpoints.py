from datetime import datetime
from typing import Any, Dict

from fastapi.testclient import TestClient

from src.main import _resolve_snapshot_interval, app

client = TestClient(app)


def test_api_config_validation() -> None:
    # Valid config
    config: Dict[str, Any] = {
        "simulation": {
            "timeStep": 0.1,
            "duration": 300,
            "warmupTime": 30.0,
        },
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
    # Validate configuration
    response = client.post("/api/v1/configs/validate", json=config)
    assert response.status_code == 200
    assert response.json()["valid"] is True


def test_api_lifecycle_and_ws_stream() -> None:
    config: Dict[str, Any] = {
        "simulation": {
            "timeStep": 0.1,
            "duration": 300,
            "warmupTime": 0.0,
        },
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
    # 1. Create Simulation
    res_create = client.post("/api/v1/simulations", json=config)
    assert res_create.status_code == 201
    sim_id = res_create.json()["simulationId"]

    # 2. Start control request
    res_start = client.post(
        f"/api/v1/simulations/{sim_id}/control", json={"action": "start"}
    )
    assert res_start.status_code == 200
    assert res_start.json()["status"] == "running"

    # 3. WebSocket stream checks
    with client.websocket_connect(f"/ws/v1/stream?simulationId={sim_id}") as websocket:
        data = websocket.receive_json()
        assert "simulationStatus" in data
        assert "tick" in data

    # 4. Pause control request
    res_pause = client.post(
        f"/api/v1/simulations/{sim_id}/control", json={"action": "pause"}
    )
    assert res_pause.status_code == 200
    assert res_pause.json()["status"] == "paused"

    # 5. Stop control request
    res_stop = client.post(
        f"/api/v1/simulations/{sim_id}/control", json={"action": "stop"}
    )
    assert res_stop.status_code == 200
    assert res_stop.json()["status"] == "completed"


def test_control_invalid_state_transition_returns_409_not_500() -> None:
    """engine.start() raises RuntimeError for an invalid transition (e.g.
    "start" on an already-running simulation). Previously this propagated
    as an unhandled 500 instead of the documented 409
    INVALID_STATE_TRANSITION (docs/architecture/08-communication-contract.md
    §6.2)."""
    config: Dict[str, Any] = {
        "simulation": {"timeStep": 0.1, "duration": 300, "warmupTime": 0.0},
        "geometry": {"intersectionType": "fixed_time_signal"},
        "controller": {"greenDuration": 30, "yellowDuration": 5, "allRedDuration": 2},
        "vehicleGeneration": {"stopSpeedThreshold": 0.1, "waitSpeedThreshold": 0.5},
    }
    sim_id = client.post("/api/v1/simulations", json=config).json()["simulationId"]

    res_first_start = client.post(
        f"/api/v1/simulations/{sim_id}/control", json={"action": "start"}
    )
    assert res_first_start.status_code == 200

    res_second_start = client.post(
        f"/api/v1/simulations/{sim_id}/control", json={"action": "start"}
    )
    assert res_second_start.status_code == 409
    error = res_second_start.json()["error"]
    assert error["code"] == "INVALID_STATE_TRANSITION"


def test_error_responses_use_documented_envelope() -> None:
    """Every HTTPException-driven error response must follow the
    documented shape (docs/architecture/08-communication-contract.md
    §6.1): {"error": {"code", "message", "details", "timestamp"}} —
    not FastAPI's bare {"detail": "..."} default."""
    res_404 = client.get("/api/v1/simulations/does-not-exist")
    assert res_404.status_code == 404
    body = res_404.json()
    assert "detail" not in body
    assert set(body.keys()) == {"error"}
    error = body["error"]
    assert error["code"] == "NOT_FOUND"
    assert isinstance(error["message"], str) and error["message"]
    assert "details" in error
    assert isinstance(error["timestamp"], str) and error["timestamp"]

    res_400 = client.post(
        "/api/v1/simulations", json={"simulation": "not-a-valid-object"}
    )
    assert res_400.status_code == 400
    error_400 = res_400.json()["error"]
    assert error_400["code"] == "VALIDATION_ERROR"
    assert isinstance(error_400["message"], str) and error_400["message"]


def test_ws_snapshot_interval_honors_configured_frequency() -> None:
    """/ws/v1/stream previously ignored simulation.snapshotFrequency and
    always streamed at a hardcoded 10Hz, despite the field being a
    documented (docs/architecture/08-communication-contract.md §5.1),
    schema-validated part of the config contract."""
    # Explicit frequency is honored.
    assert _resolve_snapshot_interval(
        {"simulation": {"snapshotFrequency": 20.0}}
    ) == 0.05
    # Missing field falls back to the documented 10Hz default.
    assert _resolve_snapshot_interval({"simulation": {}}) == 0.1
    assert _resolve_snapshot_interval({}) == 0.1
    # Out-of-range / malformed values are clamped to the documented [1, 60]Hz
    # hard limits rather than raising or streaming at an absurd rate.
    assert _resolve_snapshot_interval(
        {"simulation": {"snapshotFrequency": 1000.0}}
    ) == 1.0 / 60.0
    assert _resolve_snapshot_interval(
        {"simulation": {"snapshotFrequency": 0.0}}
    ) == 1.0
    assert _resolve_snapshot_interval(
        {"simulation": {"snapshotFrequency": "not-a-number"}}
    ) == 0.1


def _lifecycle_config() -> Dict[str, Any]:
    return {
        # randomSeed is explicit (rather than omitted) so the posted config
        # is never mutated in place by auto-seed generation (see
        # VehicleSpawner.__init__) — keeps body["config"] equality checks
        # deterministic below.
        "simulation": {
            "timeStep": 0.1,
            "duration": 300,
            "warmupTime": 0.0,
            "randomSeed": 42,
        },
        "geometry": {"intersectionType": "fixed_time_signal"},
        "controller": {"greenDuration": 30, "yellowDuration": 5, "allRedDuration": 2},
        "vehicleGeneration": {"stopSpeedThreshold": 0.1, "waitSpeedThreshold": 0.5},
    }


def test_create_simulation_response_includes_createdAt_and_config() -> None:
    """POST /api/v1/simulations: createdAt and config are additive fields
    (docs/architecture/08-communication-contract.md §3.3). Existing fields
    (simulationId/configId/status) must be unchanged, and the new fields
    must carry real, unambiguous values rather than placeholders."""
    config = _lifecycle_config()
    res = client.post("/api/v1/simulations", json=config)
    assert res.status_code == 201
    body = res.json()

    # Existing fields untouched.
    assert isinstance(body["simulationId"], str) and body["simulationId"]
    assert isinstance(body["configId"], str) and body["configId"]
    assert body["status"] == "initialized"

    # New additive fields.
    assert isinstance(body["createdAt"], str) and body["createdAt"]
    # Must be a real, parseable timestamp in the API's existing UTC-Z
    # convention (see http_exception_handler's error "timestamp" field),
    # not an arbitrary string.
    parsed = datetime.fromisoformat(body["createdAt"].replace("Z", "+00:00"))
    assert parsed.tzinfo is not None

    # config is the exact configuration the simulation was created from,
    # not a placeholder or a re-derived/partial copy.
    assert body["config"] == config


def test_get_simulation_status_still_returns_only_documented_current_fields() -> None:
    """GET /api/v1/simulations/{id} was intentionally left unchanged in
    this pass (no unambiguous engine-state field was worth adding) — this
    guards against silently regressing elapsed/tick or growing speculative
    fields (progress/totalTicks/etc.) without a real source of truth."""
    sim_id = client.post("/api/v1/simulations", json=_lifecycle_config()).json()[
        "simulationId"
    ]
    res = client.get(f"/api/v1/simulations/{sim_id}")
    assert res.status_code == 200
    body = res.json()
    assert set(body.keys()) == {"simulationId", "status", "elapsed", "tick"}
    assert body["simulationId"] == sim_id
    assert isinstance(body["elapsed"], (int, float))
    assert isinstance(body["tick"], int)


def test_control_response_includes_previous_and_current_status_and_timestamp() -> None:
    """POST /api/v1/simulations/{id}/control: simulationId/previousStatus/
    currentStatus/timestamp are additive fields
    (docs/architecture/08-communication-contract.md §3.5). previousStatus
    must reflect the state *before* the transition, currentStatus the
    actual resulting engine state, and the existing "status" field must be
    unchanged."""
    sim_id = client.post("/api/v1/simulations", json=_lifecycle_config()).json()[
        "simulationId"
    ]

    res_start = client.post(
        f"/api/v1/simulations/{sim_id}/control", json={"action": "start"}
    )
    assert res_start.status_code == 200
    body_start = res_start.json()
    assert body_start["status"] == "running"  # existing field, unchanged
    assert body_start["simulationId"] == sim_id
    assert body_start["previousStatus"] == "initialized"
    assert body_start["currentStatus"] == "running"
    parsed = datetime.fromisoformat(body_start["timestamp"].replace("Z", "+00:00"))
    assert parsed.tzinfo is not None

    res_pause = client.post(
        f"/api/v1/simulations/{sim_id}/control", json={"action": "pause"}
    )
    assert res_pause.status_code == 200
    body_pause = res_pause.json()
    assert body_pause["previousStatus"] == "running"
    assert body_pause["currentStatus"] == "paused"
    assert body_pause["status"] == "paused"


def test_control_failed_transition_still_returns_existing_error_shape() -> None:
    """A rejected transition (409 INVALID_STATE_TRANSITION) must keep
    returning the existing enveloped error response — never a
    success-shaped payload with previousStatus/currentStatus."""
    sim_id = client.post("/api/v1/simulations", json=_lifecycle_config()).json()[
        "simulationId"
    ]
    first = client.post(
        f"/api/v1/simulations/{sim_id}/control", json={"action": "start"}
    )
    assert first.status_code == 200

    second = client.post(
        f"/api/v1/simulations/{sim_id}/control", json={"action": "start"}
    )
    assert second.status_code == 409
    body = second.json()
    assert set(body.keys()) == {"error"}
    assert body["error"]["code"] == "INVALID_STATE_TRANSITION"
    assert "previousStatus" not in body
    assert "currentStatus" not in body
