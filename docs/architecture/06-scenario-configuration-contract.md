# Deliverable 6 — Scenario Configuration Contract

> **Document Version:** 0.1.0
> **Last Updated:** 2026-07-23
> **Status:** Current schema reference (audited 2026-09-07)
> **Owner:** Both Developers (jointly)

---

## 1. Overview

A **Scenario Configuration** is a JSON document that fully describes a simulation run before it begins. It specifies:

- How long to simulate
- What type of intersection controller to use
- How many vehicles to generate and how
- Road geometry and lane configuration
- Physics parameters
- Which metrics to collect
- Visualization preferences

The versioned API accepts this configuration over REST and validates it against `shared/schemas/config.schema.json`. The dashboard's compact `/api/simulation/config` payload is expanded by `backend/src/main.py`; it is documented separately in [../operations.md](../operations.md).

### Design Principles

1. **Complete** — Every parameter needed to reproduce a simulation run is in the config
2. **Defaulted** — Every field has a sensible default; minimal configs are valid
3. **Validated** — JSON Schema validation catches errors before simulation starts
4. **Deterministic** — Same config + same random seed = identical results

---

## 2. Configuration Sections

### 2.1 `simulation` — Simulation Parameters

| # | Field | Type | Required | Default | Description | Validation |
|---|-------|------|----------|---------|-------------|------------|
| 1 | `duration` | `number` | ❌ | `300` | Total simulation duration | > 0, ≤ 3600 seconds |
| 2 | `timeStep` | `number` | ❌ | `0.1` | Simulation tick interval (dt) | > 0, ≤ 1.0 seconds |
| 3 | `warmupTime` | `number` | ❌ | `30` | Initial period excluded from all metrics — vehicles still approaching the intersection during this window (not yet interacting with it) are excluded from averages so they don't distort them. Enforced by a single early-return in `MetricCollector.update()`, so every per-tick-accumulated metric (queues, delay, throughput, speed variance, idle loss, etc.) is excluded consistently. Not the same as `controller.offset` (§2.6.1), which is a signal-timing concept, not an analysis one. | ≥ 0, < `duration` |
| 4 | `randomSeed` | `integer` | ❌ | `42` | Random number generator seed | ≥ 0 |
| 5 | `snapshotFrequency` | `number` | ❌ | `10` | Snapshots emitted per second | > 0, ≤ 60 Hz |

### 2.2 `traffic` — Traffic Demand

| # | Field | Type | Required | Default | Description | Validation |
|---|-------|------|----------|---------|-------------|------------|
| 1 | `totalVehicles` | `integer` | ❌ | `200` | Maximum vehicles to generate | > 0, ≤ 5000 |
| 2 | `arrivalRate` | `number` | ❌ | `0.5` | Mean vehicles arriving per second (Poisson) | > 0, ≤ 10.0 veh/s |
| 3 | `arrivalDistribution` | `string` | ❌ | `"poisson"` | Arrival process type | enum: `poisson`, `uniform`, `burst` |
| 4 | `directionalSplit` | `object` | ❌ | See below | Fraction of vehicles from each direction | Values sum to 1.0 |
| 5 | `turnProbabilities` | `object` | ❌ | See below | Turn intent probabilities | Values sum to 1.0 per direction |

#### Default `directionalSplit`
```json
{
  "north": 0.25,
  "south": 0.25,
  "east": 0.25,
  "west": 0.25
}
```

#### Default `turnProbabilities`
```json
{
  "left": 0.2,
  "straight": 0.6,
  "right": 0.2
}
```

### 2.3 `geometry` — Intersection Geometry

| # | Field | Type | Required | Default | Description | Validation |
|---|-------|------|----------|---------|-------------|------------|
| 1 | `intersectionType` | `string` | ✅ | — | Type of intersection | enum: `fixed_time_signal`, `roundabout` |
| 2 | `intersectionCenter` | `object` | ❌ | `{"x": 0, "y": 0}` | Center coordinates | — |

### 2.4 `roads` — Road Configuration

| # | Field | Type | Required | Default | Description | Validation |
|---|-------|------|----------|---------|-------------|------------|
| 1 | `approachLength` | `number` | ❌ | `200` | Length of each approach arm | > 50, ≤ 1000 meters |
| 2 | `laneWidth` | `number` | ❌ | `3.5` | Width of each lane | > 2.5, ≤ 5.0 meters |
| 3 | `lanesPerApproach` | `integer` | ❌ | `2` | Lane count applied to all four approaches | 1–4 (see `shared/schemas/config.schema.json`) |
| 4 | `speedLimit` | `number` | ❌ | `13.89` | Speed limit on approach roads | > 0, ≤ 30 m/s (≈108 km/h) |
| 5 | `approaches` | `array<ApproachConfig>` | ❌ | All 4 directions | Per-approach overrides | See below |

> **Asymmetric lane counts — not yet part of this contract.** The versioned config schema (`shared/schemas/config.schema.json`, enforced on `POST /api/v1/configs/validate` and `POST /api/v1/simulations`) only accepts `lanesPerApproach` as a single integer shared by all four approaches. Internally, the legacy live dashboard routes (`backend/src/main.py`) and the simulation engine (`backend/src/roads/network.py`) already accept a per-direction object (`{"north": 2, "south": 3, ...}`), but that shape is an implementation detail of the live/interactive path, not a validated or documented versioned-API feature. Officially supporting asymmetric per-direction lane counts in the versioned contract — including the schema, Pydantic models, and any dependent metric formulas such as [Space/Footprint Consumed](07-metric-contract.md#61-space--footprint-consumed) — is planned future work, not current behavior.

#### ApproachConfig Object

| # | Field | Type | Required | Default | Description | Validation |
|---|-------|------|----------|---------|-------------|------------|
| 1 | `direction` | `string` | ✅ | — | Approach direction | enum: `north`, `south`, `east`, `west` |
| 2 | `lanes` | `integer` | ❌ | Inherits from `lanesPerApproach` | Lane count for this approach | ≥ 1, ≤ 4 |
| 3 | `speedLimit` | `number` | ❌ | Inherits from `roads.speedLimit` | Speed limit for this approach | > 0 m/s |

### 2.5 `vehicleGeneration` — Vehicle Properties

| # | Field | Type | Required | Default | Description | Validation |
|---|-------|------|----------|---------|-------------|------------|
| 1 | `vehicleLength` | `object` | ❌ | `{"min": 4.0, "max": 5.0}` | Vehicle length range | min > 0, max ≥ min |
| 2 | `vehicleWidth` | `object` | ❌ | `{"min": 1.8, "max": 2.2}` | Vehicle width range | min > 0, max ≥ min |
| 3 | `desiredSpeed` | `object` | ❌ | `{"min": 11.0, "max": 15.0}` | Desired free-flow speed range | min > 0, max ≥ min, m/s |
| 4 | `maxAcceleration` | `number` | ❌ | `2.0` | Maximum comfortable acceleration | > 0 m/s² |
| 5 | `comfortDeceleration` | `number` | ❌ | `3.0` | Comfortable deceleration magnitude | > 0 m/s² |
| 6 | `minimumGap` | `number` | ❌ | `2.0` | Minimum spacing between vehicles at standstill | > 0 meters |
| 7 | `desiredTimeHeadway` | `number` | ❌ | `1.5` | Desired following time headway | > 0 seconds |
| 8 | `idmDelta` | `number` | ❌ | `4` | IDM acceleration exponent | > 0 |

### 2.6 `controller` — Controller-Specific Configuration

Uses a discriminated union based on `geometry.intersectionType`.

#### 2.6.1 Fixed-Time Signal Controller

Every duration below has a **canonical** field name (matching `FixedTimeSignalController`'s own naming, and the legacy live-dashboard config path) and, for three of them, one or two **legacy alias** field names retained for backward compatibility. All are accepted by both `shared/schemas/config.schema.json` and the typed `ControllerSection` Pydantic model (used by `POST /api/simulation/new`) — a canonical field is no longer silently dropped by the typed path the way it previously was when only the alias names were declared.

| # | Field | Type | Required | Default | Description | Validation |
|---|-------|------|----------|---------|-------------|------------|
| 1 | `straightRightDuration` (canonical) / `greenDuration` / `greenTime` (aliases) | `number` | ❌ | `30` | Green phase duration for the straight+right movement of each direction | > 5, ≤ 120 seconds |
| 2 | `leftDuration` | `number` | ❌ | `5` | Protected left-turn green phase duration | > 0, ≤ 60 seconds |
| 3 | `yellowDuration` (canonical) / `yellowTime` (alias) | `number` | ❌ | `4` | Yellow (amber) phase duration | > 2, ≤ 8 seconds |
| 4 | `allRedDuration` (canonical) / `allRedTime` (alias) | `number` | ❌ | `2` | All-red clearance interval | ≥ 0, ≤ 5 seconds |
| 5 | `phaseSequence` | `array<string>` | ❌ | `["ns_green", "ns_yellow", "all_red", "ew_green", "ew_yellow", "all_red"]` | Ordered phase sequence | See below |
| 6 | `offset` | `number` | ❌ | `0` | Signal phase-coordination offset — shifts the initial phase cursor at simulation start (e.g. for multi-intersection green-wave coordination). **Not** a metrics/analysis warm-up period — see [08-communication-contract.md](08-communication-contract.md) and `simulation.warmupTime` (§2.1) for that. | ≥ 0 seconds |

**Alias precedence** (when more than one name for the same duration is present in one config, `FixedTimeSignalController.__init__` resolves them in this order, highest priority first — later-checked aliases overwrite earlier ones if the canonical field is absent):
- Green: `straightRightDuration` > `greenTime` > `greenDuration`
- Yellow: `yellowDuration` > `yellowTime`
- All-red: `allRedDuration` > `allRedTime`
- Left: `leftDuration` only — no alias exists for this field.

If none of a duration's names are present, the hardcoded fallback (30 / 5 / 4 / 2 above) is used — chosen to match the canonical/alias defaults exactly, so the effective duration is the same regardless of which alias (or none) a given config uses.

**`phaseSequence` vocabulary:** each entry is either the literal string `"all_red"`, or `"<group>_<green|yellow>"` where `<group>` is one of `n`, `s`, `e`, `w` (a single approach) or `ns`/`sn`, `ew`/`we` (a paired, order-invariant approach group sharing one green — e.g. `ns_green` runs NORTH and SOUTH together). Green-phase duration uses `straightRightDuration` (after alias resolution above); yellow-phase duration uses `yellowDuration`; `all_red` uses `allRedDuration`. During a paired-group green phase, all three turn intents (including permissive left) are allowed for both directions in the group — left-turners crossing opposing straight traffic are arbitrated by `ConflictManager` (see [08-communication-contract.md](08-communication-contract.md)), not by a separate protected-left sub-phase. An entry that doesn't match this vocabulary raises a configuration error surfaced as `400 VALIDATION_ERROR` by `POST /api/v1/simulations` and `POST /api/simulation/new`. When `phaseSequence` is omitted entirely, the controller instead builds its original one-direction-at-a-time cycle (straight+right green → protected left green → yellow → all-red, repeated for N→S→E→W) — see the note on default-consistency below.

#### 2.6.2 Roundabout Controller

| # | Field | Type | Required | Default | Description | Validation |
|---|-------|------|----------|---------|-------------|------------|
| 1 | `innerRadius` | `number` | ❌ | `10` | Inner radius of the circulatory roadway | > 5, ≤ 50 meters |
| 2 | `outerRadius` | `number` | ❌ | `20` | Outer radius of the circulatory roadway | > `innerRadius` |
| 3 | `circulatingLanes` | `integer` | ❌ | `1` | **Reserved / future-only** — see note below | ≥ 1, ≤ 3 |
| 4 | `criticalGap` | `number` | ❌ | `4.0` | Minimum acceptable gap for entry | > 0, ≤ 10 seconds |
| 5 | `followUpTime` | `number` | ❌ | `2.5` | Time between consecutive entering vehicles | > 0 seconds |
| 6 | `entrySpeed` | `number` | ❌ | `5.0` | Maximum speed at roundabout entry | > 0 m/s |
| 7 | `circulatingSpeed` | `number` | ❌ | `8.0` | Target speed within the roundabout | > 0, ≤ 15 m/s |

> **`circulatingLanes` is reserved / future-only — it has no runtime effect today.** The value is accepted and schema-validated, and `RoundaboutController` stores it, but nothing in the engine ever reads it back out. The circulating lane count a roundabout actually uses is derived entirely from `roads.lanesPerApproach` (each approach's own incoming lane count doubles as its circulating lane count in `backend/src/roads/network.py` and `backend/src/controllers/roundabout.py`) — approach lanes, circulating lane indices, connection lanes, and exit lanes are all coupled through that one value, with no independent ring-lane-count path anywhere in the current implementation. `circulatingLanes` is being kept in the schema and Pydantic model (not removed or deprecated) because it is expected to become necessary once asymmetric `lanesPerApproach` (see §2.4 above) reaches roundabouts — a single ring can only have one physical lane count, independent of any one approach's lane count, so an asymmetric-lanes roundabout will need a real, independent ring-lane-count parameter. Making it functional will require explicit future design decisions for ring geometry and the approach-lane → ring-lane mapping; none of that exists yet.

### 2.7 `metrics` — Metric Collection Configuration

| # | Field | Type | Required | Default | Description | Validation |
|---|-------|------|----------|---------|-------------|------------|
| 1 | `enabled` | `array<string>` | ❌ | All metrics | List of metric IDs to compute | Valid metric IDs |
| 2 | `updateFrequency` | `number` | ❌ | `1.0` | How often metrics are recalculated | > 0 Hz |
| 3 | `rollingWindowSize` | `number` | ❌ | `60` | Time window for rolling calculations | > 0 seconds |
| 4 | `waitSpeedThreshold` | `number` | ❌ | `0.5` | Speed below which a vehicle is "waiting" | ≥ 0 m/s |
| 5 | `stopSpeedThreshold` | `number` | ❌ | `0.1` | Speed below which a vehicle is "stopped" | ≥ 0 m/s |

### 2.8 `visualization` — Frontend Display Preferences

| # | Field | Type | Required | Default | Description | Validation |
|---|-------|------|----------|---------|-------------|------------|
| 1 | `canvasWidth` | `integer` | ❌ | `800` | Canvas width | > 400 pixels |
| 2 | `canvasHeight` | `integer` | ❌ | `800` | Canvas height | > 400 pixels |
| 3 | `pixelsPerMeter` | `number` | ❌ | `3.0` | Rendering scale factor | > 0 |
| 4 | `showVehicleIds` | `boolean` | ❌ | `false` | Display vehicle IDs on canvas | — |
| 5 | `showQueueLengths` | `boolean` | ❌ | `true` | Display queue length overlays | — |
| 6 | `colorScheme` | `string` | ❌ | `"default"` | Color scheme for vehicle states | enum: `default`, `colorblind` |
| 7 | `trailLength` | `integer` | ❌ | `0` | Number of past positions to render as trail | ≥ 0 |

---

## 3. Complete Example: Fixed-Time Signal

```json
{
  "simulation": {
    "duration": 300,
    "timeStep": 0.1,
    "warmupTime": 30,
    "randomSeed": 42,
    "snapshotFrequency": 10
  },
  "traffic": {
    "totalVehicles": 200,
    "arrivalRate": 0.5,
    "arrivalDistribution": "poisson",
    "directionalSplit": {
      "north": 0.30,
      "south": 0.30,
      "east": 0.20,
      "west": 0.20
    },
    "turnProbabilities": {
      "left": 0.2,
      "straight": 0.6,
      "right": 0.2
    }
  },
  "geometry": {
    "intersectionType": "fixed_time_signal",
    "intersectionCenter": { "x": 0, "y": 0 }
  },
  "roads": {
    "approachLength": 200,
    "laneWidth": 3.5,
    "lanesPerApproach": 2,
    "speedLimit": 13.89
  },
  "vehicleGeneration": {
    "vehicleLength": { "min": 4.0, "max": 5.0 },
    "vehicleWidth": { "min": 1.8, "max": 2.2 },
    "desiredSpeed": { "min": 11.0, "max": 15.0 },
    "maxAcceleration": 2.0,
    "comfortDeceleration": 3.0,
    "minimumGap": 2.0,
    "desiredTimeHeadway": 1.5,
    "idmDelta": 4
  },
  "controller": {
    "greenTime": 30,
    "yellowTime": 4,
    "allRedTime": 2,
    "phaseSequence": ["ns_green", "ns_yellow", "all_red", "ew_green", "ew_yellow", "all_red"],
    "offset": 0
  },
  "metrics": {
    "enabled": ["average_wait_time", "throughput", "queue_length", "stop_count", "speed_variance", "travel_time_reliability", "idle_opportunity_loss", "critical_saturation_volume", "directional_fairness", "footprint"],
    "updateFrequency": 1.0,
    "rollingWindowSize": 60,
    "waitSpeedThreshold": 0.5,
    "stopSpeedThreshold": 0.1
  },
  "visualization": {
    "canvasWidth": 800,
    "canvasHeight": 800,
    "pixelsPerMeter": 3.0,
    "showVehicleIds": false,
    "showQueueLengths": true,
    "colorScheme": "default",
    "trailLength": 0
  }
}
```

---

## 4. Complete Example: Roundabout

```json
{
  "simulation": {
    "duration": 300,
    "timeStep": 0.1,
    "warmupTime": 30,
    "randomSeed": 42,
    "snapshotFrequency": 10
  },
  "traffic": {
    "totalVehicles": 200,
    "arrivalRate": 0.5,
    "arrivalDistribution": "poisson",
    "directionalSplit": {
      "north": 0.25,
      "south": 0.25,
      "east": 0.25,
      "west": 0.25
    },
    "turnProbabilities": {
      "left": 0.2,
      "straight": 0.6,
      "right": 0.2
    }
  },
  "geometry": {
    "intersectionType": "roundabout",
    "intersectionCenter": { "x": 0, "y": 0 }
  },
  "roads": {
    "approachLength": 200,
    "laneWidth": 3.5,
    "lanesPerApproach": 1,
    "speedLimit": 13.89
  },
  "vehicleGeneration": {
    "vehicleLength": { "min": 4.0, "max": 5.0 },
    "vehicleWidth": { "min": 1.8, "max": 2.2 },
    "desiredSpeed": { "min": 11.0, "max": 15.0 },
    "maxAcceleration": 2.0,
    "comfortDeceleration": 3.0,
    "minimumGap": 2.0,
    "desiredTimeHeadway": 1.5,
    "idmDelta": 4
  },
  "controller": {
    "innerRadius": 10,
    "outerRadius": 20,
    "circulatingLanes": 1,
    "criticalGap": 4.0,
    "followUpTime": 2.5,
    "entrySpeed": 5.0,
    "circulatingSpeed": 8.0
  },
  "metrics": {
    "enabled": ["average_wait_time", "throughput", "queue_length", "stop_count", "speed_variance", "travel_time_reliability", "idle_opportunity_loss", "critical_saturation_volume", "directional_fairness", "footprint"],
    "updateFrequency": 1.0,
    "rollingWindowSize": 60,
    "waitSpeedThreshold": 0.5,
    "stopSpeedThreshold": 0.1
  },
  "visualization": {
    "canvasWidth": 800,
    "canvasHeight": 800,
    "pixelsPerMeter": 3.0,
    "showVehicleIds": false,
    "showQueueLengths": true,
    "colorScheme": "default",
    "trailLength": 0
  }
}
```

`controller.circulatingLanes` in the example above (`1`) is reserved / future-only (see §2.6.2) — it is included because it is schema-valid and accepted, not because setting it changes simulation behavior. This roundabout's actual circulating lane count comes from `roads.lanesPerApproach` (also `1`, above).

---

## 5. Validation Summary

| Rule | Scope | Description |
|------|-------|-------------|
| Required field | `geometry.intersectionType` | Must be specified; no default |
| Range checks | All numeric fields | Each has documented min/max bounds |
| Enum checks | All string enums | Must be one of the documented values |
| Sum-to-one | `directionalSplit` values | Must sum to 1.0 (±0.01 tolerance) |
| Sum-to-one | `turnProbabilities` values | Must sum to 1.0 (±0.01 tolerance) |
| Cross-field | `warmupTime < duration` | Warmup cannot exceed total duration |
| Cross-field | `outerRadius > innerRadius` | Roundabout outer must exceed inner |
| Controller match | `controller` fields | Controller config must match `geometry.intersectionType` |

---

## 6. Minimal Valid Configuration

The smallest valid configuration requires only the intersection type:

```json
{
  "geometry": {
    "intersectionType": "fixed_time_signal"
  }
}
```

All other fields use their documented defaults.

---

## 7. Cross-References

| Topic | Document |
|-------|----------|
| Shared contract layer | [04-shared-contract-layer.md](./04-shared-contract-layer.md) |
| Snapshot schema | [05-snapshot-contract.md](./05-snapshot-contract.md) |
| Metric definitions | [07-metric-contract.md](./07-metric-contract.md) |
| Communication (config submission) | [08-communication-contract.md](./08-communication-contract.md) |
