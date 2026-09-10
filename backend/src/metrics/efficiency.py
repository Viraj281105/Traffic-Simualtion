from typing import Any, Dict


def calculate_master_efficiency_score(metrics: Dict[str, Any]) -> float:
    """Calculates an overall winner efficiency score (0.0 to 100.0) from operational metrics.

    Formula weights:
    - Throughput Rate (higher is better): weight = 30.0
    - Average Wait Time (lower is better): weight = -25.0
    - Average Stops per vehicle (lower is better): weight = -15.0
    - Directional Fairness Index (higher is better): weight = 20.0
    - Idle Capacity Loss (lower is better): weight = -10.0
    """
    throughput_rate = float(metrics.get("throughputRate", 0.0))
    avg_wait = float(metrics.get("averageWaitTime", 0.0))
    avg_stops = float(metrics.get("averageStopsPerVehicle", 0.0))
    dfi = float(metrics.get("directionalFairnessIndex", 1.0))
    idle_loss = float(metrics.get("idleOpportunityLoss", 0.0))

    # Normalization mappings to prevent runaway bounds
    # throughputRate is always reported in vehicles/minute (see
    # docs/architecture/07-metric-contract.md section 2.2), so it is always
    # converted to vehicles/sec before normalizing against a high limit of
    # 2.0 vehicles/sec (120 veh/min).
    tp_per_sec = throughput_rate / 60.0
    tp_norm = min(1.0, tp_per_sec / 2.0)

    # Average wait time: normalized (1.0 at 0s, 0.0 at 60s or more wait)
    wait_norm = max(0.0, 1.0 - (avg_wait / 60.0))

    # Stops per vehicle: normalized (1.0 at 0 stops, 0.0 at 5 stops or more)
    stops_norm = max(0.0, 1.0 - (avg_stops / 5.0))

    # Fairness: directly 0.0 to 1.0
    fairness_norm = max(0.0, min(1.0, dfi))

    # Idle loss: normalized (1.0 at 0% idle loss, 0.0 at 100% idle loss)
    idle_norm = max(0.0, 1.0 - idle_loss)

    # Calculate weighted score (maximum possible sum of weights is 100.0)
    score = (
        (tp_norm * 30.0)
        + (wait_norm * 25.0)
        + (stops_norm * 15.0)
        + (fairness_norm * 20.0)
        + (idle_norm * 10.0)
    )

    return round(score, 1)
