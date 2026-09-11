import pytest
from fastapi.testclient import TestClient

import src.main as main_module
from src.main import (
    app,
    get_or_create_live_simulation,
    simulations_db,
    single_veh,
)

client = TestClient(app)


def test_health_check() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_single_vehicle_full_flow() -> None:
    # 1. Status when stopped
    client.post("/api/simulation/reset")
    status_res = client.get("/api/simulation/status")
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "stopped"

    # 2. Start
    start_res = client.post("/api/simulation/start")
    assert start_res.status_code == 200
    assert start_res.json()["status"] == "running"

    status_running = client.get("/api/simulation/status")
    assert status_running.json()["status"] == "running"

    # 3. Poll single-vehicle multiple times and wrap around (>300.0)
    single_veh.position = 299.0
    veh_res = client.get("/api/simulation/single-vehicle")
    assert veh_res.status_code == 200
    # Next poll should trigger position > 300 wrap-around
    single_veh.position = 301.0
    veh_wrap = client.get("/api/simulation/single-vehicle")
    assert veh_wrap.status_code == 200
    assert veh_wrap.json()["position"] == 0.0

    # 4. Stop
    stop_res = client.post("/api/simulation/stop")
    assert stop_res.status_code == 200
    assert stop_res.json()["status"] == "stopped"


def test_config_validation_route() -> None:
    # Valid config
    valid_cfg = {
        "simulation": {"timeStep": 0.1, "duration": 10},
        "geometry": {"intersectionType": "fixed_time_signal"},
    }
    res_val = client.post("/api/v1/configs/validate", json=valid_cfg)
    assert res_val.status_code == 200
    assert res_val.json()["valid"] is True

    # Invalid config against schema if schema loaded
    res_inv = client.post(
        "/api/v1/configs/validate", json={"simulation": "not_an_object"}
    )
    assert res_inv.status_code == 200

    # Validation when schema is empty
    orig_schema = main_module.CONFIG_SCHEMA
    main_module.CONFIG_SCHEMA = {}
    res_empty_schema = client.post("/api/v1/configs/validate", json={})
    assert res_empty_schema.json()["valid"] is True
    main_module.CONFIG_SCHEMA = orig_schema


def test_simulations_lifecycle_and_tick_callbacks() -> None:
    # 1. Create Fixed-Time Signal simulation
    cfg_signal = {
        "simulation": {"timeStep": 0.1, "duration": 30, "warmupTime": 0.0},
        "geometry": {"intersectionType": "fixed_time_signal"},
        "controller": {
            "type": "fixed_time_signal",
            "greenDuration": 10,
            "yellowDuration": 3,
            "allRedDuration": 2,
        },
    }
    res_sig = client.post("/api/v1/simulations", json=cfg_signal)
    assert res_sig.status_code == 201
    sig_sim_id = res_sig.json()["simulationId"]

    # Step engine to invoke tick_callback
    sim_data = simulations_db[sig_sim_id]
    sim_data["engine"].step()

    # 2. Create Roundabout simulation via /api/simulation/new
    cfg_roundabout = {
        "simulation": {"timeStep": 0.1, "duration": 30, "warmupTime": 0.0},
        "geometry": {"intersectionType": "roundabout"},
        "controller": {"type": "roundabout"},
    }
    res_round = client.post("/api/simulation/new", json=cfg_roundabout)
    assert res_round.status_code == 200
    round_sim_id = res_round.json()["simulationId"]
    sim_data_round = simulations_db[round_sim_id]
    sim_data_round["engine"].step()

    # 3. Invalid schema on creation
    res_bad = client.post("/api/v1/simulations", json={"simulation": "invalid_type"})
    assert res_bad.status_code in (400, 422)

    # 4. Step engine before stop to populate history buffer
    sim_data["engine"].step()
    first_tick = sim_data["buffer"].get_all()[0]["tick"]
    frame_res = client.get(f"/api/v1/simulations/{sig_sim_id}/history/{first_tick}")
    assert frame_res.status_code == 200
    assert (
        client.get(f"/api/v1/simulations/{sig_sim_id}/history/99999").status_code == 404
    )
    assert client.get("/api/v1/simulations/unknown_id/history/0").status_code == 404

    # 5. Control simulation: start, pause, resume, stop, invalid action, not found
    for action in ["start", "pause", "resume", "stop"]:
        ctrl_res = client.post(
            f"/api/v1/simulations/{sig_sim_id}/control", json={"action": action}
        )
        assert ctrl_res.status_code == 200

    bad_action = client.post(
        f"/api/v1/simulations/{sig_sim_id}/control", json={"action": "fly"}
    )
    assert bad_action.status_code == 400

    not_found_ctrl = client.post(
        "/api/v1/simulations/unknown_id/control", json={"action": "start"}
    )
    assert not_found_ctrl.status_code == 404

    # 6. Get simulation status & metrics
    get_res = client.get(f"/api/v1/simulations/{sig_sim_id}")
    assert get_res.status_code == 200
    assert client.get("/api/v1/simulations/unknown_id").status_code == 404

    met_res = client.get(f"/api/v1/simulations/{sig_sim_id}/metrics")
    assert met_res.status_code == 200
    assert client.get("/api/v1/simulations/unknown_id/metrics").status_code == 404

    # 7. History & history frames
    hist_res = client.get(f"/api/v1/simulations/{sig_sim_id}/history")
    assert hist_res.status_code == 200
    assert client.get("/api/v1/simulations/unknown_id/history").status_code == 404

    # 8. Reports: json and csv
    rep_json = client.get(f"/api/v1/simulations/{sig_sim_id}/report?format=json")
    assert rep_json.status_code == 200
    assert "finalMetrics" in rep_json.json()

    rep_csv = client.get(f"/api/v1/simulations/{sig_sim_id}/report?format=csv")
    assert rep_csv.status_code == 200
    assert client.get("/api/v1/simulations/unknown_id/report").status_code == 404


def test_dashboard_config_rejects_unknown_intersection_type() -> None:
    """/api/simulation/config previously accepted any intersectionType
    string silently: the controller-config shape it builds is chosen by
    `== "fixed_time_signal"`, while create_controller() separately checks
    `== "roundabout"` — the two checks disagree for anything else, so a
    typo silently discarded the submitted signal-timing parameters instead
    of failing. It must now reject unrecognized values with a 400, like
    the versioned creation endpoints already do."""
    res = client.post("/api/simulation/config", json={"intersectionType": "bogus"})
    assert res.status_code == 400
    error = res.json()["error"]
    assert "bogus" in error["message"]
    assert "fixed_time_signal" in error["message"]
    assert "roundabout" in error["message"]

    # A missing intersectionType still falls back to the documented default.
    res_default = client.post("/api/simulation/config", json={})
    assert res_default.status_code == 200


def test_dashboard_config_default_signal_durations_match_canonical_contract() -> None:
    """A fixed-time-signal dashboard config with no greenDuration/
    yellowDuration must resolve to the same canonical defaults
    (greenTime=30, yellowTime=4) as the versioned creation endpoints —
    DEFAULT_CONFIG previously used mismatched values (15/3)."""
    res = client.post(
        "/api/simulation/config", json={"intersectionType": "fixed_time_signal"}
    )
    assert res.status_code == 200
    live_sim = get_or_create_live_simulation()
    controller = live_sim["controller"]
    assert controller.straight_right_duration == 30.0
    assert controller.yellow_duration == 4.0
    assert controller.all_red_duration == 2.0


def test_dashboard_config_rejects_malformed_duration() -> None:
    """A non-numeric `duration` previously escaped as an uncaught
    ValueError -> raw 500 (float("not-a-number") raises). It must be
    rejected as a 400 client error, matching how /api/v1/simulations
    already surfaces a bad config as a 400 instead of a 500."""
    res = client.post("/api/simulation/config", json={"duration": "not-a-number"})
    assert res.status_code == 400
    error = res.json()["error"]
    assert "duration" in error["message"].lower()

    # A non-numeric type entirely (e.g. a list) must also be a 400, not a
    # TypeError leaking out as a 500.
    res_list = client.post("/api/simulation/config", json={"duration": [1, 2]})
    assert res_list.status_code == 400


def test_dashboard_config_rejects_out_of_range_duration() -> None:
    """duration must be bounded to [1, 3600] seconds, the same range the
    versioned API enforces via SimulationSection.duration (ge=1, le=3600).
    This legacy endpoint builds its config by hand rather than through
    that Pydantic model, so it previously accepted any value at all."""
    below_min = client.post("/api/simulation/config", json={"duration": 0.5})
    assert below_min.status_code == 400
    assert "duration" in below_min.json()["error"]["message"].lower()

    above_max = client.post("/api/simulation/config", json={"duration": 3601})
    assert above_max.status_code == 400
    assert "duration" in above_max.json()["error"]["message"].lower()


def test_dashboard_config_accepts_boundary_durations() -> None:
    """The bounds are inclusive: exactly 1 and exactly 3600 seconds must
    both still be accepted and applied to the live config as-is. Calls
    update_simulation_config() directly against a dedicated session
    (rather than through the shared TestClient, whose cookie-scoped
    session isn't the same one a bare `get_or_create_live_simulation()`
    call would read back) for a precise, deterministic assertion on the
    resulting duration."""
    from src.main import (
        _get_or_create_session,
        _live_session_var,
        update_simulation_config,
    )

    session_min = _get_or_create_session("test-duration-boundary-min")
    token_min = _live_session_var.set(session_min)
    try:
        result_min = update_simulation_config({"duration": 1})
    finally:
        _live_session_var.reset(token_min)
    assert result_min["status"] == "ok"
    assert session_min.current_live_config["simulation"]["duration"] == 1.0

    session_max = _get_or_create_session("test-duration-boundary-max")
    token_max = _live_session_var.set(session_max)
    try:
        result_max = update_simulation_config({"duration": 3600})
    finally:
        _live_session_var.reset(token_max)
    assert result_max["status"] == "ok"
    assert session_max.current_live_config["simulation"]["duration"] == 3600.0


def test_dashboard_config_rejects_malformed_non_duration_numeric_field() -> None:
    """Every other numeric field this endpoint coerces by hand
    (laneWidth, lanesNorth/South/East/West, arrivalRate, intersectionSize,
    greenDuration/leftDuration/yellowDuration/allRedDuration, criticalGap,
    followUpTime) previously escaped a malformed value as an uncaught
    ValueError/TypeError -> raw 500. Spot-check representative fields from
    each affected section land as a 400 instead."""
    res_lane_width = client.post(
        "/api/simulation/config", json={"laneWidth": "wide"}
    )
    assert res_lane_width.status_code == 400
    assert "Invalid configuration" in res_lane_width.json()["error"]["message"]

    res_lanes_north = client.post(
        "/api/simulation/config", json={"lanesNorth": "many"}
    )
    assert res_lanes_north.status_code == 400

    res_arrival_rate = client.post(
        "/api/simulation/config", json={"arrivalRate": {}}
    )
    assert res_arrival_rate.status_code == 400

    res_green_duration = client.post(
        "/api/simulation/config",
        json={"intersectionType": "fixed_time_signal", "greenDuration": "long"},
    )
    assert res_green_duration.status_code == 400

    res_critical_gap = client.post(
        "/api/simulation/config",
        json={"intersectionType": "roundabout", "criticalGap": "wide"},
    )
    assert res_critical_gap.status_code == 400


def test_live_simulation_and_dual_simulation_endpoints() -> None:
    # 1. Get active vehicles
    act_res = client.get("/api/simulation/active-vehicles")
    assert act_res.status_code == 200
    assert isinstance(act_res.json(), list)

    # 2. Update config and reset live sim
    cfg_payload = {
        "intersectionType": "roundabout",
        "intersectionSize": 20.0,
        "laneWidth": 3.0,
        "lanesNorth": 2,
        "lanesSouth": 2,
        "lanesEast": 1,
        "lanesWest": 1,
    }
    cfg_res = client.post("/api/simulation/config", json=cfg_payload)
    assert cfg_res.status_code == 200

    # Step live engine tick callback
    live_sim = get_or_create_live_simulation()
    live_sim["engine"].step()

    # Play and pause live simulation
    play_res = client.post("/api/simulation/play")
    assert play_res.status_code == 200
    pause_res = client.post("/api/simulation/pause")
    assert pause_res.status_code == 200
    # Play again from paused (resume)
    play_res2 = client.post("/api/simulation/play")
    assert play_res2.status_code == 200

    # 3. Dual simulation endpoints
    dual_play = client.post("/api/simulation/dual/play")
    assert dual_play.status_code == 200

    dual_pause = client.post("/api/simulation/dual/pause")
    assert dual_pause.status_code == 200

    dual_status = client.get("/api/simulation/dual/status")
    assert dual_status.status_code == 200

    dual_reset = client.post("/api/simulation/dual/reset")
    assert dual_reset.status_code == 200


def test_websocket_streams() -> None:
    # 1. /ws/v1/stream with invalid sim ID
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/v1/stream?simulationId=nonexistent") as ws:
            ws.receive_json()

    # 2. /ws/v1/stream with valid sim ID
    cfg = {
        "simulation": {"duration": 10, "timeStep": 0.1, "warmupTime": 0.0},
        "geometry": {"intersectionType": "fixed_time_signal"},
        "controller": {
            "type": "fixed_time_signal",
            "greenDuration": 10,
            "yellowDuration": 3,
            "allRedDuration": 2,
        },
    }
    res = client.post("/api/v1/simulations", json=cfg)
    assert res.status_code == 201
    sim_id = res.json()["simulationId"]

    with client.websocket_connect(f"/ws/v1/stream?simulationId={sim_id}") as ws:
        frame = ws.receive_json()
        assert frame["schemaVersion"] == "1.0.0"

    # 3. /ws/simulation/dual
    with client.websocket_connect("/ws/simulation/dual") as ws:
        dual_frame = ws.receive_json()
        assert "signal" in dual_frame
        assert "roundabout" in dual_frame
