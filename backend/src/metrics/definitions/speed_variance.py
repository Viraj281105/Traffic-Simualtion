import math
from typing import List

from src.vehicles.vehicle import Vehicle


def calculate_speed_variance_index(active_vehicles: List[Vehicle]) -> float:
    """Computes the Coefficient of Variation (CV) of speed for one tick's
    active vehicles (see docs/architecture/07-metric-contract.md §3.2).

    This is CV(t) for a single tick, not the time-averaged SVI — callers
    that need the aggregate (MetricCollector) average this across ticks
    themselves, skipping ticks with fewer than 2 active vehicles per the
    contract's edge cases.

    - No data (0 or 1 active vehicle): 0.0. There is no measured
      variability, so — consistent with this codebase's "no data reports
      the metric's best-case value" convention (see e.g.
      calculate_directional_fairness) — 0.0 is reported, not the
      contract's documented "typical worst" end of the 0-2 scale.
    - All vehicles stopped (mean speed == 0): CV(t) = 0.0 per the contract
      ("all vehicles have the same speed: zero").
    - All vehicles at the same nonzero speed (zero variance): CV(t) = 0.0
      — the most uniform, i.e. best, possible flow.
    """
    speeds = [v.speed for v in active_vehicles]
    n = len(speeds)
    if n <= 1:
        return 0.0

    mean_speed = sum(speeds) / n
    if mean_speed <= 0:
        return 0.0

    # Population variance (divide by M(t), not M(t)-1) per the contract's
    # sigma_v(t) definition — this is a full-population per-tick snapshot,
    # not a sample drawn from a larger population.
    variance = sum((s - mean_speed) ** 2 for s in speeds) / n
    if variance <= 0:
        return 0.0

    std_dev = math.sqrt(variance)
    return std_dev / mean_speed
