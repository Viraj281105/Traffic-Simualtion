import math
from typing import Any, Dict, List

from src.vehicles.vehicle import Vehicle


def calculate_average_travel_speed(active_vehicles: List[Vehicle]) -> float:
    """Calculates average travel speed (ATS) of all active vehicles."""
    if not active_vehicles:
        return 0.0
    return float(sum(v.speed for v in active_vehicles) / len(active_vehicles))


def calculate_queue_stability_index(queue_history: List[Dict[str, int]]) -> float:
    """Calculates Queue Stability Index (QSI) over history.

    QSI = SD(queue length) / Mean(queue length)
    """
    if not queue_history:
        return 0.0

    total_queues = [sum(q.values()) for q in queue_history]
    n = len(total_queues)
    if n < 2:
        return 0.0

    mean_q = sum(total_queues) / n
    if mean_q == 0:
        return 0.0

    variance = sum((x - mean_q) ** 2 for x in total_queues) / (n - 1)
    sd = math.sqrt(variance)

    return float(round(sd / mean_q, 3))


def calculate_critical_saturation_volume(
    config: Dict[str, Any],
    throughput: int,
    throughput_rate: float,
    total_spawned: int,
) -> float:
    """Estimates critical saturation volume (vehicles/sec) per the metric contract.

    See docs/architecture/07-metric-contract.md section 4.2 ("Simplified
    practical approach"):

        CSV = arrival_rate_config * (throughput / total_spawned)

    unless the configured arrival rate already saturates the system
    (observed throughput rate below the configured rate), in which case CSV
    is reported as the observed throughput rate.

    ``throughput_rate`` is expected in vehicles/minute (as returned by
    calculate_throughput_rate) and is converted to vehicles/sec for
    comparison against the configured (vehicles/sec) arrival rate.
    """
    if total_spawned <= 0:
        return 0.0

    traffic_cfg = config.get("traffic", {})
    veh_gen_cfg = config.get("vehicleGeneration", {})
    arrival_rate_config = float(
        traffic_cfg.get("arrivalRate", veh_gen_cfg.get("arrivalRate", 0.5))
    )

    throughput_rate_per_sec = throughput_rate / 60.0

    if throughput_rate_per_sec < arrival_rate_config:
        # The configured arrival rate already saturates the system.
        return float(round(throughput_rate_per_sec, 3))

    csv = arrival_rate_config * (throughput / total_spawned)
    return float(round(csv, 3))


def calculate_space_footprint_consumed(config: Dict[str, Any]) -> float:
    """Calculates physical space footprint consumed by the intersection geometry.

    Roundabout: A = pi * outerRadius^2
    Signal: A = (2 * lanesPerApproach * laneWidth)^2 (conflict box area)
    """
    geom_cfg = config.get("geometry", {})
    roads_cfg = config.get("roads", {})
    ctrl_cfg = config.get("controller", {})

    intersection_type = geom_cfg.get("intersectionType", "fixed_time_signal")

    if intersection_type == "roundabout":
        outer_radius = ctrl_cfg.get("outerRadius", 20.0)
        return float(round(math.pi * (outer_radius**2), 2))
    else:
        lanes = roads_cfg.get("lanesPerApproach", 2)
        lane_width = roads_cfg.get("laneWidth", 3.5)
        if isinstance(lanes, dict):
            lane_count = max(lanes.values()) if lanes else 2
        else:
            lane_count = int(lanes)
        # Central square where the roads cross
        width = 2 * lane_count * lane_width
        return float(round(width * width, 2))
