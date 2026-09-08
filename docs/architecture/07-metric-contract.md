# Deliverable 7 — Metric Contract

> **Document Version:** 0.1.0
> **Last Updated:** 2026-07-23
> **Status:** Current metric reference (audited 2026-09-07)
> **Owner:** Both Developers (jointly)

---

## 1. Overview

This document summarizes the metrics currently returned by `MetricCollector`. The backend computes them and the frontend displays the returned dictionary. The implementation in `backend/src/metrics/collector.py` and `backend/src/metrics/definitions/` is authoritative; metric keys use camelCase.

### Metric Categories

| Category | Metrics | Purpose |
|----------|---------|---------|
| Operational Efficiency | Average Wait Time, Throughput, Queue Length Statistics | Core performance indicators |
| Traffic Flow Quality | Stop Count, Speed Variance Index, Travel Time Reliability | Smoothness of traffic flow |
| System Performance | Idle Opportunity Loss, Critical Saturation Volume | Intersection capacity utilization |
| Fairness | Directional Fairness Index | Equity across approaches |
| Physical Constraints | Space / Footprint Consumed | Land use comparison |

### Conventions

- All time values are in **seconds (s)** unless otherwise stated
- All distance values are in **meters (m)** unless otherwise stated
- All speed values are in **meters per second (m/s)** unless otherwise stated
- Dimensionless ratios are specified as such
- "Exited vehicles" = vehicles that have completed their journey through the intersection
- Warmup period vehicles are excluded from all metric calculations (configurable via `simulation.warmupTime`)

---

## 2. Operational Efficiency Metrics

### 2.1 Average Wait Time

| Attribute | Value |
|-----------|-------|
| **Metric ID** | `average_wait_time` |
| **Description** | Mean cumulative time that vehicles spend waiting (speed below threshold) while in the simulation. Lower is better. |
| **Units** | seconds (s) |
| **Inputs Required** | Per-vehicle `waitTime` (cumulative time with `speed < waitSpeedThreshold`) |
| **Update Frequency** | Every metric update tick (configurable, default 1 Hz) |
| **Final Aggregation** | Arithmetic mean across all exited vehicles |

**Mathematical Definition:**

$$
\bar{W} = \frac{1}{N} \sum_{i=1}^{N} W_i
$$

Where:
- $N$ = total number of exited vehicles (post-warmup)
- $W_i$ = cumulative wait time of vehicle $i$
- $\text{waitSpeedThreshold}$ = configurable (default 0.5 m/s)

**Running (real-time) value:** Computed over all vehicles that have exited so far. Updated as each vehicle exits.

**Edge Cases:**
- If no vehicles have exited yet, report `0.0`
- If all vehicles pass through without waiting, report `0.0`
- Vehicles still in the simulation are excluded from the final value (but included in a separate "current average" for the running metric)

---

### 2.2 Throughput

| Attribute | Value |
|-----------|-------|
| **Metric ID** | `throughput` |
| **Description** | Total number of vehicles that have successfully traversed the intersection and exited the simulation. Higher is better. |
| **Units** | vehicles (integer count) |
| **Inputs Required** | Vehicle exit events |
| **Update Frequency** | Every metric update tick |
| **Final Aggregation** | Total count at simulation end |

**Mathematical Definition:**

$$
T = \sum_{i=1}^{N} \mathbb{1}[\text{vehicle}_i \text{ exited}]
$$

**Throughput Rate (rolling):**

$$
T_{\text{rate}} = \frac{T_{\text{window}}}{\Delta t_{\text{window}}} \times 60
$$

Where:
- $T_{\text{window}}$ = vehicles exiting within the rolling window
- $\Delta t_{\text{window}}$ = rolling window duration (configurable, default 60s)
- Result is in vehicles per minute

**Edge Cases:**
- At simulation start, throughput is `0`
- Throughput rate may be `0` during low-traffic periods — this is valid, not an error
- Vehicles that are still in the simulation at completion are NOT counted

---

### 2.3 Queue Length Statistics

| Attribute | Value |
|-----------|-------|
| **Metric ID** | `queue_length` |
| **Description** | Statistical summary of queue lengths (vehicles waiting on each approach arm). Lower is better. |
| **Units** | vehicles (integer counts) |
| **Inputs Required** | Per-approach count of vehicles with `speed < waitSpeedThreshold` |
| **Update Frequency** | Every metric update tick |
| **Final Aggregation** | Multiple statistics (see below) |

**Mathematical Definition:**

Per approach direction $d$ at time $t$:

$$
Q_d(t) = |\{v : v.\text{direction} = d \wedge v.\text{speed} < \text{threshold} \wedge v.\text{state} \in \{\text{approaching}, \text{waiting}\}\}|
$$

**Aggregated Statistics:**

| Statistic | Formula | Description |
|-----------|---------|-------------|
| Current queue per direction | $Q_d(t)$ | Instantaneous queue length per approach |
| Average queue length | $\bar{Q} = \frac{1}{4} \sum_{d} \bar{Q}_d$ | Mean across all 4 approaches, time-averaged |
| Maximum queue length | $Q_{\max} = \max_{d,t} Q_d(t)$ | Worst queue observed across all directions and times |
| 95th percentile queue | $Q_{95}$ | 95th percentile of all observed queue lengths |

**Edge Cases:**
- Empty approaches have queue length `0`
- During warmup, queues are tracked but not included in final statistics
- If an approach has no vehicles assigned (e.g., `directionalSplit` = 0), its queue is always `0`

---

## 3. Traffic Flow Quality Metrics

### 3.1 Stop Count

| Attribute | Value |
|-----------|-------|
| **Metric ID** | `stop_count` |
| **Description** | Average number of times a vehicle comes to a complete stop before exiting. Fewer stops indicate smoother flow. Lower is better. |
| **Units** | stops per vehicle (dimensionless) |
| **Inputs Required** | Per-vehicle stop counter (incremented when speed drops below `stopSpeedThreshold` from above it) |
| **Update Frequency** | Every metric update tick |
| **Final Aggregation** | Arithmetic mean across all exited vehicles |

**Mathematical Definition:**

A stop event occurs when vehicle $i$'s speed transitions from $v \geq \theta_{\text{stop}}$ to $v < \theta_{\text{stop}}$:

$$
S_i = \sum_{t} \mathbb{1}[v_i(t-1) \geq \theta_{\text{stop}} \wedge v_i(t) < \theta_{\text{stop}}]
$$

$$
\bar{S} = \frac{1}{N} \sum_{i=1}^{N} S_i
$$

Where:
- $\theta_{\text{stop}}$ = `stopSpeedThreshold` (default 0.1 m/s)
- $N$ = number of exited vehicles (post-warmup)

**Edge Cases:**
- A vehicle that never stops has $S_i = 0$
- A vehicle that arrives at a red light and waits without moving counts as 1 stop (the initial deceleration to zero)
- Repeated oscillations around the threshold should not double-count (use hysteresis or minimum time between counts)

---

### 3.2 Speed Variance Index

| Attribute | Value |
|-----------|-------|
| **Metric ID** | `speed_variance` |
| **Description** | Coefficient of variation (CV) of vehicle speeds across the simulation, capturing how variable vehicle speeds are. Lower indicates more uniform flow. Lower is better. |
| **Units** | dimensionless (ratio) |
| **Inputs Required** | All vehicle speeds at each metric update tick |
| **Update Frequency** | Every metric update tick |
| **Final Aggregation** | Time-averaged CV |

**Mathematical Definition:**

At each metric update tick $t$, given $M(t)$ active vehicles:

$$
\bar{v}(t) = \frac{1}{M(t)} \sum_{j=1}^{M(t)} v_j(t)
$$

$$
\sigma_v(t) = \sqrt{\frac{1}{M(t)} \sum_{j=1}^{M(t)} (v_j(t) - \bar{v}(t))^2}
$$

$$
\text{CV}(t) = \frac{\sigma_v(t)}{\bar{v}(t)}
$$

$$
\text{SVI} = \frac{1}{T} \sum_{t=1}^{T} \text{CV}(t)
$$

Where $T$ = number of metric update ticks (post-warmup).

**Edge Cases:**
- If $\bar{v}(t) = 0$ (all vehicles stopped), CV is undefined. Use $\text{CV}(t) = 0$ in this case (all vehicles have the same speed: zero).
- If fewer than 2 vehicles are active, skip that tick in the average.
- Values typically range from 0 (perfectly uniform) to ~2.0 (highly variable).

---

### 3.3 Travel Time Reliability

| Attribute | Value |
|-----------|-------|
| **Metric ID** | `travel_time_reliability` |
| **Description** | Planning Time Index (PTI): ratio of the 95th percentile travel time to the median travel time. Measures how much extra time travelers must budget. Closer to 1.0 is better. |
| **Units** | dimensionless (ratio) |
| **Inputs Required** | Per-vehicle total travel time (`exitTime - spawnTime`) |
| **Update Frequency** | Updated each time a vehicle exits |
| **Final Aggregation** | Single ratio computed over all exited vehicles |

**Mathematical Definition:**

Given travel times $\{TT_1, TT_2, \ldots, TT_N\}$ for all $N$ exited vehicles:

$$
\text{PTI} = \frac{TT_{95}}{TT_{50}}
$$

Where:
- $TT_{95}$ = 95th percentile of travel times
- $TT_{50}$ = median (50th percentile) of travel times

**Edge Cases:**
- If fewer than 20 vehicles have exited, the percentile calculation may be unreliable. Report the value but flag it as "low sample size."
- If $TT_{50} = 0$, this indicates a data error (a vehicle cannot have zero travel time). Report `null`.
- A perfectly reliable system has PTI = 1.0. Real-world values are typically 1.5–3.0.

---

## 4. System Performance Metrics

### 4.1 Idle Opportunity Loss

| Attribute | Value |
|-----------|-------|
| **Metric ID** | `idle_opportunity_loss` |
| **Description** | Fraction of time the intersection capacity is wasted — specifically, time periods where the intersection blocks movement (e.g., red signal) but no vehicles are waiting on the green approach. Applicable primarily to fixed-time signals. Lower is better. |
| **Units** | dimensionless (0 to 1) |
| **Inputs Required** | Signal phase state, queue lengths per approach |
| **Update Frequency** | Every simulation tick |
| **Final Aggregation** | Ratio of idle ticks to total ticks |

**Mathematical Definition:**

For a fixed-time signal at tick $t$:

Let $G(t)$ = set of approaches that currently have green, and $R(t)$ = set of approaches that currently have red.

An "idle opportunity loss" tick occurs when:
- Some approach in $R(t)$ has vehicles waiting ($Q_d(t) > 0$ for some $d \in R(t)$)
- AND all approaches in $G(t)$ have no vehicles ($Q_d(t) = 0$ for all $d \in G(t)$)

$$
\text{IOL} = \frac{\sum_{t} \mathbb{1}[\exists d \in R(t): Q_d(t) > 0 \wedge \forall d' \in G(t): Q_{d'}(t) = 0]}{T_{\text{total}}}
$$

**For roundabouts:** IOL is always `0.0` because roundabouts do not have fixed phases that block movement. Vehicles yield dynamically.

**Edge Cases:**
- During all-red phases, if any approach has vehicles, the tick counts as IOL
- During warmup period, IOL ticks are excluded
- A value of 0.0 means the signal phases are perfectly matched to demand

---

### 4.2 Critical Saturation Volume

| Attribute | Value |
|-----------|-------|
| **Metric ID** | `critical_saturation_volume` |
| **Description** | The maximum arrival rate (vehicles per second) at which the intersection can still maintain stable queue lengths (queues do not grow unbounded). Higher is better (more capacity). |
| **Units** | vehicles per second (veh/s) |
| **Inputs Required** | Time-averaged throughput rate, time-averaged arrival rate, queue growth trend |
| **Update Frequency** | Calculated at simulation end |
| **Final Aggregation** | Single value |

**Mathematical Definition:**

The saturation volume is estimated by observing queue dynamics:

$$
\text{CSV} \approx \frac{T_{\text{total}}}{t_{\text{effective}}} \times \lambda_{\text{config}}
$$

Where:
- $T_{\text{total}}$ = total throughput (exited vehicles)
- $t_{\text{effective}}$ = simulation duration minus warmup
- $\lambda_{\text{config}}$ = configured arrival rate

**Simplified practical approach:**

If $\text{throughput rate} \geq \text{arrival rate}$ → the system is not saturated at the configured rate.

The CSV is estimated as the arrival rate at which the average queue length growth rate approaches zero:

$$
\text{CSV} = \lambda_{\text{config}} \times \frac{T_{\text{total}}}{V_{\text{spawned}}}
$$

Where $V_{\text{spawned}}$ = total vehicles spawned (post-warmup).

**Edge Cases:**
- If the simulation duration is too short, CSV may be inaccurate. Minimum recommended: 180 seconds post-warmup.
- If the configured arrival rate already saturates the system, CSV = observed throughput rate.
- For roundabouts, capacity depends on circulating flow; CSV should be interpreted carefully.

---

## 5. Fairness Metrics

### 5.1 Directional Fairness Index

| Attribute | Value |
|-----------|-------|
| **Metric ID** | `directional_fairness` |
| **Description** | Jain's Fairness Index applied to average wait times across the four approach directions. A value of 1.0 means all directions experience equal wait times. Higher is better. |
| **Units** | dimensionless (0 to 1) |
| **Inputs Required** | Average wait time per direction |
| **Update Frequency** | Every metric update tick |
| **Final Aggregation** | Single value at simulation end |

**Mathematical Definition:**

Given average wait times per direction $\{\bar{W}_{\text{north}}, \bar{W}_{\text{south}}, \bar{W}_{\text{east}}, \bar{W}_{\text{west}}\}$:

$$
J = \frac{\left(\sum_{d=1}^{4} \bar{W}_d\right)^2}{4 \cdot \sum_{d=1}^{4} \bar{W}_d^2}
$$

This is Jain's Fairness Index for 4 users (directions).

**Properties:**
- $J = 1.0$: All directions have equal average wait time (perfectly fair)
- $J = 0.25$: Only one direction has non-zero wait time (maximally unfair for 4 directions)
- Range: $[1/n, 1]$ where $n = 4$

**Edge Cases:**
- If all directions have $\bar{W}_d = 0$ (no waiting), $J = 1.0$ (perfectly fair)
- If a direction has no vehicles (e.g., `directionalSplit` = 0), exclude it from the calculation and adjust $n$
- For symmetric configurations (equal arrival rates, equal green times), $J$ should be very close to 1.0

---

## 6. Physical Constraints Metrics

### 6.1 Space / Footprint Consumed

| Attribute | Value |
|-----------|-------|
| **Metric ID** | `footprint` |
| **Description** | Total land area consumed by the intersection infrastructure. This is a static metric determined by geometry, not by simulation dynamics. Lower is better (more land-efficient). |
| **Units** | square meters (m²) |
| **Inputs Required** | Intersection geometry from configuration |
| **Update Frequency** | Computed once at simulation initialization |
| **Final Aggregation** | Single value |

**Mathematical Definition:**

**Fixed-Time Signal:**

The footprint is the area of the intersection box formed by the crossing lanes:

$$
A_{\text{signal}} = (n_{\text{NS}} \times w_{\text{lane}}) \times (n_{\text{EW}} \times w_{\text{lane}})
$$

Where:
- $n_{\text{NS}}$ = total lanes on North + South approaches (both directions)
- $n_{\text{EW}}$ = total lanes on East + West approaches (both directions)
- $w_{\text{lane}}$ = lane width

For 2 lanes per approach: $A = (2 \times 2 \times 3.5) \times (2 \times 2 \times 3.5) = 14 \times 14 = 196 \text{ m}^2$

**Roundabout:**

The footprint is the area of the outer circle:

$$
A_{\text{roundabout}} = \pi \times r_{\text{outer}}^2
$$

For $r_{\text{outer}} = 20$m: $A = \pi \times 400 \approx 1256.6 \text{ m}^2$

**Edge Cases:**
- Footprint does not change during simulation — it is constant
- For comparison purposes, include the approach taper areas if significantly different between designs
- This metric provides context: roundabouts use more land but may provide better flow

---

## 7. Metric Summary Table

| # | Metric ID | Category | Units | Direction | Running? | Key Formula |
|---|-----------|----------|-------|-----------|----------|-------------|
| 1 | `average_wait_time` | Operational Efficiency | seconds | Lower ↓ | ✅ | $\bar{W} = \frac{1}{N}\sum W_i$ |
| 2 | `throughput` | Operational Efficiency | vehicles | Higher ↑ | ✅ | Count of exited vehicles |
| 3 | `queue_length` | Operational Efficiency | vehicles | Lower ↓ | ✅ | Per-approach count, aggregated |
| 4 | `stop_count` | Traffic Flow Quality | stops/vehicle | Lower ↓ | ✅ | $\bar{S} = \frac{1}{N}\sum S_i$ |
| 5 | `speed_variance` | Traffic Flow Quality | dimensionless | Lower ↓ | ✅ | Time-averaged CV of speeds |
| 6 | `travel_time_reliability` | Traffic Flow Quality | dimensionless | Closer to 1.0 | ❌ | $\text{PTI} = TT_{95} / TT_{50}$ |
| 7 | `idle_opportunity_loss` | System Performance | dimensionless | Lower ↓ | ✅ | Idle ticks / total ticks |
| 8 | `critical_saturation_volume` | System Performance | veh/s | Higher ↑ | ❌ | Capacity estimation |
| 9 | `directional_fairness` | Fairness | dimensionless | Higher ↑ | ✅ | Jain's Fairness Index |
| 10 | `footprint` | Physical Constraints | m² | Lower ↓ | ❌ | Geometric area calculation |

**Direction:** Whether higher or lower values indicate better performance.
**Running?:** Whether the metric is updated in real-time snapshots (✅) or computed only at simulation end (❌).

---

## 8. Metric Output Schema

The final metric output (returned after simulation completion) follows this structure:

```json
{
  "simulationId": "sim_a1b2c3d4",
  "configId": "cfg_fixed_time_default",
  "controllerType": "fixed_time_signal",
  "simulationDuration": 300,
  "effectiveDuration": 270,
  "totalVehiclesProcessed": 185,
  "computedAt": "2026-07-23T14:35:00.000Z",

  "metrics": {
    "average_wait_time": {
      "value": 23.4,
      "unit": "seconds",
      "sampleSize": 185,
      "confidence": "high"
    },
    "throughput": {
      "value": 185,
      "unit": "vehicles",
      "rate": 41.1,
      "rateUnit": "vehicles_per_minute"
    },
    "queue_length": {
      "average": 4.25,
      "maximum": 12,
      "percentile95": 9,
      "unit": "vehicles",
      "perDirection": {
        "north": { "average": 4.8, "maximum": 12 },
        "south": { "average": 3.1, "maximum": 8 },
        "east": { "average": 5.2, "maximum": 11 },
        "west": { "average": 3.9, "maximum": 9 }
      }
    },
    "stop_count": {
      "value": 2.07,
      "unit": "stops_per_vehicle",
      "total": 383
    },
    "speed_variance": {
      "value": 0.45,
      "unit": "dimensionless"
    },
    "travel_time_reliability": {
      "value": 1.8,
      "unit": "dimensionless",
      "median_travel_time": 25.0,
      "p95_travel_time": 45.0
    },
    "idle_opportunity_loss": {
      "value": 0.12,
      "unit": "dimensionless"
    },
    "critical_saturation_volume": {
      "value": 0.72,
      "unit": "vehicles_per_second",
      "confidence": "medium"
    },
    "directional_fairness": {
      "value": 0.85,
      "unit": "dimensionless",
      "perDirection": {
        "north": 25.1,
        "south": 21.8,
        "east": 28.3,
        "west": 18.4
      }
    },
    "footprint": {
      "value": 196.0,
      "unit": "square_meters"
    }
  }
}
```

---

## 9. Cross-References

| Topic | Document |
|-------|----------|
| Shared contract layer | [04-shared-contract-layer.md](./04-shared-contract-layer.md) |
| Snapshot (running metrics) | [05-snapshot-contract.md](./05-snapshot-contract.md) |
| Configuration (metric settings) | [06-scenario-configuration-contract.md](./06-scenario-configuration-contract.md) |
| Communication (metric endpoints) | [08-communication-contract.md](./08-communication-contract.md) |
