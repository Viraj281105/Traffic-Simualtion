import asyncio
import csv
import io
import logging
import random
import traceback
import uuid
from pathlib import Path
from typing import Any, Dict

import jsonschema
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.controllers.factory import build_tick_callback, create_controller
from src.core.clock import Clock
from src.core.config_models import ScenarioConfiguration
from src.core.engine import SimulationEngine
from src.core.enums import SimulationStatus
from src.database.dao import RunMetricsDAO, SimulationRunDAO, SweepSessionDAO
from src.database.db import DB_PATH, get_db_connection, init_db
from src.metrics.collector import MetricCollector
from src.snapshot.buffer import SnapshotBuffer
from src.snapshot.builder import SnapshotBuilder
from src.snapshot.dual_orchestrator import DualSimulationOrchestrator
from src.study.report_generator import (
    generate_study_report_csv,
    generate_study_report_json,
)
from src.study.validation import run_invariant_checks, run_statistical_validation
from src.study.volume_sweep import run_volume_sweep_experiment

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Traffic Simulation Framework API", version="1.0.0")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for dev/testing ease
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Database
try:
    init_db()
    logger.info("Database initialized successfully.")
except Exception as e:
    logger.error(f"Failed to initialize database: {e}")


# ── Health check endpoint (used by Docker HEALTHCHECK) ───────────────────────
@app.get("/health")
def health_check() -> Dict[str, str]:
    return {"status": "healthy"}


# Load schemas for validation
SCHEMA_PATHS = [
    Path(__file__).resolve().parent.parent.parent
    / "shared"
    / "schemas"
    / "config.schema.json",
    Path("shared/schemas/config.schema.json"),
]

import json

CONFIG_SCHEMA: Dict[str, Any] = {}
for p in SCHEMA_PATHS:
    if p.is_file():
        try:
            with open(p, "r", encoding="utf-8") as f:
                CONFIG_SCHEMA = json.load(f)
            break
        except Exception:
            pass

# ── Global State for Multi-Vehicle Simulations ──────────────────────────────
# Dict mapping simulation_id -> { "engine": SimulationEngine, "collector": MetricCollector, "controller": Any }
simulations_db: Dict[str, Dict[str, Any]] = {}


def _get_simulation_or_404(sim_id: str) -> Dict[str, Any]:
    if sim_id not in simulations_db:
        raise HTTPException(status_code=404, detail="Simulation not found")
    return simulations_db[sim_id]


# ── Global State for Single-Vehicle Polling Mode (Sprint 2 UI compatibility) ──
class SingleVehicleState:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.vehicle_id = "vehicle_1"
        self.position = 0.0
        self.speed = 10.0
        self.acceleration = 0.0
        self.x = -150.0
        self.y = -3.5
        self.heading = 90.0
        self.state = "approaching"
        self.lane_id = "w_in_0"
        self.wait_time = 0.0
        self.stop_count = 0
        self.sim_time = 0.0
        self.tick = 0
        self.status = "stopped"


single_veh = SingleVehicleState()


# ── Pydantic Request/Response Models ────────────────────────────────────────
class ScenarioConfigInput(BaseModel):
    config: Dict[str, Any]


class ControlRequest(BaseModel):
    action: str  # start, pause, resume, stop


# ── Single-Vehicle Endpoints (Sprint 2/3 Compatibility) ─────────────────────
@app.get("/api/simulation/status")
def get_simulation_status() -> Dict[str, Any]:
    return {
        "status": single_veh.status,
        "sim_time": round(single_veh.sim_time, 2),
        "tick": single_veh.tick,
        "vehicle_state": single_veh.state,
        "message": "Ready" if single_veh.status == "stopped" else "Running",
    }


@app.post("/api/simulation/start")
def start_simulation() -> Dict[str, Any]:
    single_veh.status = "running"
    return {"status": "running", "message": "Simulation started"}


@app.post("/api/simulation/stop")
def stop_simulation() -> Dict[str, Any]:
    single_veh.status = "stopped"
    sim = get_or_create_live_simulation()
    engine = sim.get("engine")
    if engine is not None:
        try:
            engine.stop()
        except Exception as e:
            logger.error(f"Error stopping live engine: {e}")
    return {"status": "stopped", "message": "Simulation stopped"}


@app.post("/api/simulation/reset")
def reset_simulation() -> Dict[str, Any]:
    single_veh.reset()
    return {"status": "stopped", "message": "Simulation reset"}


@app.get("/api/simulation/single-vehicle")
def get_single_vehicle() -> Dict[str, Any]:
    if single_veh.status == "running":
        # Advance vehicle state
        dt = 0.1
        single_veh.tick += 1
        single_veh.sim_time += dt
        single_veh.position += single_veh.speed * dt
        single_veh.x += single_veh.speed * dt

        # Wrap around route for visual testing
        if single_veh.position > 300.0:
            single_veh.position = 0.0
            single_veh.x = -150.0

    return {
        "vehicle_id": single_veh.vehicle_id,
        "position": round(single_veh.position, 2),
        "speed": round(single_veh.speed, 2),
        "acceleration": round(single_veh.acceleration, 2),
        "x": round(single_veh.x, 2),
        "y": round(single_veh.y, 2),
        "heading": round(single_veh.heading, 1),
        "state": single_veh.state,
        "lane_id": single_veh.lane_id,
        "wait_time": round(single_veh.wait_time, 2),
        "stop_count": single_veh.stop_count,
        "sim_time": round(single_veh.sim_time, 2),
        "tick": single_veh.tick,
        "simulation_status": single_veh.status,
    }


@app.get("/api/simulation/active-vehicles")
def get_active_vehicles() -> list[dict[str, Any]]:
    sim = get_or_create_live_simulation()
    builder = sim["builder"]
    snapshot = builder.build()
    return [v for v in snapshot["vehicles"] if v["state"] != "exited"]


# ── Full Scenario Configuration Validation Route ────────────────────────────
@app.post("/api/v1/configs/validate")
def validate_config(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not CONFIG_SCHEMA:
        return {
            "valid": True,
            "message": "Schema validation skipped (schema not found)",
        }
    try:
        jsonschema.validate(instance=payload, schema=CONFIG_SCHEMA)
        return {"valid": True, "errors": []}
    except jsonschema.ValidationError as err:
        return {"valid": False, "errors": [err.message]}


# ── Full Simulation Lifecycle REST Routes ───────────────────────────────────
@app.post("/api/simulation/new")
def create_simulation_v2(payload: ScenarioConfiguration) -> Dict[str, Any]:
    config_dict = payload.model_dump(exclude_none=True)
    return create_simulation(config_dict)


@app.post("/api/v1/simulations")
def create_simulation(config: Dict[str, Any]) -> Dict[str, Any]:
    # Validate configuration
    if CONFIG_SCHEMA:
        try:
            jsonschema.validate(instance=config, schema=CONFIG_SCHEMA)
        except jsonschema.ValidationError as err:
            raise HTTPException(
                status_code=400, detail=f"Invalid configuration: {err.message}"
            )

    sim_id = str(uuid.uuid4())
    config_id = str(uuid.uuid4())

    # Ensure simulation section has a randomSeed if not provided
    if "simulation" not in config:
        config["simulation"] = {}
    if config["simulation"].get("randomSeed") is None:
        config["simulation"]["randomSeed"] = random.randint(1, 10000000)

    # Instantiate clock, engine, collector, and controller
    clock = Clock(time_step=config.get("simulation", {}).get("timeStep", 0.1))
    duration = config.get("simulation", {}).get("duration", 300)
    engine = SimulationEngine(clock, duration=duration, config=config)

    controller = create_controller(config, engine.network)
    engine.controller = controller

    collector = MetricCollector(config)
    builder = SnapshotBuilder(sim_id, config_id, engine, collector, controller)
    buffer = SnapshotBuffer(max_frames=1000)

    # Register tick callback on engine to update collector and controller
    engine.register_tick_callback(
        build_tick_callback(controller, clock, engine, collector, buffer, builder)
    )

    simulations_db[sim_id] = {
        "engine": engine,
        "collector": collector,
        "controller": controller,
        "config_id": config_id,
        "buffer": buffer,
    }

    return {
        "simulationId": sim_id,
        "configId": config_id,
        "status": engine.status.value.lower(),
    }


@app.post("/api/v1/simulations/{sim_id}/control")
def control_simulation(sim_id: str, payload: ControlRequest) -> Dict[str, Any]:
    sim = _get_simulation_or_404(sim_id)
    engine = sim["engine"]
    action = payload.action.lower()

    if action == "start":
        engine.start()
    elif action == "pause":
        engine.pause()
    elif action == "resume":
        engine.resume()
    elif action == "stop":
        engine.stop()
    else:
        raise HTTPException(status_code=400, detail="Invalid action")

    return {"status": engine.status.value.lower()}


@app.get("/api/v1/simulations/{sim_id}")
def get_simulation(sim_id: str) -> Dict[str, Any]:
    sim = _get_simulation_or_404(sim_id)
    engine = sim["engine"]
    return {
        "simulationId": sim_id,
        "status": engine.status.value.lower(),
        "elapsed": round(engine.clock.get_elapsed_time(), 2),
        "tick": engine.clock.get_tick_count(),
    }


@app.get("/api/v1/simulations/{sim_id}/metrics")
def get_simulation_metrics(sim_id: str) -> Dict[str, Any]:
    sim = _get_simulation_or_404(sim_id)
    engine = sim["engine"]
    collector: MetricCollector = sim["collector"]
    return collector.get_metrics(
        engine.clock.get_elapsed_time(),
        engine.pool.active_vehicles,
        engine.pool.exited_vehicles,
        engine.spawner.spawned_count if engine.spawner else 0,
    )


@app.get("/api/v1/simulations/{sim_id}/history")
def get_simulation_history(sim_id: str) -> list[dict[str, Any]]:
    sim = _get_simulation_or_404(sim_id)
    buffer: SnapshotBuffer = sim["buffer"]
    return buffer.get_all()


@app.get("/api/v1/simulations/{sim_id}/history/{tick}")
def get_simulation_history_tick(sim_id: str, tick: int) -> dict[str, Any]:
    sim = _get_simulation_or_404(sim_id)
    buffer: SnapshotBuffer = sim["buffer"]
    frame = buffer.get_frame(tick)
    if frame is None:
        raise HTTPException(
            status_code=404, detail=f"Frame at tick {tick} not found in buffer"
        )
    return frame


@app.get("/api/v1/simulations/{sim_id}/report")
def get_simulation_report(sim_id: str, format: str = "csv") -> Any:  # noqa: A002
    sim = _get_simulation_or_404(sim_id)
    engine = sim["engine"]
    collector = sim["collector"]

    # Get final metrics
    final_metrics = collector.get_metrics(
        engine.clock.get_elapsed_time(),
        engine.pool.active_vehicles,
        engine.pool.exited_vehicles,
        engine.spawner.spawned_count if engine.spawner else 0,
    )

    if format == "json":
        return {
            "simulationId": sim_id,
            "finalMetrics": final_metrics,
            "ticksCount": engine.clock.get_tick_count(),
        }

    output = io.StringIO()
    writer = csv.writer(output)

    # Write header
    writer.writerow(["Metric Name", "Value"])
    for key, value in final_metrics.items():
        if isinstance(value, dict):
            writer.writerow([key, json.dumps(value)])
        else:
            writer.writerow([key, value])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=simulation_{sim_id}_report.csv"
        },
    )


@app.websocket("/ws/v1/stream")
async def websocket_stream(websocket: WebSocket, simulationId: str) -> None:  # noqa: N803
    await websocket.accept()
    try:
        sim = _get_simulation_or_404(simulationId)
    except HTTPException:
        await websocket.close(code=1008, reason="Simulation not found")
        return

    engine = sim["engine"]
    collector = sim["collector"]
    controller = sim["controller"]
    config_id = sim["config_id"]

    builder = SnapshotBuilder(simulationId, config_id, engine, collector, controller)

    try:
        while True:
            # Generate and send state snapshot
            snapshot = builder.build()
            await websocket.send_json(snapshot)

            # Check if simulation complete
            if snapshot["simulationStatus"] in ("completed", "error"):
                break

            # Stream at 10Hz (matching dt = 0.1)
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        await websocket.close(code=1011, reason=str(e))


DEFAULT_CONFIG: Dict[str, Any] = {
    "simulation": {
        "timeStep": 0.1,
        "duration": 600,
        "warmupTime": 30.0,
    },
    "geometry": {
        "intersectionType": "fixed_time_signal",
        "intersectionCenter": {"x": 0.0, "y": 0.0},
        "boundingRadius": 15.0,
    },
    "controller": {
        "straightRightDuration": 15.0,
        "leftDuration": 5.0,
        "yellowDuration": 3.0,
        "allRedDuration": 2.0,
    },
    "vehicleGeneration": {
        "stopSpeedThreshold": 0.1,
        "waitSpeedThreshold": 0.5,
        "maxAcceleration": 3.0,
        "comfortDeceleration": 3.5,
        "desiredSpeed": {
            "min": 18.0,
            "max": 25.0,
        },
    },
}

current_live_config: Dict[str, Any] = DEFAULT_CONFIG.copy()
is_user_defined_seed: bool = False

live_sim_data: Dict[str, Any] = {
    "engine": None,
    "collector": None,
    "controller": None,
    "builder": None,
    "config_id": None,
}


def get_or_create_live_simulation() -> Dict[str, Any]:
    global current_live_config
    if live_sim_data["engine"] is None:
        clock = Clock(time_step=0.1)
        engine = SimulationEngine(clock, duration=300, config=current_live_config)
        controller = create_controller(current_live_config, engine.network)
        engine.controller = controller

        collector = MetricCollector(current_live_config)
        config_id = str(uuid.uuid4())
        builder = SnapshotBuilder("live_sim", config_id, engine, collector, controller)

        engine.register_tick_callback(
            build_tick_callback(controller, clock, engine, collector)
        )
        live_sim_data["engine"] = engine
        live_sim_data["collector"] = collector
        live_sim_data["controller"] = controller
        live_sim_data["builder"] = builder
        live_sim_data["config_id"] = config_id
    return live_sim_data


@app.post("/api/simulation/config")
def update_simulation_config(payload: Dict[str, Any]) -> Dict[str, Any]:
    global current_live_config, dual_sim_orchestrator, is_user_defined_seed
    # Shutdown existing simulation if running
    if live_sim_data["engine"] is not None:
        try:
            live_sim_data["engine"].stop()
        except Exception:
            pass
        live_sim_data["engine"] = None

    # Reset dual orchestrator if existing
    if dual_sim_orchestrator is not None:
        try:
            dual_sim_orchestrator.stop()
        except Exception:
            pass
        dual_sim_orchestrator = None

    # Determine randomSeed (preserve user-provided seed explicitly)
    raw_seed = payload.get("randomSeed")
    if raw_seed is not None and str(raw_seed).strip() != "":
        try:
            seed_val = int(raw_seed)
            is_user_defined_seed = True
        except (ValueError, TypeError):
            seed_val = random.randint(1, 10000000)
            is_user_defined_seed = False
    else:
        seed_val = random.randint(1, 10000000)
        is_user_defined_seed = False

    # Compile the config dictionary based on user payload
    current_live_config = {
        "simulation": {
            "timeStep": DEFAULT_CONFIG["simulation"]["timeStep"],
            "duration": float(
                payload.get("duration", DEFAULT_CONFIG["simulation"]["duration"])
            ),
            "warmupTime": DEFAULT_CONFIG["simulation"]["warmupTime"],
            "randomSeed": seed_val,
        },
        "geometry": {
            "intersectionType": payload.get("intersectionType", "fixed_time_signal"),
            "intersectionCenter": {"x": 0.0, "y": 0.0},
            "boundingRadius": float(payload.get("intersectionSize", 15.0)),
        },
        "roads": {
            "approachLength": 200.0,
            "laneWidth": float(payload.get("laneWidth", 3.5)),
            "lanesPerApproach": {
                "north": int(payload.get("lanesNorth", 2)),
                "south": int(payload.get("lanesSouth", 2)),
                "east": int(payload.get("lanesEast", 2)),
                "west": int(payload.get("lanesWest", 2)),
            },
        },
        "traffic": {
            "arrivalRate": float(payload.get("arrivalRate", 0.5)),
            "arrivalDistribution": "poisson",
        },
        "controller": (
            {
                "straightRightDuration": float(
                    payload.get(
                        "greenDuration",
                        DEFAULT_CONFIG["controller"]["straightRightDuration"],
                    )
                ),
                "leftDuration": float(
                    payload.get(
                        "leftDuration", DEFAULT_CONFIG["controller"]["leftDuration"]
                    )
                ),
                "yellowDuration": float(
                    payload.get(
                        "yellowDuration",
                        DEFAULT_CONFIG["controller"]["yellowDuration"],
                    )
                ),
                "allRedDuration": float(
                    payload.get(
                        "allRedDuration",
                        DEFAULT_CONFIG["controller"]["allRedDuration"],
                    )
                ),
            }
            if payload.get("intersectionType", "fixed_time_signal")
            == "fixed_time_signal"
            else {
                "innerRadius": 10.0,
                "outerRadius": 20.0,
                "circulatingLanes": 1,
                "criticalGap": float(payload.get("criticalGap", 2.5)),
                "followUpTime": float(payload.get("followUpTime", 1.5)),
                "entrySpeed": 5.0,
                "circulatingSpeed": 8.0,
            }
        ),
        "roundaboutController": {
            "criticalGap": float(payload.get("criticalGap", 4.0)),
            "followUpTime": float(payload.get("followUpTime", 2.5)),
        },
        "vehicleGeneration": DEFAULT_CONFIG["vehicleGeneration"],
    }

    # Reset live simulation cache
    live_sim_data["engine"] = None
    live_sim_data["collector"] = None
    live_sim_data["controller"] = None
    live_sim_data["builder"] = None
    live_sim_data["config_id"] = None

    # Pre-create the simulation with new configuration parameters
    get_or_create_live_simulation()

    return {
        "status": "ok",
        "message": "Simulation configuration updated successfully",
        "randomSeed": seed_val,
    }


@app.post("/api/simulation/play")
def play_live_simulation() -> Dict[str, Any]:
    sim = get_or_create_live_simulation()
    engine = sim["engine"]
    if engine.status == SimulationStatus.COMPLETED:
        # Re-randomize seed for the new run only if not explicitly user-defined
        if not is_user_defined_seed:
            current_live_config["simulation"]["randomSeed"] = random.randint(
                1, 10000000
            )
        live_sim_data["engine"] = None
        sim = get_or_create_live_simulation()
        engine = sim["engine"]
        engine.start()
    elif engine.status == SimulationStatus.INITIALIZED:
        engine.start()
    elif engine.status == SimulationStatus.PAUSED:
        engine.resume()
    return {
        "status": sim["engine"].status.value.lower(),
        "message": "Live simulation started/resumed",
        "randomSeed": current_live_config["simulation"].get("randomSeed"),
    }


@app.post("/api/simulation/pause")
def pause_live_simulation() -> Dict[str, Any]:
    sim = get_or_create_live_simulation()
    sim["engine"].pause()
    return {
        "status": sim["engine"].status.value.lower(),
        "message": "Live simulation paused",
    }


@app.websocket("/ws/simulation/live")
async def websocket_live_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            sim = get_or_create_live_simulation()
            builder = sim.get("builder")
            if builder is not None:
                snapshot = builder.build()
                await websocket.send_json(snapshot)
            # Sleep 100ms for 10Hz frequency
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        traceback.print_exc()
        try:
            await websocket.close(code=1011, reason=str(e))
        except Exception:
            pass


dual_sim_orchestrator: DualSimulationOrchestrator | None = None


def get_or_create_dual_orchestrator() -> DualSimulationOrchestrator:
    global dual_sim_orchestrator
    if dual_sim_orchestrator is None:
        dual_sim_orchestrator = DualSimulationOrchestrator(current_live_config)
    return dual_sim_orchestrator


@app.post("/api/simulation/dual/play")
def play_dual_simulation() -> Dict[str, Any]:
    global dual_sim_orchestrator
    orch = get_or_create_dual_orchestrator()
    status = orch.engine_signal.status
    if status == SimulationStatus.COMPLETED:
        # Re-randomize shared seed for next dual comparison run only if not user-defined
        if dual_sim_orchestrator is not None:
            try:
                dual_sim_orchestrator.stop()
            except Exception:
                pass
        dual_sim_orchestrator = None
        if not is_user_defined_seed:
            current_live_config["simulation"]["randomSeed"] = random.randint(
                1, 10000000
            )
        orch = get_or_create_dual_orchestrator()
        orch.start()
    elif status == SimulationStatus.INITIALIZED:
        orch.start()
    elif status == SimulationStatus.PAUSED:
        orch.resume()
    return {
        "status": orch.get_status(),
        "message": "Dual simulation started/resumed",
        "randomSeed": current_live_config["simulation"].get("randomSeed"),
    }


@app.post("/api/simulation/dual/pause")
def pause_dual_simulation() -> Dict[str, Any]:
    orch = get_or_create_dual_orchestrator()
    orch.pause()
    return {"status": orch.get_status(), "message": "Dual simulation paused"}


@app.post("/api/simulation/dual/reset")
def reset_dual_simulation() -> Dict[str, Any]:
    global dual_sim_orchestrator
    if dual_sim_orchestrator is not None:
        try:
            dual_sim_orchestrator.stop()
        except Exception:
            pass
    dual_sim_orchestrator = None
    # Generate a fresh shared random seed only if not user-defined
    if not is_user_defined_seed:
        current_live_config["simulation"]["randomSeed"] = random.randint(1, 10000000)
    orch = get_or_create_dual_orchestrator()
    return {
        "status": orch.get_status(),
        "message": "Dual simulation reset",
        "randomSeed": current_live_config["simulation"].get("randomSeed"),
    }


@app.get("/api/simulation/dual/status")
def get_dual_simulation_status() -> Dict[str, Any]:
    orch = get_or_create_dual_orchestrator()
    return {
        "status": orch.get_status(),
        "elapsed": round(orch.clock_signal.get_elapsed_time(), 2),
        "tick": orch.clock_signal.get_tick_count(),
    }


@app.websocket("/ws/simulation/dual")
async def websocket_dual_stream(websocket: WebSocket) -> None:
    await websocket.accept()

    try:
        while True:
            # Re-fetch orchestrator each frame so config changes are reflected
            orch = get_or_create_dual_orchestrator()
            snapshot = orch.get_dual_snapshot()
            await websocket.send_json(snapshot)
            # Sleep 100ms for 10Hz frequency
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        traceback.print_exc()
        try:
            await websocket.close(code=1011, reason=str(e))
        except Exception:
            pass


# ── Week 7 & Week 8: Study, Volume Sweeps, History & Validation Endpoints ────


class VolumeSweepRequest(BaseModel):
    arrivalRates: list[float] | None = None
    duration: float = 60.0
    randomSeed: int = 42
    name: str = "Comparative Volume Sweep"
    customConfig: Dict[str, Any] | None = None


class MonteCarloValidationRequest(BaseModel):
    numSeeds: int = 5
    duration: float = 30.0
    customConfig: Dict[str, Any] | None = None


class RepeatabilityValidationRequest(BaseModel):
    duration: float = 20.0
    randomSeed: int = 12345


@app.post("/api/v1/study/sweeps/run")
def run_sweep_endpoint(payload: VolumeSweepRequest | None = None) -> Dict[str, Any]:
    """Runs an automated traffic volume sweep comparing Signals vs. Roundabouts."""
    req = payload or VolumeSweepRequest()
    return run_volume_sweep_experiment(
        arrival_rates=req.arrivalRates,
        duration=req.duration,
        random_seed=req.randomSeed,
        custom_config=req.customConfig,
        name=req.name,
    )


@app.get("/api/v1/study/sweeps")
def list_sweeps_endpoint(limit: int = 20, offset: int = 0) -> list[Dict[str, Any]]:
    """Lists past volume sweep benchmark experiments."""
    init_db()
    import sqlite3

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        return SweepSessionDAO.list_sessions(conn, limit=limit, offset=offset)
    finally:
        conn.close()


@app.get("/api/v1/study/sweeps/{sweep_id}")
def get_sweep_endpoint(sweep_id: str) -> Dict[str, Any]:
    """Retrieves a specific volume sweep benchmark session."""
    init_db()
    import sqlite3

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        session = SweepSessionDAO.get(conn, sweep_id)
        if not session:
            raise HTTPException(status_code=404, detail="Sweep session not found")
        return session
    finally:
        conn.close()


class RunComparisonRequest(BaseModel):
    runIdA: str
    runIdB: str


@app.get("/api/v1/study/history/runs")
def list_simulation_runs_endpoint(
    limit: int = 50,
    offset: int = 0,
    intersection_type: str | None = None,
    seed: int | None = None,
    batch_id: str | None = None,
) -> list[Dict[str, Any]]:
    """Lists past simulation runs with their status, metrics, and filters."""
    init_db()
    for conn in get_db_connection():
        return SimulationRunDAO.list_runs(
            conn,
            limit=limit,
            offset=offset,
            intersection_type=intersection_type,
            seed=seed,
            batch_id=batch_id,
        )
    return []


@app.get("/api/v1/study/history/runs/{run_id}")
def get_simulation_run_endpoint(run_id: str) -> Dict[str, Any]:
    """Retrieves metadata and time-series metrics for a specific simulation run."""
    init_db()
    for conn in get_db_connection():
        run = SimulationRunDAO.get(conn, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Simulation run not found")
        metrics = RunMetricsDAO.get_all_for_run(conn, run_id)
        return {"run": run, "metricsTimeline": metrics}
    raise HTTPException(status_code=500, detail="Database connection error")


@app.post("/api/v1/study/history/runs/compare")
def compare_runs_endpoint(payload: RunComparisonRequest) -> Dict[str, Any]:
    """Compares two historical simulation runs side-by-side with delta analysis."""
    init_db()
    for conn in get_db_connection():
        run_a = SimulationRunDAO.get(conn, payload.runIdA)
        if not run_a:
            raise HTTPException(
                status_code=404, detail=f"Run '{payload.runIdA}' not found"
            )
        run_b = SimulationRunDAO.get(conn, payload.runIdB)
        if not run_b:
            raise HTTPException(
                status_code=404, detail=f"Run '{payload.runIdB}' not found"
            )

        metrics_a = run_a.get("summary_metrics", {})
        metrics_b = run_b.get("summary_metrics", {})

        delay_a = metrics_a.get("averageDelay", metrics_a.get("averageWaitTime", 0.0))
        delay_b = metrics_b.get("averageDelay", metrics_b.get("averageWaitTime", 0.0))
        tp_a = metrics_a.get("throughput", 0.0)
        tp_b = metrics_b.get("throughput", 0.0)
        queue_a = metrics_a.get("averageQueueLength", 0.0)
        queue_b = metrics_b.get("averageQueueLength", 0.0)
        stops_a = metrics_a.get("totalStops", 0)
        stops_b = metrics_b.get("totalStops", 0)

        delay_delta = round(delay_b - delay_a, 2)
        delay_delta_pct = (
            round(((delay_b - delay_a) / max(delay_a, 0.01)) * 100, 1)
            if delay_a > 0
            else 0.0
        )
        tp_delta = round(tp_b - tp_a, 1)
        queue_delta = round(queue_b - queue_a, 1)
        stops_delta = stops_b - stops_a

        # Winner evaluation based on lower delay
        if delay_a < delay_b:
            winner = run_a.get("intersection_type") or payload.runIdA
        elif delay_b < delay_a:
            winner = run_b.get("intersection_type") or payload.runIdB
        else:
            winner = "tie"

        return {
            "runA": {
                "id": payload.runIdA,
                "intersectionType": run_a.get("intersection_type"),
                "seed": run_a.get("random_seed"),
                "arrivalRate": run_a.get("arrival_rate"),
                "metrics": metrics_a,
            },
            "runB": {
                "id": payload.runIdB,
                "intersectionType": run_b.get("intersection_type"),
                "seed": run_b.get("random_seed"),
                "arrivalRate": run_b.get("arrival_rate"),
                "metrics": metrics_b,
            },
            "comparison": {
                "delayDelta": delay_delta,
                "delayDeltaPercent": delay_delta_pct,
                "throughputDelta": tp_delta,
                "queueDelta": queue_delta,
                "stopsDelta": stops_delta,
                "winner": winner,
            },
            "identicalSeed": run_a.get("random_seed") == run_b.get("random_seed"),
            "seed": run_a.get("random_seed")
            if run_a.get("random_seed") == run_b.get("random_seed")
            else None,
        }
    raise HTTPException(status_code=500, detail="Database connection error")


@app.post("/api/v1/study/history/runs/{run_id}/reproduce")
def reproduce_run_endpoint(run_id: str) -> Dict[str, Any]:
    """Re-executes the exact run headlessly using its stored configuration and seed to verify determinism."""
    init_db()
    for conn in get_db_connection():
        run = SimulationRunDAO.get(conn, run_id)
        if not run:
            raise HTTPException(
                status_code=404, detail=f"Simulation run '{run_id}' not found"
            )

        config = run.get("config")
        if not config or not isinstance(config, dict) or len(config) == 0:
            raise HTTPException(
                status_code=400,
                detail=f"Run '{run_id}' does not have a saved configuration to reproduce.",
            )

        random_seed = run.get("random_seed", 0)
        time_step = config.get("simulation", {}).get("timeStep", 0.1)
        duration = run.get("duration") or run.get("elapsed", 30.0)

        # Clone config and ensure seed, timeStep, duration match
        run_config = json.loads(json.dumps(config))
        if "simulation" not in run_config:
            run_config["simulation"] = {}
        run_config["simulation"]["randomSeed"] = random_seed
        run_config["simulation"]["timeStep"] = time_step
        run_config["simulation"]["duration"] = duration

        clock = Clock(time_step=time_step)
        engine = SimulationEngine(clock, duration=duration, config=run_config)
        controller = create_controller(run_config, engine.network)
        engine.controller = controller
        collector = MetricCollector(run_config)

        def tick_callback() -> None:
            controller.update(clock.time_step, engine.pool.active_vehicles)
            collector.update(
                clock.get_elapsed_time(),
                engine.pool.active_vehicles,
                engine.pool.exited_vehicles,
                getattr(controller, "current_signals", {}),
            )

        engine.register_tick_callback(tick_callback)

        steps = int(duration / time_step)
        for _ in range(steps):
            engine.step()

        reproduced_metrics = collector.get_metrics(
            clock.get_elapsed_time(),
            engine.pool.active_vehicles,
            engine.pool.exited_vehicles,
            engine.spawner.spawned_count if engine.spawner else 0,
        )

        original_metrics = run.get("summary_metrics", {})

        # Compare determinism on key metrics
        orig_delay = original_metrics.get(
            "averageDelay", original_metrics.get("averageWaitTime")
        )
        repro_delay = reproduced_metrics.get(
            "averageDelay", reproduced_metrics.get("averageWaitTime")
        )
        orig_tp = original_metrics.get("throughput")
        repro_tp = reproduced_metrics.get("throughput")

        discrepancies = []
        if orig_delay is not None and repro_delay is not None:
            if abs(orig_delay - repro_delay) > 0.05:
                discrepancies.append(
                    f"Delay mismatch: original={orig_delay}, reproduced={repro_delay}"
                )
        if orig_tp is not None and repro_tp is not None:
            if abs(orig_tp - repro_tp) > 0.1:
                discrepancies.append(
                    f"Throughput mismatch: original={orig_tp}, reproduced={repro_tp}"
                )

        is_deterministic = len(discrepancies) == 0

        return {
            "runId": run_id,
            "seed": random_seed,
            "intersectionType": run.get("intersection_type"),
            "duration": duration,
            "isDeterministic": is_deterministic,
            "originalMetrics": original_metrics,
            "reproducedMetrics": reproduced_metrics,
            "discrepancies": discrepancies,
        }
    raise HTTPException(status_code=500, detail="Database connection error")


@app.post("/api/v1/study/validate/repeatability")
def validate_repeatability_endpoint(
    payload: RepeatabilityValidationRequest | None = None,
) -> Dict[str, Any]:
    """Verifies physical invariants, mass conservation, and deterministic seed repeatability."""
    req = payload or RepeatabilityValidationRequest()
    return run_invariant_checks(
        duration=req.duration,
        random_seed=req.randomSeed,
    )


@app.post("/api/v1/study/validate/monte-carlo")
def validate_monte_carlo_endpoint(
    payload: MonteCarloValidationRequest | None = None,
) -> Dict[str, Any]:
    """Runs multi-seed Monte Carlo statistical validation with confidence intervals."""
    req = payload or MonteCarloValidationRequest()
    return run_statistical_validation(
        config=req.customConfig,
        num_seeds=req.numSeeds,
        duration=req.duration,
    )


@app.get("/api/v1/study/export")
def export_study_report_endpoint(format: str = "json") -> Any:  # noqa: A002
    """Exports full comprehensive validated study dataset in JSON or CSV format."""
    if format.lower() == "csv":
        csv_content = generate_study_report_csv()
        return StreamingResponse(
            iter([csv_content]),
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=traffic_simulation_study_v1.csv"
            },
        )
    return generate_study_report_json()


class SaveReplayRequest(BaseModel):
    name: str
    config: Dict[str, Any]
    metrics: Dict[str, Any]


from src.database.replay_dao import ReplayDAO


@app.post("/api/v1/replays")
def save_replay(payload: SaveReplayRequest) -> Dict[str, Any]:
    init_db()
    for conn in get_db_connection():
        replay_id = ReplayDAO.save(conn, payload.name, payload.config, payload.metrics)
        # Also persist to simulation_runs for history and reproducible comparison
        itype = payload.config.get("geometry", {}).get("intersectionType", "unknown")
        seed = payload.config.get("simulation", {}).get("randomSeed", 0)
        arr_rate = payload.config.get("traffic", {}).get("arrivalRate", 0.5)
        duration = payload.config.get("simulation", {}).get("duration", 60.0)
        SimulationRunDAO.save(
            conn,
            replay_id,
            "completed",
            duration,
            intersection_type=itype,
            random_seed=seed,
            arrival_rate=arr_rate,
            duration=duration,
            batch_id="replay",
            config=payload.config,
            summary_metrics=payload.metrics,
        )
        conn.commit()
        return {"status": "ok", "replay_id": replay_id}
    raise HTTPException(status_code=500, detail="Database connection error")


@app.get("/api/v1/replays")
def list_replays(limit: int = 50, offset: int = 0) -> list[Dict[str, Any]]:
    init_db()
    for conn in get_db_connection():
        return ReplayDAO.list_all(conn, limit=limit, offset=offset)
    return []


@app.delete("/api/v1/replays/{replay_id}")
def delete_replay(replay_id: str) -> Dict[str, Any]:
    init_db()
    for conn in get_db_connection():
        success = ReplayDAO.delete(conn, replay_id)
        if not success:
            raise HTTPException(status_code=404, detail="Replay not found")
        return {"status": "ok"}
    raise HTTPException(status_code=500, detail="Database connection error")
