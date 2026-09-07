import math
from typing import Any, Dict, List

from src.core.enums import Direction
from src.metrics.definitions.derived_metrics import (
    calculate_average_travel_speed,
    calculate_queue_stability_index,
    calculate_space_footprint_consumed,
)
from src.metrics.definitions.fairness import calculate_directional_fairness
from src.metrics.definitions.idle_loss import calculate_idle_loss_tick
from src.metrics.definitions.queue_length import get_current_queue_lengths
from src.metrics.definitions.speed_variance import calculate_speed_variance_index
from src.metrics.definitions.stop_count import (
    calculate_average_stops,
    update_vehicle_stops,
)
from src.metrics.definitions.throughput import (
    calculate_throughput,
    calculate_throughput_rate,
)
from src.metrics.definitions.travel_time import calculate_travel_time_reliability
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
        self.total_stops_in_warmup: int = 0
        self.idle_loss_ticks: int = 0
        self.total_ticks_post_warmup: int = 0
        self.congestion_recovery_time: float = 0.0
        self.demand_ticks: int = 0
        self.service_ticks: int = 0

        # Maintain list of queue lengths over time to compute time-average and max
        self.queue_history: List[Dict[str, int]] = []

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
            # Track stops during warmup to exclude them from post-warmup metrics
            self.total_stops_in_warmup = sum(v.stop_count for v in exited_vehicles)
            return

        # Increment post-warmup simulation ticks count
        self.total_ticks_post_warmup += 1

        if active_vehicles:
            self.demand_ticks += 1
            avg_speed = sum(v.speed for v in active_vehicles) / len(active_vehicles)
            if avg_speed > self.wait_speed_threshold:
                self.service_ticks += 1

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
            if (
                v.exit_time is not None
                and v.exit_time >= self.warmup_time
            )
            or (
                v.exit_time is None
                and v.spawn_time >= self.warmup_time
            )
        ]

        # Calculate current queue lengths
        curr_queues = get_current_queue_lengths(
            active_vehicles, self.wait_speed_threshold
        )

        # Compute max, time-averaged, active average queue length, and queue std dev
        if self.queue_history:
            all_queues_sums = [sum(q.values()) for q in self.queue_history]
            max_q = max(all_queues_sums)
            avg_q = round(sum(all_queues_sums) / len(self.queue_history), 2)
            non_zero_queues = [q for q in all_queues_sums if q > 0]
            active_avg_q = (
                round(sum(non_zero_queues) / len(non_zero_queues), 2)
                if non_zero_queues
                else 0.0
            )
            if len(all_queues_sums) > 1:
                var_q = sum((x - avg_q) ** 2 for x in all_queues_sums) / (
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
                actual_travel_time = exit_t - spawn_t
                if getattr(v, "route", None):
                    route_len = sum(
                        lane.length for lane in v.route if hasattr(lane, "length")
                    )
                    free_flow_time = route_len / max(
                        getattr(v, "desired_speed", 15.0), 1.0
                    )
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

        # Compute total stops post-warmup (excluding stops incurred during warmup)
        total_stops_exited = max(
            0,
            sum(v.stop_count for v in post_warmup_exited) - self.total_stops_in_warmup,
        )

        # Idle opportunity loss
        idle_loss = 0.0
        if self.total_ticks_post_warmup > 0:
            idle_loss = self.idle_loss_ticks / self.total_ticks_post_warmup

        # Extract active lane lengths for QSI calculation
        lane_lengths = {}
        for v in active_vehicles:
            if v.lane:
                lane_lengths[v.lane.lane_id] = v.lane.length

        base_metrics = {
            "averageWaitTime": calculate_average_wait_time(post_warmup_exited),
            "averageDelay": avg_delay,
            "medianDelay": med_delay,
            "minDelay": min_delay,
            "maxDelay": max_delay,
            "p95Delay": p95_delay,
            "delayStdDev": sd_delay,
            "throughput": calculate_throughput(post_warmup_exited),
            "throughputRate": calculate_throughput_rate(
                post_warmup_exited, current_time, warmup_time=self.warmup_time
            ),
            "currentQueueLengths": curr_queues,
            "maxQueueLength": max_q,
            "averageQueueLength": avg_q,
            "activeAverageQueueLength": active_avg_q,
            "queueStdDev": sd_q,
            "totalStops": total_stops_exited,
            "averageStopsPerVehicle": calculate_average_stops(post_warmup_exited),
            "speedVarianceIndex": calculate_speed_variance_index(active_vehicles),
            "travelTimeReliability": calculate_travel_time_reliability(
                post_warmup_exited
            ),
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
            "criticalSaturationVolume": 1800.0,
        }
        base_metrics["masterEfficiencyScore"] = calculate_master_efficiency_score(
            base_metrics
        )
        return base_metrics
