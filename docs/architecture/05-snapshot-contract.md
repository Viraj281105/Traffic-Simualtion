# Deliverable 5 — Snapshot Contract

> **Document Version:** 0.1.0
> **Last Updated:** 2026-07-23
> **Status:** Phase 0 — Architecture Specification
> **Owner:** Both Developers (jointly)

---

## 1. Overview

A **Snapshot** is a complete, self-contained representation of the simulation state at a single point in time. The backend emits snapshots at a fixed frequency (configurable, default 10 Hz). The frontend consumes snapshots to render the visualization and display metrics.

### Design Principles

1. **Self-contained** — Every snapshot includes all information needed to render a single frame. No external lookups required.
2. **Extensible** — New controller types can be added without modifying the core snapshot structure.
3. **Versioned** — Every snapshot carries its schema version so consumers can detect incompatibilities.
4. **Immutable** — Once emitted, a snapshot is never modified. Each tick produces a new snapshot.

---

## 2. Top-Level Schema

| # | Field | Type | Required | Description | Units | Example |
|---|-------|------|----------|-------------|-------|---------|
| 1 | `schemaVersion` | `string` | ✅ | Semantic version of the snapshot schema | — | `"1.0.0"` |
| 2 | `simulationId` | `string` | ✅ | Unique identifier for this simulation run | — | `"sim_a1b2c3d4"` |
| 3 | `configId` | `string` | ✅ | Identifier of the scenario configuration used | — | `"cfg_fixed_time_default"` |
| 4 | `timestamp` | `number` | ✅ | Simulation time elapsed since start | seconds (s) | `45.3` |
| 5 | `frameNumber` | `integer` | ✅ | Sequential frame counter (0-indexed) | — | `453` |
| 6 | `tick` | `integer` | ✅ | Simulation tick counter (0-indexed) | — | `453` |
| 7 | `wallClockTime` | `string` | ✅ | ISO 8601 timestamp of when this snapshot was generated | — | `"2026-07-23T14:30:00.123Z"` |
| 8 | `samplingFrequency` | `number` | ✅ | Rate at which snapshots are emitted | Hz | `10.0` |
| 9 | `deltaTime` | `number` | ✅ | Time step between ticks | seconds (s) | `0.1` |
| 10 | `vehicles` | `array<Vehicle>` | ✅ | List of all vehicles currently in the simulation | — | See Section 3 |
| 11 | `intersection` | `IntersectionState` | ✅ | Current state of the intersection | — | See Section 4 |
| 12 | `controller` | `ControllerState` | ✅ | Current state of the active controller | — | See Section 5 |
| 13 | `metrics` | `RunningMetrics` | ✅ | Real-time metric values computed up to this tick | — | See Section 6 |
| 14 | `vehicleCounts` | `VehicleCounts` | ✅ | Summary counts of vehicles by state | — | See Section 7 |
| 15 | `simulationStatus` | `string` | ✅ | Current simulation status | — | `"running"` |
| 16 | `units` | `UnitSystem` | ✅ | Unit system used in this snapshot | — | See Section 8 |

---

## 3. Vehicle Object

Each entry in the `vehicles` array describes one vehicle at this instant.

| # | Field | Type | Required | Description | Units | Example |
|---|-------|------|----------|-------------|-------|---------|
| 1 | `id` | `string` | ✅ | Unique vehicle identifier | — | `"veh_001"` |
| 2 | `x` | `number` | ✅ | X-coordinate of vehicle center | meters (m) | `125.4` |
| 3 | `y` | `number` | ✅ | Y-coordinate of vehicle center | meters (m) | `-30.2` |
| 4 | `speed` | `number` | ✅ | Current speed | m/s | `8.5` |
| 5 | `acceleration` | `number` | ✅ | Current acceleration (negative = deceleration) | m/s² | `-1.2` |
| 6 | `heading` | `number` | ✅ | Direction of travel, clockwise from North | degrees (°) | `90.0` |
| 7 | `length` | `number` | ✅ | Vehicle length | meters (m) | `4.5` |
| 8 | `width` | `number` | ✅ | Vehicle width | meters (m) | `2.0` |
| 9 | `state` | `string` | ✅ | Current vehicle state (enum: `approaching`, `waiting`, `crossing`, `in_roundabout`, `exited`) | — | `"waiting"` |
| 10 | `laneId` | `string` | ✅ | Current lane identifier | — | `"north_approach_lane_1"` |
| 11 | `direction` | `string` | ✅ | Origin approach direction (enum: `north`, `south`, `east`, `west`) | — | `"north"` |
| 12 | `turnIntent` | `string` | ✅ | Intended turn (enum: `left`, `straight`, `right`) | — | `"straight"` |
| 13 | `waitTime` | `number` | ✅ | Cumulative time this vehicle has spent waiting (speed < threshold) | seconds (s) | `12.3` |
| 14 | `stopCount` | `integer` | ✅ | Number of times this vehicle has come to a complete stop | — | `2` |
| 15 | `spawnTime` | `number` | ✅ | Simulation time when this vehicle was spawned | seconds (s) | `10.0` |
| 16 | `exitTime` | `number` | ❌ | Simulation time when this vehicle exited (null if still active) | seconds (s) | `55.3` |
| 17 | `distanceTraveled` | `number` | ✅ | Total distance traveled since spawn | meters (m) | `85.7` |

---

## 4. Intersection State Object

| # | Field | Type | Required | Description | Units | Example |
|---|-------|------|----------|-------------|-------|---------|
| 1 | `type` | `string` | ✅ | Intersection control type (enum: `fixed_time_signal`, `roundabout`) | — | `"fixed_time_signal"` |
| 2 | `centerX` | `number` | ✅ | X-coordinate of intersection center | meters (m) | `0.0` |
| 3 | `centerY` | `number` | ✅ | Y-coordinate of intersection center | meters (m) | `0.0` |
| 4 | `boundingRadius` | `number` | ✅ | Radius of the intersection's bounding circle | meters (m) | `25.0` |
| 5 | `approaches` | `array<Approach>` | ✅ | List of approach arms | — | See below |

### Approach Object

| # | Field | Type | Required | Description | Units | Example |
|---|-------|------|----------|-------------|-------|---------|
| 1 | `direction` | `string` | ✅ | Approach direction (enum: `north`, `south`, `east`, `west`) | — | `"north"` |
| 2 | `queueLength` | `integer` | ✅ | Number of vehicles currently queued on this approach | — | `5` |
| 3 | `laneCount` | `integer` | ✅ | Number of lanes on this approach | — | `2` |

---

## 5. Controller State Object (Extensible)

The controller state uses a **discriminated union** pattern. The `type` field determines which additional fields are present.

### 5.1 Base Controller State (always present)

| # | Field | Type | Required | Description | Units | Example |
|---|-------|------|----------|-------------|-------|---------|
| 1 | `type` | `string` | ✅ | Controller type (discriminator) | — | `"fixed_time_signal"` |
| 2 | `timeInCurrentState` | `number` | ✅ | Time elapsed in current controller state | seconds (s) | `15.2` |

### 5.2 Fixed-Time Signal State (when `type` = `"fixed_time_signal"`)

| # | Field | Type | Required | Description | Units | Example |
|---|-------|------|----------|-------------|-------|---------|
| 3 | `currentPhase` | `string` | ✅ | Active signal phase (enum: `ns_green`, `ns_yellow`, `ew_green`, `ew_yellow`, `all_red`) | — | `"ns_green"` |
| 4 | `phaseTimeRemaining` | `number` | ✅ | Time remaining in the current phase | seconds (s) | `14.8` |
| 5 | `cycleNumber` | `integer` | ✅ | Current signal cycle count | — | `3` |
| 6 | `signals` | `array<SignalHead>` | ✅ | State of each signal head | — | See below |

#### SignalHead Object

| # | Field | Type | Required | Description | Units | Example |
|---|-------|------|----------|-------------|-------|---------|
| 1 | `direction` | `string` | ✅ | Which approach this signal serves | — | `"north"` |
| 2 | `color` | `string` | ✅ | Current signal color (enum: `green`, `yellow`, `red`) | — | `"green"` |

### 5.3 Roundabout State (when `type` = `"roundabout"`)

| # | Field | Type | Required | Description | Units | Example |
|---|-------|------|----------|-------------|-------|---------|
| 3 | `innerRadius` | `number` | ✅ | Inner radius of the roundabout | meters (m) | `10.0` |
| 4 | `outerRadius` | `number` | ✅ | Outer radius of the roundabout | meters (m) | `20.0` |
| 5 | `circulatingCount` | `integer` | ✅ | Number of vehicles currently in the roundabout circle | — | `4` |
| 6 | `yieldingCount` | `integer` | ✅ | Number of vehicles currently yielding at entry | — | `2` |
| 7 | `gapAcceptance` | `number` | ✅ | Current critical gap threshold | seconds (s) | `4.0` |

### 5.4 Adding Future Controllers

To add a new controller type (e.g., `adaptive_signal`):
1. Add the type value to the `ControllerType` enum in `shared/enums/controller-type.md`
2. Define the controller-specific fields in a new subsection (e.g., 5.4 Adaptive Signal State)
3. Update `snapshot.schema.json` with the new discriminated union variant
4. No modification to the base snapshot structure is required

---

## 6. Running Metrics Object

Real-time metric values computed up to the current tick. All values are cumulative/rolling.

| # | Field | Type | Required | Description | Units | Example |
|---|-------|------|----------|-------------|-------|---------|
| 1 | `averageWaitTime` | `number` | ✅ | Mean wait time across all vehicles that have exited | seconds (s) | `23.4` |
| 2 | `throughput` | `number` | ✅ | Total vehicles that have completed their journey | vehicles | `42` |
| 3 | `throughputRate` | `number` | ✅ | Vehicles exiting per minute (rolling window) | vehicles/min | `8.4` |
| 4 | `currentQueueLengths` | `object` | ✅ | Queue length per direction `{ "north": 5, "south": 3, "east": 7, "west": 2 }` | vehicles | See example |
| 5 | `maxQueueLength` | `integer` | ✅ | Maximum queue length observed on any approach | vehicles | `12` |
| 6 | `averageQueueLength` | `number` | ✅ | Mean queue length across all approaches | vehicles | `4.25` |
| 7 | `totalStops` | `integer` | ✅ | Total number of stops across all vehicles | — | `87` |
| 8 | `averageStopsPerVehicle` | `number` | ✅ | Mean stop count per vehicle | — | `2.07` |
| 9 | `speedVarianceIndex` | `number` | ✅ | Coefficient of variation of vehicle speeds | dimensionless | `0.45` |
| 10 | `travelTimeReliability` | `number` | ✅ | Planning Time Index (95th percentile / median travel time) | dimensionless | `1.8` |
| 11 | `idleOpportunityLoss` | `number` | ✅ | Fraction of time the intersection has no demand but restricts movement | dimensionless (0-1) | `0.12` |
| 12 | `directionalFairnessIndex` | `number` | ✅ | Jain's Fairness Index across approach directions | dimensionless (0-1) | `0.85` |
| 13 | `activeVehicleCount` | `integer` | ✅ | Number of vehicles currently in the simulation | — | `18` |
| 14 | `totalVehiclesSpawned` | `integer` | ✅ | Total vehicles generated since simulation start | — | `60` |

---

## 7. Vehicle Counts Object

| # | Field | Type | Required | Description | Units | Example |
|---|-------|------|----------|-------------|-------|---------|
| 1 | `active` | `integer` | ✅ | Vehicles currently in the simulation | — | `18` |
| 2 | `approaching` | `integer` | ✅ | Vehicles approaching the intersection | — | `8` |
| 3 | `waiting` | `integer` | ✅ | Vehicles waiting (speed ≈ 0) | — | `5` |
| 4 | `crossing` | `integer` | ✅ | Vehicles currently crossing the intersection | — | `3` |
| 5 | `inRoundabout` | `integer` | ✅ | Vehicles circulating in the roundabout (0 for signal) | — | `0` |
| 6 | `exited` | `integer` | ✅ | Total vehicles that have completed their journey | — | `42` |

---

## 8. Unit System Object

| # | Field | Type | Required | Description | Example |
|---|-------|------|----------|-------------|---------|
| 1 | `distance` | `string` | ✅ | Distance unit | `"meters"` |
| 2 | `speed` | `string` | ✅ | Speed unit | `"meters_per_second"` |
| 3 | `acceleration` | `string` | ✅ | Acceleration unit | `"meters_per_second_squared"` |
| 4 | `time` | `string` | ✅ | Time unit | `"seconds"` |
| 5 | `angle` | `string` | ✅ | Angle unit | `"degrees"` |

---

## 9. Simulation Status Enum

| Value | Description |
|-------|-------------|
| `"initialized"` | Simulation is being set up |
| `"running"` | Simulation is actively ticking |
| `"paused"` | Simulation is paused (can be resumed) |
| `"completed"` | Simulation has finished (reached max time or max vehicles) |
| `"error"` | Simulation encountered an error |

---

## 10. Example Snapshot Payload

```json
{
  "schemaVersion": "1.0.0",
  "simulationId": "sim_a1b2c3d4",
  "configId": "cfg_fixed_time_default",
  "timestamp": 45.3,
  "frameNumber": 453,
  "tick": 453,
  "wallClockTime": "2026-07-23T14:30:00.123Z",
  "samplingFrequency": 10.0,
  "deltaTime": 0.1,
  "simulationStatus": "running",

  "vehicles": [
    {
      "id": "veh_001",
      "x": 0.0,
      "y": -50.0,
      "speed": 0.0,
      "acceleration": 0.0,
      "heading": 0.0,
      "length": 4.5,
      "width": 2.0,
      "state": "waiting",
      "laneId": "north_approach_lane_1",
      "direction": "north",
      "turnIntent": "straight",
      "waitTime": 12.3,
      "stopCount": 2,
      "spawnTime": 10.0,
      "exitTime": null,
      "distanceTraveled": 85.7
    }
  ],

  "intersection": {
    "type": "fixed_time_signal",
    "centerX": 0.0,
    "centerY": 0.0,
    "boundingRadius": 25.0,
    "approaches": [
      { "direction": "north", "queueLength": 5, "laneCount": 2 },
      { "direction": "south", "queueLength": 3, "laneCount": 2 },
      { "direction": "east",  "queueLength": 7, "laneCount": 2 },
      { "direction": "west",  "queueLength": 2, "laneCount": 2 }
    ]
  },

  "controller": {
    "type": "fixed_time_signal",
    "timeInCurrentState": 15.2,
    "currentPhase": "ns_green",
    "phaseTimeRemaining": 14.8,
    "cycleNumber": 3,
    "signals": [
      { "direction": "north", "color": "green" },
      { "direction": "south", "color": "green" },
      { "direction": "east",  "color": "red" },
      { "direction": "west",  "color": "red" }
    ]
  },

  "metrics": {
    "averageWaitTime": 23.4,
    "throughput": 42,
    "throughputRate": 8.4,
    "currentQueueLengths": { "north": 5, "south": 3, "east": 7, "west": 2 },
    "maxQueueLength": 12,
    "averageQueueLength": 4.25,
    "totalStops": 87,
    "averageStopsPerVehicle": 2.07,
    "speedVarianceIndex": 0.45,
    "travelTimeReliability": 1.8,
    "idleOpportunityLoss": 0.12,
    "directionalFairnessIndex": 0.85,
    "activeVehicleCount": 18,
    "totalVehiclesSpawned": 60
  },

  "vehicleCounts": {
    "active": 18,
    "approaching": 8,
    "waiting": 5,
    "crossing": 3,
    "inRoundabout": 0,
    "exited": 42
  },

  "units": {
    "distance": "meters",
    "speed": "meters_per_second",
    "acceleration": "meters_per_second_squared",
    "time": "seconds",
    "angle": "degrees"
  }
}
```

---

## 11. Extensibility Guidelines

### Adding a New Field

1. Add the field as **optional** in the schema
2. Provide a default value or document that `null` is acceptable
3. Update type documentation in `shared/types/`
4. Both sides must handle the field being absent (for backward compatibility)

### Adding a New Controller Type

1. Add the type value to `ControllerType` enum
2. Define controller-specific fields as a new variant in Section 5
3. Add a `oneOf` variant to the JSON Schema's `controller` definition
4. Frontend adds a new renderer for the controller type
5. Backend implements the controller and populates the new fields
6. The core snapshot structure remains unchanged

### Adding a New Vehicle State

1. Add the value to the `VehicleState` enum
2. Document the transition rules (when does a vehicle enter/exit this state)
3. Update vehicle count object if a new count category is needed
4. Frontend may need a new visual representation for the state

---

## 12. Cross-References

| Topic | Document |
|-------|----------|
| Shared contract layer | [04-shared-contract-layer.md](./04-shared-contract-layer.md) |
| Configuration contract | [06-scenario-configuration-contract.md](./06-scenario-configuration-contract.md) |
| Metric definitions | [07-metric-contract.md](./07-metric-contract.md) |
| Communication (snapshot streaming) | [08-communication-contract.md](./08-communication-contract.md) |
