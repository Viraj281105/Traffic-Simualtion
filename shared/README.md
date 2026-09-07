# Shared Contracts Layer

This directory contains the JSON Schema files shared conceptually by the backend and frontend. The backend currently loads `config.schema.json` for versioned request validation; the snapshot schemas document payload shapes but are not automatically applied to every WebSocket response.

To ensure strict decoupling, it contains **zero executable code**. It defines structural formats in programming language-independent formats (JSON Schema), allowing both Python and TypeScript components to serialize, deserialize, and validate payloads reliably.

**Owners:** Joint ownership — modifications require mutual agreement between Backend and Frontend engineers.

---

## Folder Organization

```
shared/
├── schemas/
│   ├── config.schema.json        # Structural specification for Simulation Scenario Config
│   ├── snapshot.schema.json      # Structural specification for Real-time Simulation Engine Snapshot
│   └── vehicle_state.json        # Structural specification for individual vehicle telemetry states
└── README.md                     # This documentation file
```

---

## Schema Architecture & Data Contracts

### 1. Scenario Configuration Schema (`config.schema.json`)

Defines the parameters needed to initialize, customize, and save a simulation run.

- **Intersection Layout Settings**:
  - `simulation.duration` and `simulation.timeStep` control run length and tick size.
  - `geometry.intersectionType` is `fixed_time_signal` or `roundabout`.
  - `roads.laneWidth` and `roads.lanesPerApproach` describe road geometry.
  - `traffic.arrivalRate` and `traffic.arrivalDistribution` describe demand.
- **Simulation Controls**:
  - `simulation.randomSeed` (integer): Random number generator seed.
- **Physics and Car-Following Parameters (Intelligent Driver Model)**:
  - `desired_speed` ($v_0$): Ideal target speed on clear lanes.
  - `safe_time_gap` ($T$): Preferred time headway behind leading cars.
  - `max_acceleration` ($a$): Maximum vehicle acceleration power.
  - `comfortable_deceleration` ($b$): Preferred braking rate.
  - `min_gap` ($s_0$): Minimum static safety margin spacing.

### 2. Real-Time Snapshot Schema (`snapshot.schema.json`)

Defines the state payload broadcasted by the backend at 10Hz over WebSockets to feed the visualization engine:

- **Global Context**:
  - `simulation_id` (string): UUID of the active run.
  - `tick` (integer): Monotonically increasing tick counter.
  - `sim_time` (number): Cumulative simulation elapsed time in seconds.
  - `status` (string): State of the simulation runtime lifecycle (e.g., `running`, `paused`, `completed`, `error`).
- **Vehicle Telemetry Collection**:
  - Contains an array of active vehicle states conforming to the vehicle state sub-schema.
- **Infrastructure Phase States**:
  - Traffic light active indexes, time remaining on the active phase, and signal statuses for signalized intersections.

### 3. Vehicle State Schema (`vehicle_state.json`)

Defines properties tracked for each active vehicle:

- `vehicle_id` (string): Unique identifier.
- `position_x`, `position_y` (numbers): Coordinates in meters relative to the intersection center $(0,0)$.
- `speed` (number): Instantaneous velocity in m/s.
- `acceleration` (number): Instantaneous acceleration in $m/s^2$.
- `lane_id` (string): Identifier of the lane currently occupied.
- `heading` (number): Orientation angle in radians (0 to $2\pi$).

---

## Schema Validation Workflow

To check the schema files themselves, run the repository validator. It verifies that each JSON file is well-formed and has a `$schema` field; it does not validate arbitrary captured API messages.

A Python-based validation utility is available to test schemas against mock samples:

- Execution Script: [`scripts/validate_schemas.py`](../scripts/validate_schemas.py)
- Command Line Run:
  ```bash
  python scripts/validate_schemas.py
  ```
- Shell Script Runner (automated via CI/CD):
  ```bash
  ./scripts/validate-schemas.sh
  ```
