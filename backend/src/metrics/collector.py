import math
from typing import Any, Dict, List

from src.core.enums import Direction
from src.metrics.definitions.derived_metrics import (
    calculate_average_travel_speed,
    calculate_critical_saturation_volume,
    calculate_queue_stability_index,
    calculate_space_footprint_consumed,
)
from src.metrics.definitions.fairness import calculate_directional_fairness
from src.metrics.definitions.idle_loss import calculate_idle_loss_tick
from src.metrics.definitions.queue_length import get_current_queue_lengths
from src.metrics.definitions.speed_variance import calculate_speed_variance_index
from src.metrics.definitions.stop_count import update_vehicle_stops
from src.metrics.definitions.throughput import (
    calculate_throughput,
    calculate_throughput_rate,
)
from src.metrics.definitions.travel_time import (
    MIN_RELIABLE_SAMPLE_SIZE,
    calculate_travel_time_reliability,
)
from src.metrics.definitions.wait_time import calculate_average_wait_time
from src.metrics.efficiency import calculate_master_efficiency_score
from src.vehicles.vehicle import Vehicle


class MetricCollector:
    """Manages the periodic aggregation of simulation operational metrics."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config: Dict[str, Any] = config
        sim_cfg = config.get("simulation", {})
        self.warmup_time: float = sim_cfg.get("warmupTime", 15.0)
        self.time_step: float = sim_cfg.get("timeStep", 0.1)

        # Hysteresis configuration
        veh_gen = config.get("vehicleGeneration", {})
        self.stop_speed_threshold: float = veh_gen.get("stopSpeedThreshold", 0.1)
        self.wait_speed_threshold: float = veh_gen.get("waitSpeedThreshold", 0.5)

        self.reset()

    def reset(self) -> None:
        self.idle_loss_ticks: int = 0
        self.total_ticks_post_warmup: int = 0
        self.congestion_recovery_time: float = 0.0
        self.demand_ticks: int = 0
        self.service_ticks: int = 0

        # Maintain list of queue lengths over time to compute time-average and max
        self.queue_history: List[Dict[str, int]] = []

        # Per-tick speed CV history (see speed_variance.py) for computing
        # the time-averaged SVI = (1/T) * sum(CV(t)) per the metric contract.
        self.speed_cv_history: List[float] = []

        # Per-vehicle wait_time/stop_count snapshot taken at the moment
        # warmup ends, so a vehicle already active at that point doesn't
        # have its pre-warmup wait/stops leak into post-warmup averages
        # (mirrors how averageDelay clips via effective_spawn_t below).
        self._warmup_baseline_wait: Dict[str, float] = {}
        self._warmup_baseline_stops: Dict[str, int] = {}
        self._warmup_baseline_captured: bool = False

    def update(
        self,
        current_time: float,
        active_vehicles: List[Vehicle],
        exited_vehicles: List[Vehicle],
        signals_state: Dict[Direction, str],
    ) -> None:
        """Ticks the metrics state checks (e.g. updating vehicle stop count hysteresis)."""
        # Always update stop count states regardless of warmup to keep vehicle state correct
        for v in active_vehicles:
            update_vehicle_stops(v, self.stop_speed_threshold)

        # Discard metrics check during warmup
        if current_time < self.warmup_time:
            return

        if not self._warmup_baseline_captured:
            # First post-warmup tick: snapshot the cumulative wait_time/
            # stop_count of every vehicle still active right now, so their
            # pre-warmup contribution can be subtracted later in
            # get_metrics() for any of them that exits post-warmup.
            for v in active_vehicles:
                self._warmup_baseline_wait[v.vehicle_id] = v.wait_time
                self._warmup_baseline_stops[v.vehicle_id] = v.stop_count
            self._warmup_baseline_captured = True

        # Increment post-warmup simulation ticks count
        self.total_ticks_post_warmup += 1

        if active_vehicles:
            self.demand_ticks += 1
            avg_speed = sum(v.speed for v in active_vehicles) / len(active_vehicles)
            if avg_speed > self.wait_speed_threshold:
                self.service_ticks += 1

        # Speed Variance Index: accumulate this tick's CV(t) into the
        # history used for the time-averaged SVI in get_metrics(). Per the
        # metric contract, ticks with fewer than 2 active vehicles are
        # skipped entirely rather than contributing a value.
        if len(active_vehicles) >= 2:
            self.speed_cv_history.append(
                calculate_speed_variance_index(active_vehicles)
            )

        # Track idle opportunity loss
        if calculate_idle_loss_tick(
            active_vehicles, signals_state, self.wait_speed_threshold
        ):
            self.idle_loss_ticks += 1

        # Save queue history
        current_queues = get_current_queue_lengths(
            active_vehicles, self.wait_speed_threshold
        )
        self.queue_history.append(current_queues)

        # Congestion Recovery: increment recovery time if total queue length across all approaches > 5
        if sum(current_queues.values()) > 5:
            self.congestion_recovery_time += self.time_step

    def get_metrics(
        self,
        current_time: float,
        active_vehicles: List[Vehicle],
        exited_vehicles: List[Vehicle],
        total_spawned: int,
    ) -> Dict[str, Any]:
        """Calculates and aggregates the complete metrics snapshot."""
        # Filter exited vehicles that completed their journey post-warmup
        post_warmup_exited = [
            v
            for v in exited_vehicles
            if (v.exit_time is not None and v.exit_time >= self.warmup_time)
            or (v.exit_time is None and v.spawn_time >= self.warmup_time)
        ]

        # Calculate current queue lengths
        curr_queues = get_current_queue_lengths(
            active_vehicles, self.wait_speed_threshold
        )

        # Compute max/time-averaged queue length per the metric contract
        # (docs/architecture/07-metric-contract.md §2.3): per-direction
        # time-average/maximum first, then averageQueueLength = mean of the
        # 4 per-direction averages and maxQueueLength = max over all
        # directions and ticks. (activeAverageQueueLength/queueStdDev remain
        # based on the intersection-wide total queue per tick — they are
        # undocumented, separate derived stats and are left unchanged.)
        directions = ["north", "south", "east", "west"]
        if self.queue_history:
            per_direction_avg = {}
            per_direction_max = {}
            for d in directions:
                series = [q.get(d, 0) for q in self.queue_history]
                per_direction_avg[d] = sum(series) / len(series)
                per_direction_max[d] = max(series)

            avg_q = round(sum(per_direction_avg.values()) / len(directions), 2)
            max_q = max(per_direction_max.values())

            all_queues_sums = [sum(q.values()) for q in self.queue_history]
            non_zero_queues = [q for q in all_queues_sums if q > 0]
            active_avg_q = (
                round(sum(non_zero_queues) / len(non_zero_queues), 2)
                if non_zero_queues
                else 0.0
            )
            if len(all_queues_sums) > 1:
                total_q_mean = sum(all_queues_sums) / len(all_queues_sums)
                var_q = sum((x - total_q_mean) ** 2 for x in all_queues_sums) / (
                    len(all_queues_sums) - 1
                )
                sd_q = round(math.sqrt(var_q), 2)
            else:
                sd_q = 0.0
        else:
            max_q = 0
            avg_q = 0.0
            active_avg_q = 0.0
            sd_q = 0.0

        # Compute control delay distribution (actual travel time minus free-flow time)
        delays: List[float] = []
        for v in post_warmup_exited:
            spawn_t = getattr(v, "spawn_time", 0.0)
            exit_t = getattr(v, "exit_time", None)
            if exit_t is not None and exit_t > spawn_t:
                effective_spawn_t = max(spawn_t, self.warmup_time)
                actual_travel_time = max(0.0, exit_t - effective_spawn_t)
                total_duration = exit_t - spawn_t
                if getattr(v, "route", None):
                    route_len = sum(
                        lane.length for lane in v.route if hasattr(lane, "length")
                    )
                    free_flow_time = route_len / max(
                        getattr(v, "desired_speed", 15.0), 1.0
                    )
                    # If spawned during warmup, scale free-flow time to post-warmup duration fraction
                    if spawn_t < self.warmup_time and total_duration > 0:
                        free_flow_time *= actual_travel_time / total_duration
                else:
                    free_flow_time = 0.0
                delays.append(max(0.0, actual_travel_time - free_flow_time))
            else:
                delays.append(getattr(v, "wait_time", 0.0))

        if delays:
            avg_delay = round(sum(delays) / len(delays), 2)
            sorted_d = sorted(delays)
            n_d = len(sorted_d)
            med_delay = round(
                sorted_d[n_d // 2]
                if n_d % 2 == 1
                else (sorted_d[n_d // 2 - 1] + sorted_d[n_d // 2]) / 2.0,
                2,
            )
            min_delay = round(sorted_d[0], 2)
            max_delay = round(sorted_d[-1], 2)
            k_d = (n_d - 1) * 0.95
            f_d = math.floor(k_d)
            c_d = math.ceil(k_d)
            p95_delay = round(
                sorted_d[int(f_d)]
                + (sorted_d[int(c_d)] - sorted_d[int(f_d)]) * (k_d - f_d),
                2,
            )
            if n_d > 1:
                var_d = sum((x - avg_delay) ** 2 for x in delays) / (n_d - 1)
                sd_delay = round(math.sqrt(var_d), 2)
            else:
                sd_delay = 0.0
        else:
            avg_delay = round(calculate_average_wait_time(post_warmup_exited), 2)
            med_delay = 0.0
            min_delay = 0.0
            max_delay = 0.0
            p95_delay = 0.0
            sd_delay = 0.0

        # average_wait_time / averageStopsPerVehicle / totalStops: subtract
        # each vehicle's warmup-boundary baseline (captured in update()) so
        # a vehicle that was already active when warmup ended doesn't have
        # its pre-warmup wait time / stops counted here — mirrors how
        # avg_delay above clips via effective_spawn_t. Vehicles that
        # spawned after warmup have no baseline entry (default 0), so
        # their full wait_time/stop_count counts as-is.
        #
        # totalStops previously subtracted a single scalar
        # (stops of vehicles that had *already exited* during warmup) from
        # the sum of stops of `post_warmup_exited` vehicles — a set that,
        # by construction, never includes those already-exited vehicles.
        # That scalar had no relationship to the quantity it was subtracted
        # from. Using the same per-vehicle baseline clip as
        # averageStopsPerVehicle makes totalStops == sum(clipped_stops),
        # i.e. consistent with avg_stops_per_vehicle * len(post_warmup_exited).
        clipped_waits: List[float] = []
        clipped_stops: List[int] = []
        for v in post_warmup_exited:
            baseline_wait = self._warmup_baseline_wait.get(v.vehicle_id, 0.0)
            baseline_stops = self._warmup_baseline_stops.get(v.vehicle_id, 0)
            clipped_waits.append(max(0.0, v.wait_time - baseline_wait))
            clipped_stops.append(max(0, v.stop_count - baseline_stops))

        avg_wait_time = (
            round(sum(clipped_waits) / len(clipped_waits), 2) if clipped_waits else 0.0
        )
        avg_stops_per_vehicle = (
            round(sum(clipped_stops) / len(clipped_stops), 2) if clipped_stops else 0.0
        )
        total_stops_exited = sum(clipped_stops)

        # Idle opportunity loss
        idle_loss = 0.0
        if self.total_ticks_post_warmup > 0:
            idle_loss = self.idle_loss_ticks / self.total_ticks_post_warmup

        # Extract active lane lengths for QSI calculation
        lane_lengths = {}
        for v in active_vehicles:
            if v.lane:
                lane_lengths[v.lane.lane_id] = v.lane.length

        throughput_val = calculate_throughput(post_warmup_exited)
        throughput_rate_val = calculate_throughput_rate(
            post_warmup_exited, current_time, warmup_time=self.warmup_time
        )

        # Time-averaged Speed Variance Index: SVI = (1/T) * sum(CV(t)) over
        # post-warmup ticks with >=2 active vehicles (see update() above).
        speed_variance_index = (
            round(sum(self.speed_cv_history) / len(self.speed_cv_history), 3)
            if self.speed_cv_history
            else 0.0
        )

        travel_time_reliability, travel_time_sample_size = (
            calculate_travel_time_reliability(post_warmup_exited)
        )

        base_metrics = {
            "averageWaitTime": avg_wait_time,
            "averageDelay": avg_delay,
            "medianDelay": med_delay,
            "minDelay": min_delay,
            "maxDelay": max_delay,
            "p95Delay": p95_delay,
            "delayStdDev": sd_delay,
            "throughput": throughput_val,
            "throughputRate": throughput_rate_val,
            "currentQueueLengths": curr_queues,
            "maxQueueLength": max_q,
            "averageQueueLength": avg_q,
            "activeAverageQueueLength": active_avg_q,
            "queueStdDev": sd_q,
            "totalStops": total_stops_exited,
            "averageStopsPerVehicle": avg_stops_per_vehicle,
            "speedVarianceIndex": speed_variance_index,
            "travelTimeReliability": travel_time_reliability,
            "travelTimeReliabilityLowSampleSize": travel_time_sample_size
            < MIN_RELIABLE_SAMPLE_SIZE,
            "idleOpportunityLoss": idle_loss,
            "directionalFairnessIndex": calculate_directional_fairness(
                post_warmup_exited
            ),
            "activeVehicleCount": len(active_vehicles),
            "totalVehiclesSpawned": total_spawned,
            "averageTravelSpeed": calculate_average_travel_speed(active_vehicles),
            "queueStabilityIndex": calculate_queue_stability_index(self.queue_history),
            "congestionRecoveryTime": round(self.congestion_recovery_time, 2),
            "spaceFootprintConsumed": calculate_space_footprint_consumed(self.config),
            "intersectionUtilization": round(
                (self.service_ticks / self.demand_ticks * 100)
                if self.demand_ticks > 0
                else 0.0,
                1,
            ),
            "criticalSaturationVolume": calculate_critical_saturation_volume(
                self.config, throughput_val, throughput_rate_val, total_spawned
            ),
        }
        base_metrics["masterEfficiencyScore"] = calculate_master_efficiency_score(
            base_metrics
        )
        return base_metrics
