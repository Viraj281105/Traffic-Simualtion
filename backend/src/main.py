import asyncio
import contextvars
import csv
import io
import json
import logging
import os
import random
import secrets
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import jsonschema
from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from src.controllers.factory import (
    build_tick_callback,
    create_controller,
    derive_signals_state,
)
from src.core.clock import Clock
from src.core.config_models import ScenarioConfiguration
from src.core.engine import SimulationEngine
from src.core.enums import SimulationStatus
from src.database.dao import RunMetricsDAO, SimulationRunDAO, SweepSessionDAO
from src.database.db import DB_PATH, get_db_connection, init_db  # noqa: F401
from src.database.replay_dao import ReplayDAO
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

# ── CORS ──────────────────────────────────────────────────────────────────
# Origins are environment-driven (CORS_ORIGINS, comma-separated), never
# hardcoded to a specific machine/domain. The local-dev default covers the
# Vite dev server's default port. A bare "*" is never combined with
# allow_credentials=True (browsers reject that combination anyway, and it
# amounts to an unrestricted, credentialed CORS policy) — CORS_ORIGINS="*"
# instead explicitly disables credentials for that case.
_DEFAULT_DEV_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
_cors_origins_raw = os.environ.get("CORS_ORIGINS", _DEFAULT_DEV_ORIGINS).strip()
if _cors_origins_raw == "*":
    CORS_ORIGINS = ["*"]
    CORS_ALLOW_CREDENTIALS = False
else:
    CORS_ORIGINS = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]
    CORS_ALLOW_CREDENTIALS = True

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=CORS_ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Minimal API-key protection for mutating / compute-heavy endpoints ──────
# Disabled (no-op) when API_KEY is unset/empty — the intended local-dev
# default, so nothing needs to change to keep developing without auth. Set
# the API_KEY environment variable to require
# `Authorization: Bearer <API_KEY>` on protected routes (see usage below).
API_KEY = os.environ.get("API_KEY", "").strip()


def require_api_key(authorization: Optional[str] = Header(default=None)) -> None:
    if not API_KEY:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    provided = authorization[len("Bearer ") :]
    if not secrets.compare_digest(provided, API_KEY):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── Uniform error envelope (docs/architecture/08-communication-contract.md
# §6.1) ──────────────────────────────────────────────────────────────────
# Every route in this file raises plain HTTPException(status_code, detail=
# "..."), which FastAPI serializes by default as {"detail": "..."}. The
# documented contract instead requires every error response to share one
# consistent shape: {"error": {"code", "message", "details", "timestamp"}}.
# This handler rewrites the response body only — it does not change status
# codes, and it never runs for a 2xx response, so no successful response
# structure is affected. The frontend does not inspect error response
# bodies (it keys off HTTP status only — see useSimulationPolling.ts), so
# this is safe to change without a frontend change.
_STATUS_ERROR_CODES: Dict[int, str] = {
    400: "VALIDATION_ERROR",
    401: "UNAUTHORIZED",
    404: "NOT_FOUND",
    409: "INVALID_STATE_TRANSITION",
    429: "SIMULATION_LIMIT_REACHED",
    500: "INTERNAL_ERROR",
}


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    code = _STATUS_ERROR_CODES.get(exc.status_code, "INTERNAL_ERROR")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": None,
                "timestamp": datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
            }
        },
        headers=exc.headers,
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


# Load the shared config JSON schema, resolved relative to this package's
# location on disk (backend/src/main.py -> repo root / shared / schemas),
# never a machine-specific absolute path or the process's CWD. Validation
# against this schema is a security/correctness boundary (see
# create_simulation() and validate_config()), so a missing or unreadable
# schema must fail application startup loudly rather than silently falling
# back to an empty schema that would make validation a no-op.
# Two known-valid package layouts share this codebase: running from the
# repo checkout (backend/src/main.py, shared/ three levels up) and running
# from the built Docker image (/app/src/main.py, shared/ copied directly
# under /app — see backend/Dockerfile's `COPY shared/ ./shared/`, one
# level up). Try both — still package-relative, never a machine-specific
# absolute path — and fail loudly only if neither resolves.
_SCHEMA_PATH_CANDIDATES = [
    Path(__file__).resolve().parents[2] / "shared" / "schemas" / "config.schema.json",
    Path(__file__).resolve().parents[1] / "shared" / "schemas" / "config.schema.json",
]

CONFIG_SCHEMA_PATH: Optional[Path] = next(
    (p for p in _SCHEMA_PATH_CANDIDATES if p.is_file()), None
)

if CONFIG_SCHEMA_PATH is None:
    raise RuntimeError(
        "Failed to load required config schema: none of "
        f"{[str(p) for p in _SCHEMA_PATH_CANDIDATES]} exist. The application "
        "cannot start without it, since configuration validation would "
        "otherwise silently become a no-op."
    )

try:
    with open(CONFIG_SCHEMA_PATH, "r", encoding="utf-8") as f:
        CONFIG_SCHEMA: Dict[str, Any] = json.load(f)
except (OSError, json.JSONDecodeError) as exc:
    raise RuntimeError(
        f"Failed to load required config schema from {CONFIG_SCHEMA_PATH}. "
        "The application cannot start without it, since configuration "
        "validation would otherwise silently become a no-op."
    ) from exc

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


@app.post("/api/simulation/start", dependencies=[Depends(require_api_key)])
def start_simulation() -> Dict[str, Any]:
    single_veh.status = "running"
    return {"status": "running", "message": "Simulation started"}


@app.post("/api/simulation/stop", dependencies=[Depends(require_api_key)])
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


@app.post("/api/simulation/reset", dependencies=[Depends(require_api_key)])
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
    try:
        jsonschema.validate(instance=payload, schema=CONFIG_SCHEMA)
        return {"valid": True, "errors": []}
    except jsonschema.ValidationError as err:
        return {"valid": False, "errors": [err.message]}


# ── Full Simulation Lifecycle REST Routes ───────────────────────────────────
@app.post("/api/simulation/new", dependencies=[Depends(require_api_key)])
def create_simulation_v2(payload: ScenarioConfiguration) -> Dict[str, Any]:
    config_dict = payload.model_dump(exclude_none=True)
    return create_simulation(config_dict)


def _persist_completed_run(
    sim_id: str, config: Dict[str, Any], engine: SimulationEngine, collector: MetricCollector
) -> None:
    """Records a completed (or stopped) simulation into simulation_runs.

    Reads the random seed straight from the spawner — the single
    authoritative place a seed is resolved (see VehicleSpawner.__init__) —
    so the persisted seed is always the exact one actually used, whether it
    was user-supplied or auto-generated. Any failure here is logged and
    swallowed rather than propagated, so a database hiccup can never flip an
    otherwise-successful simulation into an error state.
    """
    try:
        itype = config.get("geometry", {}).get("intersectionType", "unknown")
        seed = (
            engine.spawner.random_seed
            if engine.spawner is not None
            else config.get("simulation", {}).get("randomSeed", 0)
        )
        arrival_rate = config.get("traffic", {}).get("arrivalRate", 0.5)
        elapsed = engine.clock.get_elapsed_time()
        final_metrics = collector.get_metrics(
            elapsed,
            engine.pool.active_vehicles,
            engine.pool.exited_vehicles,
            engine.spawner.spawned_count if engine.spawner else 0,
        )
        with get_db_connection() as conn:
            SimulationRunDAO.save(
                conn,
                sim_id,
                "completed",
                elapsed,
                intersection_type=itype,
                random_seed=seed,
                arrival_rate=arrival_rate,
                duration=elapsed,
                config=config,
                summary_metrics=final_metrics,
            )
    except Exception:
        logger.exception("Failed to persist simulation run %s to history", sim_id)


# Bound the in-memory simulation registry so it cannot grow without limit.
MAX_CONCURRENT_SIMULATIONS = 50


def _evict_completed_simulations() -> None:
    """Evicts the oldest completed/errored simulations to make room.

    Never evicts a RUNNING or PAUSED simulation.
    """
    if len(simulations_db) < MAX_CONCURRENT_SIMULATIONS:
        return

    evictable = [
        (sid, entry)
        for sid, entry in simulations_db.items()
        if entry["engine"].status in (SimulationStatus.COMPLETED, SimulationStatus.ERROR)
    ]
    evictable.sort(key=lambda item: item[1].get("created_at", 0.0))

    slots_needed = len(simulations_db) - MAX_CONCURRENT_SIMULATIONS + 1
    for sid, _ in evictable[:slots_needed]:
        del simulations_db[sid]


@app.post(
    "/api/v1/simulations",
    status_code=201,
    dependencies=[Depends(require_api_key)],
)
def create_simulation(config: Dict[str, Any]) -> Dict[str, Any]:
    # Validate configuration against the schema (schema-level shape/bounds).
    try:
        jsonschema.validate(instance=config, schema=CONFIG_SCHEMA)
    except jsonschema.ValidationError as err:
        raise HTTPException(
            status_code=400, detail=f"Invalid configuration: {err.message}"
        )

    _evict_completed_simulations()
    if len(simulations_db) >= MAX_CONCURRENT_SIMULATIONS:
        raise HTTPException(
            status_code=429, detail="Maximum concurrent simulations reached"
        )

    sim_id = str(uuid.uuid4())
    config_id = str(uuid.uuid4())

    # Instantiate clock, engine, collector, and controller. This can raise
    # ValueError/KeyError/TypeError for a config that passed schema
    # validation but is semantically invalid (e.g. duration <= 0, an
    # unsupported phaseSequence entry) — surface those as 400s, not a raw
    # 500, since they are still the client's fault.
    try:
        clock = Clock(time_step=config.get("simulation", {}).get("timeStep", 0.1))
        duration = config.get("simulation", {}).get("duration", 300)
        engine = SimulationEngine(clock, duration=duration, config=config)

        controller = create_controller(config, engine.network)
        engine.controller = controller

        collector = MetricCollector(config)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(
            status_code=400, detail=f"Invalid configuration: {exc}"
        ) from exc

    builder = SnapshotBuilder(sim_id, config_id, engine, collector, controller)
    buffer = SnapshotBuffer(max_frames=1000)

    # Register tick callback on engine to update collector and controller
    engine.register_tick_callback(
        build_tick_callback(controller, clock, engine, collector, buffer, builder)
    )
    # Persist to run history the moment the simulation completes (naturally
    # or via an explicit stop) — the single existing "run-save flow" this
    # extends to cover ordinary /api/v1/simulations runs, not just sweeps
    # and manually-saved replays.
    engine.register_status_callback(
        lambda new_status: (
            _persist_completed_run(sim_id, config, engine, collector)
            if new_status == SimulationStatus.COMPLETED
            else None
        )
    )

    simulations_db[sim_id] = {
        "engine": engine,
        "collector": collector,
        "controller": controller,
        "config_id": config_id,
        "buffer": buffer,
        "created_at": time.time(),
    }

    return {
        "simulationId": sim_id,
        "configId": config_id,
        "status": engine.status.value.lower(),
    }


@app.delete("/api/v1/simulations/{sim_id}", dependencies=[Depends(require_api_key)])
def delete_simulation(sim_id: str) -> Dict[str, Any]:
    """Explicitly removes a simulation from the in-memory registry.

    Refuses to delete a RUNNING/PAUSED simulation — stop it first.
    """
    sim = _get_simulation_or_404(sim_id)
    engine = sim["engine"]
    if engine.status in (SimulationStatus.RUNNING, SimulationStatus.PAUSED):
        raise HTTPException(
            status_code=400,
            detail="Cannot delete a running or paused simulation; stop it first.",
        )
    del simulations_db[sim_id]
    return {"status": "deleted", "simulationId": sim_id}


@app.post(
    "/api/v1/simulations/{sim_id}/control", dependencies=[Depends(require_api_key)]
)
def control_simulation(sim_id: str, payload: ControlRequest) -> Dict[str, Any]:
    sim = _get_simulation_or_404(sim_id)
    engine = sim["engine"]
    action = payload.action.lower()

    if action not in ("start", "pause", "resume", "stop"):
        raise HTTPException(status_code=400, detail="Invalid action")

    try:
        if action == "start":
            engine.start()
        elif action == "pause":
            engine.pause()
        elif action == "resume":
            engine.resume()
        elif action == "stop":
            engine.stop()
    except RuntimeError as exc:
        # engine.start() raises RuntimeError for an invalid transition
        # (e.g. "start" on an already-running/completed simulation) —
        # surface that as the documented 409 INVALID_STATE_TRANSITION
        # (docs/architecture/08-communication-contract.md §6.2), not an
        # unhandled 500. pause()/resume()/stop() have no invalid-transition
        # case to catch here: they are documented no-ops outside their
        # applicable state (see SimulationEngine).
        raise HTTPException(status_code=409, detail=str(exc)) from exc

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
    # Hold the engine's lock so this doesn't race the background simulation
    # thread mutating pool.active_vehicles/exited_vehicles mid-tick.
    with engine.lock:
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

    # Get final metrics. Hold the engine's lock so this doesn't race the
    # background simulation thread mutating the vehicle lists mid-tick.
    with engine.lock:
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


def _resolve_snapshot_interval(config: Dict[str, Any]) -> float:
    """Resolves the WS streaming sleep interval from simulation.snapshotFrequency.

    docs/architecture/08-communication-contract.md §5.1: snapshot frequency
    is configurable via simulation.snapshotFrequency (default 10Hz),
    hard-limited to [1, 60]Hz. CONFIG_SCHEMA/ScenarioConfiguration already
    enforce that range on the way in; the clamp here is just a defensive
    fallback for configs that bypassed that validation.
    """
    snapshot_frequency = config.get("simulation", {}).get("snapshotFrequency", 10.0)
    try:
        snapshot_frequency = float(snapshot_frequency)
    except (TypeError, ValueError):
        snapshot_frequency = 10.0
    snapshot_frequency = min(max(snapshot_frequency, 1.0), 60.0)
    return 1.0 / snapshot_frequency


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
    snapshot_interval = _resolve_snapshot_interval(engine.config)

    try:
        while True:
            # Generate and send state snapshot
            snapshot = builder.build()
            await websocket.send_json(snapshot)

            # Check if simulation complete
            if snapshot["simulationStatus"] in ("completed", "error"):
                break

            await asyncio.sleep(snapshot_interval)
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
        # Matches the canonical greenTime=30/yellowTime=4/allRedTime=2
        # defaults (docs/architecture/06-scenario-configuration-contract.md,
        # ControllerSection, CONFIG_SCHEMA) — see
        # FixedTimeSignalController.__init__ for the same reconciliation.
        "straightRightDuration": 30.0,
        "leftDuration": 5.0,
        "yellowDuration": 4.0,
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

# ── Per-client isolation for the live/dual demo simulation state ───────────
# current_live_config, live_sim_data, and dual_sim_orchestrator used to be
# bare process-global singletons, so one client's /api/simulation/config or
# /api/simulation/dual/reset call would silently reset what every other
# connected client was watching. There is no existing session/user concept
# in this API to key off of, so the smallest practical, dependency-free
# (no Redis/DB) mechanism is a browser cookie — the closest thing to a
# built-in "connection identifier" HTTP already provides.
LIVE_SESSION_COOKIE = "ts_session"
_DEFAULT_SESSION_KEY = "default"
_LIVE_SESSION_PATH_PREFIX = "/api/simulation"


class _LiveSession:
    """Per-client container for what used to be the three global variables."""

    def __init__(self) -> None:
        self.current_live_config: Dict[str, Any] = DEFAULT_CONFIG.copy()
        self.is_user_defined_seed: bool = False
        self.live_sim_data: Dict[str, Any] = {
            "engine": None,
            "collector": None,
            "controller": None,
            "builder": None,
            "config_id": None,
        }
        self.dual_sim_orchestrator: Optional[DualSimulationOrchestrator] = None


_live_sessions: Dict[str, _LiveSession] = {_DEFAULT_SESSION_KEY: _LiveSession()}
_live_session_var: "contextvars.ContextVar[Optional[_LiveSession]]" = (
    contextvars.ContextVar("live_session", default=None)
)


def _get_or_create_session(key: str) -> _LiveSession:
    if key not in _live_sessions:
        _live_sessions[key] = _LiveSession()
    return _live_sessions[key]


def _current_session() -> _LiveSession:
    """Returns the live session for the current request context.

    Falls back to one shared "default" session for anything that isn't a
    request routed through `_live_session_middleware` with a valid cookie —
    notably the two WebSocket handlers below (which resolve their own
    session explicitly from `websocket.cookies`) and any direct/test call
    outside of request handling. That fallback exactly matches this
    application's previous single-shared-state behavior.
    """
    session = _live_session_var.get()
    if session is not None:
        return session
    return _get_or_create_session(_DEFAULT_SESSION_KEY)


@app.middleware("http")
async def _live_session_middleware(request: Request, call_next: Any) -> Any:
    """Resolves a per-client live-simulation session from a cookie.

    Scoped to /api/simulation/* only (where the shared state actually
    lives) so unrelated routes are unaffected. Standard session-cookie
    bootstrap: an incoming cookie is reused as-is; a request with no cookie
    mints one fresh id and uses that SAME id both for this request and for
    the Set-Cookie response, so the very next request from that client
    lands on the same (now-isolated) session rather than a different one.

    This works transparently — no frontend changes needed — for any client
    whose browser actually stores and resends the cookie: the deployed
    nginx-proxied production topology (frontend and API share an origin,
    see docker-compose.yml/frontend/nginx.conf), `npm run dev` (Vite's own
    dev-server proxy forwards /api and /ws to the backend under the same
    http://localhost:5173 origin — see frontend/vite.config.ts `server.proxy`
    and frontend/src/config.ts, which defaults to relative URLs), and
    same-origin test clients.

    Known limitation: docker-compose.dev.yml's frontend container sets
    VITE_API_URL to an absolute http://localhost:8000 URL, which makes the
    browser call the backend cross-origin, bypassing Vite's proxy. Fetch
    calls there don't set `credentials: "include"`, so the browser will
    neither send nor store this cookie, and each request falls back to a
    fresh, isolated, single-use session — i.e. the live/dual dashboard's
    multi-step flows (config → play → stream) would not see continuity in
    that one specific dev variant. Fixing that needs either a frontend
    change (out of scope for this security/deployment-only batch) or
    propagating the session via a query param/header instead of a cookie —
    a bigger change than "smallest practical improvement" calls for here,
    so it's documented as a follow-up rather than solved.
    """
    if not request.url.path.startswith(_LIVE_SESSION_PATH_PREFIX):
        return await call_next(request)

    incoming = request.cookies.get(LIVE_SESSION_COOKIE)
    key = incoming or str(uuid.uuid4())
    token = _live_session_var.set(_get_or_create_session(key))
    try:
        response = await call_next(request)
    finally:
        _live_session_var.reset(token)
    if not incoming:
        response.set_cookie(
            LIVE_SESSION_COOKIE,
            key,
            httponly=True,
            samesite="lax",
            max_age=60 * 60 * 24,
        )
    return response


def get_or_create_live_simulation() -> Dict[str, Any]:
    session = _current_session()
    if session.live_sim_data["engine"] is None:
        clock = Clock(time_step=0.1)
        duration = session.current_live_config.get("simulation", {}).get(
            "duration", 300
        )
        engine = SimulationEngine(
            clock, duration=duration, config=session.current_live_config
        )
        controller = create_controller(session.current_live_config, engine.network)
        engine.controller = controller

        collector = MetricCollector(session.current_live_config)
        config_id = str(uuid.uuid4())
        builder = SnapshotBuilder("live_sim", config_id, engine, collector, controller)

        engine.register_tick_callback(
            build_tick_callback(controller, clock, engine, collector)
        )
        session.live_sim_data["engine"] = engine
        session.live_sim_data["collector"] = collector
        session.live_sim_data["controller"] = controller
        session.live_sim_data["builder"] = builder
        session.live_sim_data["config_id"] = config_id
    return session.live_sim_data


_VALID_INTERSECTION_TYPES: list[str] = CONFIG_SCHEMA["properties"]["geometry"][
    "properties"
]["intersectionType"]["enum"]


def _generate_random_seed() -> int:
    """The single authority for auto-generating a live-dashboard random
    seed, used wherever the dashboard needs a fresh seed because the
    current one isn't user-defined (initial config, restarting a
    completed live/dual run, resetting the dual comparison).

    Was previously duplicated at each call site as a bare
    `random.randint(1, 10000000)`, pulling from the shared global `random`
    module. Matches the fix already applied in VehicleSpawner and
    DualSimulationOrchestrator for the same reason: never touch the
    shared global module's state for a simulation-scoped seed — use a
    private, independently OS-seeded Random instance instead.
    """
    return random.Random().randint(1, 10_000_000)


@app.post("/api/simulation/config", dependencies=[Depends(require_api_key)])
def update_simulation_config(payload: Dict[str, Any]) -> Dict[str, Any]:
    # Unlike /api/v1/simulations and /api/simulation/new, this endpoint
    # builds its config dict directly from the raw payload without ever
    # running it through CONFIG_SCHEMA or a Pydantic model. An unrecognized
    # intersectionType previously passed through silently: the controller
    # dict below is shaped by `== "fixed_time_signal"` (so any other value,
    # typo or not, gets the roundabout-shaped controller dict), while
    # create_controller() separately checks `== "roundabout"` (so anything
    # else, including that same typo, builds a FixedTimeSignalController) —
    # the two checks disagree for any value that is neither, so a typo
    # silently ignored the user's submitted signal-timing parameters
    # instead of failing. Reject it up front instead, consistent with how
    # the versioned creation endpoints already validate this field.
    intersection_type = payload.get("intersectionType")
    if (
        intersection_type is not None
        and intersection_type not in _VALID_INTERSECTION_TYPES
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid intersectionType '{intersection_type}'. "
                f"Must be one of: {', '.join(_VALID_INTERSECTION_TYPES)}."
            ),
        )

    session = _current_session()
    # Shutdown existing simulation if running
    if session.live_sim_data["engine"] is not None:
        try:
            session.live_sim_data["engine"].stop()
        except Exception:
            pass
        session.live_sim_data["engine"] = None

    # Reset dual orchestrator if existing
    if session.dual_sim_orchestrator is not None:
        try:
            session.dual_sim_orchestrator.stop()
        except Exception:
            pass
        session.dual_sim_orchestrator = None

    # Determine randomSeed (preserve user-provided seed explicitly)
    raw_seed = payload.get("randomSeed")
    if raw_seed is not None and str(raw_seed).strip() != "":
        try:
            seed_val = int(raw_seed)
            session.is_user_defined_seed = True
        except (ValueError, TypeError):
            seed_val = _generate_random_seed()
            session.is_user_defined_seed = False
    else:
        seed_val = _generate_random_seed()
        session.is_user_defined_seed = False

    # Compile the config dictionary based on user payload
    session.current_live_config = {
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
                "criticalGap": float(payload.get("criticalGap", 4.0)),
                "followUpTime": float(payload.get("followUpTime", 2.5)),
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
    session.live_sim_data["engine"] = None
    session.live_sim_data["collector"] = None
    session.live_sim_data["controller"] = None
    session.live_sim_data["builder"] = None
    session.live_sim_data["config_id"] = None

    # Pre-create the simulation with new configuration parameters
    get_or_create_live_simulation()

    return {
        "status": "ok",
        "message": "Simulation configuration updated successfully",
        "randomSeed": seed_val,
    }


@app.post("/api/simulation/play", dependencies=[Depends(require_api_key)])
def play_live_simulation() -> Dict[str, Any]:
    session = _current_session()
    sim = get_or_create_live_simulation()
    engine = sim["engine"]
    if engine.status == SimulationStatus.COMPLETED:
        # Re-randomize seed for the new run only if not explicitly user-defined
        if not session.is_user_defined_seed:
            session.current_live_config["simulation"]["randomSeed"] = (
                _generate_random_seed()
            )
        session.live_sim_data["engine"] = None
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
        "randomSeed": session.current_live_config["simulation"].get("randomSeed"),
    }


@app.post("/api/simulation/pause", dependencies=[Depends(require_api_key)])
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
    session_key = websocket.cookies.get(LIVE_SESSION_COOKIE) or _DEFAULT_SESSION_KEY
    token = _live_session_var.set(_get_or_create_session(session_key))
    last_status: Optional[str] = None
    last_sent_time = 0.0

    try:
        while True:
            sim = get_or_create_live_simulation()
            engine = sim.get("engine")
            builder = sim.get("builder")
            if builder is not None and engine is not None:
                current_status = engine.status.value.lower()
                now = time.time()

                if (
                    current_status != "completed"
                    or current_status != last_status
                    or (now - last_sent_time >= 1.0)
                ):
                    snapshot = builder.build()
                    await websocket.send_json(snapshot)
                    last_status = current_status
                    last_sent_time = now

            # Sleep 100ms for 10Hz frequency
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.exception("Live simulation websocket failed")
        try:
            await websocket.close(code=1011, reason=str(e))
        except Exception:
            pass
    finally:
        _live_session_var.reset(token)


def get_or_create_dual_orchestrator() -> DualSimulationOrchestrator:
    session = _current_session()
    if session.dual_sim_orchestrator is None:
        session.dual_sim_orchestrator = DualSimulationOrchestrator(
            session.current_live_config
        )
    return session.dual_sim_orchestrator


@app.post("/api/simulation/dual/play", dependencies=[Depends(require_api_key)])
def play_dual_simulation() -> Dict[str, Any]:
    session = _current_session()
    orch = get_or_create_dual_orchestrator()
    status = orch.engine_signal.status
    if status == SimulationStatus.COMPLETED:
        # Re-randomize shared seed for next dual comparison run only if not user-defined
        if session.dual_sim_orchestrator is not None:
            try:
                session.dual_sim_orchestrator.stop()
            except Exception:
                pass
        session.dual_sim_orchestrator = None
        if not session.is_user_defined_seed:
            session.current_live_config["simulation"]["randomSeed"] = (
                _generate_random_seed()
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
        "randomSeed": session.current_live_config["simulation"].get("randomSeed"),
    }


@app.post("/api/simulation/dual/pause", dependencies=[Depends(require_api_key)])
def pause_dual_simulation() -> Dict[str, Any]:
    orch = get_or_create_dual_orchestrator()
    orch.pause()
    return {"status": orch.get_status(), "message": "Dual simulation paused"}


@app.post("/api/simulation/dual/reset", dependencies=[Depends(require_api_key)])
def reset_dual_simulation() -> Dict[str, Any]:
    session = _current_session()
    if session.dual_sim_orchestrator is not None:
        try:
            session.dual_sim_orchestrator.stop()
        except Exception:
            pass
    session.dual_sim_orchestrator = None
    # Generate a fresh shared random seed only if not user-defined
    if not session.is_user_defined_seed:
        session.current_live_config["simulation"]["randomSeed"] = (
            _generate_random_seed()
        )
    orch = get_or_create_dual_orchestrator()
    return {
        "status": orch.get_status(),
        "message": "Dual simulation reset",
        "randomSeed": session.current_live_config["simulation"].get("randomSeed"),
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
    session_key = websocket.cookies.get(LIVE_SESSION_COOKIE) or _DEFAULT_SESSION_KEY
    token = _live_session_var.set(_get_or_create_session(session_key))
    last_status: Optional[str] = None
    last_sent_time = 0.0

    try:
        while True:
            # Re-fetch orchestrator each frame so config changes are reflected
            orch = get_or_create_dual_orchestrator()
            current_status = orch.get_status()
            now = time.time()

            if (
                current_status != "completed"
                or current_status != last_status
                or (now - last_sent_time >= 1.0)
            ):
                snapshot = orch.get_dual_snapshot()
                await websocket.send_json(snapshot)
                last_status = current_status
                last_sent_time = now

            # Sleep 100ms for 10Hz frequency
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.exception("Dual simulation websocket failed")
        try:
            await websocket.close(code=1011, reason=str(e))
        except Exception:
            pass
    finally:
        _live_session_var.reset(token)


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


@app.post("/api/v1/study/sweeps/run", dependencies=[Depends(require_api_key)])
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
    with get_db_connection() as conn:
        return SweepSessionDAO.list_sessions(conn, limit=limit, offset=offset)
    return []


@app.get("/api/v1/study/sweeps/{sweep_id}")
def get_sweep_endpoint(sweep_id: str) -> Dict[str, Any]:
    """Retrieves a specific volume sweep benchmark session."""
    init_db()
    with get_db_connection() as conn:
        session = SweepSessionDAO.get(conn, sweep_id)
        if not session:
            raise HTTPException(status_code=404, detail="Sweep session not found")
        res = dict(session)
        if isinstance(session.get("results"), dict):
            for k, v in session["results"].items():
                if k not in res:
                    res[k] = v
        if "sessionId" not in res:
            res["sessionId"] = res.get("id", sweep_id)
        return res
    raise HTTPException(status_code=500, detail="Database connection error")


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
    with get_db_connection() as conn:
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
    with get_db_connection() as conn:
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
    with get_db_connection() as conn:
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


@app.post(
    "/api/v1/study/history/runs/{run_id}/reproduce",
    dependencies=[Depends(require_api_key)],
)
def reproduce_run_endpoint(run_id: str) -> Dict[str, Any]:
    """Re-executes the exact run headlessly using its stored configuration and seed to verify determinism."""
    init_db()
    with get_db_connection() as conn:
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
            # engine.step() already calls controller.update() once per tick
            # (via engine.controller, set above) before running tick
            # callbacks — calling it again here would advance the
            # controller's phase/follow-up timing at double the rate of the
            # original run, breaking reproduction. Only read its resulting
            # state, exactly like build_tick_callback does for ordinary runs.
            collector.update(
                clock.get_elapsed_time(),
                engine.pool.active_vehicles,
                engine.pool.exited_vehicles,
                derive_signals_state(controller),
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


@app.post(
    "/api/v1/study/validate/repeatability", dependencies=[Depends(require_api_key)]
)
def validate_repeatability_endpoint(
    payload: RepeatabilityValidationRequest | None = None,
) -> Dict[str, Any]:
    """Verifies physical invariants, mass conservation, and deterministic seed repeatability."""
    req = payload or RepeatabilityValidationRequest()
    return run_invariant_checks(
        duration=req.duration,
        random_seed=req.randomSeed,
    )


@app.post(
    "/api/v1/study/validate/monte-carlo", dependencies=[Depends(require_api_key)]
)
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


@app.post("/api/v1/replays", dependencies=[Depends(require_api_key)])
def save_replay(payload: SaveReplayRequest) -> Dict[str, Any]:
    init_db()
    with get_db_connection() as conn:
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
    with get_db_connection() as conn:
        return ReplayDAO.list_all(conn, limit=limit, offset=offset)
    return []


@app.get("/api/v1/replays/{replay_id}")
def get_replay(replay_id: str) -> Dict[str, Any]:
    init_db()
    with get_db_connection() as conn:
        replay = ReplayDAO.get(conn, replay_id)
        if not replay:
            raise HTTPException(status_code=404, detail="Replay not found")
        return replay
    raise HTTPException(status_code=500, detail="Database connection error")


@app.delete("/api/v1/replays/{replay_id}", dependencies=[Depends(require_api_key)])
def delete_replay(replay_id: str) -> Dict[str, Any]:
    init_db()
    with get_db_connection() as conn:
        success = ReplayDAO.delete(conn, replay_id)
        if not success:
            raise HTTPException(status_code=404, detail="Replay not found")
        return {"status": "ok"}
    raise HTTPException(status_code=500, detail="Database connection error")
