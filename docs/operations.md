# Operations Guide

This guide describes the behavior implemented by `backend/src/main.py` and the current frontend services. The interactive dashboard uses the legacy live routes; the versioned routes are intended for programmatic runs and study analysis.

## Start a Versioned Simulation

The request body is a scenario object. A minimal valid example is:

```json
{
  "simulation": { "duration": 30, "timeStep": 0.1, "randomSeed": 42 },
  "geometry": { "intersectionType": "fixed_time_signal" },
  "traffic": { "arrivalRate": 0.3, "arrivalDistribution": "poisson" },
  "roads": {
    "approachLength": 200,
    "laneWidth": 3.5,
    "lanesPerApproach": { "north": 2, "south": 2, "east": 2, "west": 2 }
  }
}
```

Validate it with `POST /api/v1/configs/validate`, then create it with `POST /api/v1/simulations`. The response contains `simulationId`, `configId`, and `status`. Use the returned ID with:

```text
POST /api/v1/simulations/{id}/control       {"action":"start|pause|resume|stop"}
GET  /api/v1/simulations/{id}
GET  /api/v1/simulations/{id}/metrics
GET  /api/v1/simulations/{id}/history
GET  /api/v1/simulations/{id}/history/{tick}
GET  /api/v1/simulations/{id}/report?format=json
GET  /api/v1/simulations/{id}/report?format=csv
```

The status response has `simulationId`, `status`, `elapsed`, and `tick`. The history endpoint returns buffered snapshots (up to 1,000 frames). The report endpoint returns final metrics as JSON or a CSV download. Versioned simulations are held in memory and return 404 after a backend restart.

## WebSockets

The versioned stream is:

```text
ws://localhost:8000/ws/v1/stream?simulationId=<id>
```

It sends a JSON snapshot approximately every 100 ms until the snapshot status is `completed` or `error`. The server does not accept control messages on this socket; use the REST control endpoint. A missing simulation closes with WebSocket code `1008`.

The dashboard-compatible sockets are:

```text
ws://localhost:8000/ws/simulation/live
ws://localhost:8000/ws/simulation/dual
```

They also send JSON snapshots at approximately 10 Hz. The live and dual engines advance only after their play/start actions are called.

## Dashboard Workflow

The dashboard sends a compact form payload to `POST /api/simulation/config`:

```json
{
  "intersectionType": "fixed_time_signal",
  "intersectionSize": 15,
  "laneWidth": 3.5,
  "lanesNorth": 2,
  "lanesSouth": 2,
  "lanesEast": 2,
  "lanesWest": 2,
  "arrivalRate": 0.5,
  "duration": 300,
  "randomSeed": 42
}
```

The server expands it into the internal camelCase scenario configuration. Use `POST /api/simulation/play`, `/pause`, or `/stop`; use `/api/simulation/dual/play`, `/pause`, or `/reset` for the side-by-side signal/roundabout comparison. `GET /api/simulation/dual/status` reports the dual run clock. The compatibility endpoints `/api/simulation/start`, `/stop`, `/reset`, `/status`, and `/single-vehicle` support the polling/demo view; `/single-vehicle` advances its simple state by 0.1 seconds when running.

## Study and Analysis

Run and persist a comparative volume sweep:

```http
POST /api/v1/study/sweeps/run
```

Optional JSON fields are `arrivalRates` (array of vehicles per second), `duration`, `randomSeed`, `name`, and `customConfig`. Without `arrivalRates`, the implementation uses `0.1` through `0.8` vehicles/second. Each rate runs signal and roundabout engines with the same seed and stores both runs plus a sweep session in SQLite.

Retrieve saved sweeps with `GET /api/v1/study/sweeps` and `GET /api/v1/study/sweeps/{sweepId}`. Retrieve historical runs with `GET /api/v1/study/history/runs`; optional query parameters are `limit`, `offset`, `intersection_type`, `seed`, and `batch_id`. A run detail includes `run` metadata and a `metricsTimeline`. Compare two saved runs with:

```json
POST /api/v1/study/history/runs/compare
{"runIdA":"...", "runIdB":"..."}
```

`POST /api/v1/study/history/runs/{runId}/reproduce` reruns a saved configuration and seed and reports whether key delay and throughput values match within the implementation tolerances.

Validation endpoints are:

```text
POST /api/v1/study/validate/repeatability  {"duration":20,"randomSeed":12345}
POST /api/v1/study/validate/monte-carlo    {"numSeeds":5,"duration":30,"customConfig":{...}}
GET  /api/v1/study/export?format=json|csv
```

The repeatability check tests vehicle conservation, non-negative speeds, and deterministic key metrics. Monte Carlo validation generates random seeds and returns means, standard deviations, approximate 95% confidence intervals, Cohen's *d*, and a significance flag for delay, throughput, and queue length.

The command-line equivalent is:

```powershell
python scripts/run_full_study.py --help
python scripts/run_full_study.py
```

Use `--output` and the other options shown by `--help` to control output paths and run sizes. The script is separate from the API and writes reports locally.

## Replays and Database

Save a completed result with `POST /api/v1/replays`:

```json
{
  "name": "baseline",
  "config": { "simulation": { "duration": 30 }, "geometry": { "intersectionType": "roundabout" } },
  "metrics": { "throughput": 12.0 }
}
```

List with `GET /api/v1/replays`, delete with `DELETE /api/v1/replays/{replayId}`. Saving a replay also creates a completed historical run with batch ID `replay`.

The SQLite path is controlled by `DB_PATH`. `backend/src/database/db.py` creates these tables on startup:

- `configurations`: JSON configuration records.
- `simulation_runs`: status, elapsed/duration, controller type, seed, arrival rate, batch ID, configuration JSON, summary metrics, and timestamp.
- `run_metrics`: one JSON metrics record per run and tick.
- `sweep_sessions`: sweep configuration and complete results JSON.
- `saved_replays`: named configuration and metrics JSON.

SQLite uses WAL mode, a five-second busy timeout, and foreign keys. Docker stores the database in the `traffic_data` named volume; deleting that volume deletes persisted studies and replays.

## Contracts and Metrics

`shared/schemas/config.schema.json` is the validation schema for versioned configuration payloads. `snapshot.schema.json` and `vehicle_state.json` describe shared snapshot and vehicle shapes, although runtime route validation is currently centered on configuration validation. The authoritative metric names and formulas are implemented under `backend/src/metrics/definitions/` and aggregated by `MetricCollector`; the API exposes the resulting dictionary rather than a separate metric envelope.

## Troubleshooting

- If the dashboard cannot reach the backend in native mode, confirm port `8000` is listening and use the Vite proxy or set `VITE_API_URL` and `VITE_WS_URL` explicitly.
- If Docker's frontend health check fails, inspect `docker compose logs frontend backend`; the Nginx image proxies `/api`, `/ws`, and `/health` to the backend service.
- If old study data is unexpected, inspect `DB_PATH` and the active Compose volume before removing anything.
