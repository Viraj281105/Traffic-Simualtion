import math
from typing import List, Optional, Tuple

from src.vehicles.vehicle import Vehicle

# Below this many exited vehicles, the 95th-percentile/median calculation
# is considered statistically unreliable (see metric contract §3.3).
MIN_RELIABLE_SAMPLE_SIZE = 20


def _calculate_median(lst: List[float]) -> float:
    if not lst:
        return 0.0
    s = sorted(lst)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    else:
        return (s[n // 2 - 1] + s[n // 2]) / 2.0


def _calculate_percentile(lst: List[float], p: float) -> float:
    if not lst:
        return 0.0
    s = sorted(lst)
    k = (len(s) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return s[int(k)]
    d0 = s[int(f)] * (c - k)
    d1 = s[int(c)] * (k - f)
    return d0 + d1


def calculate_travel_time_reliability(
    exited_vehicles: List[Vehicle],
) -> Tuple[Optional[float], int]:
    """Computes the Planning Time Index (PTI) for exited vehicles in pure Python.

    PTI = 95th percentile travel time / median (50th percentile) travel time.

    Returns ``(pti, sample_size)``:
    - No exited vehicles (or none with a recorded exit time yet): ``(1.0, 0)``
      — "no data yet" reports the metric's best-case value, consistent with
      this codebase's convention for other metrics.
    - Real travel-time data exists but the median is exactly 0: per the
      metric contract ("a vehicle cannot have zero travel time" is a data
      error), this returns ``(None, sample_size)`` instead of a fabricated
      1.0, so callers can surface it as null rather than a plausible-looking
      number.
    - ``sample_size`` is always the count of vehicles the PTI was computed
      from, so callers can flag "low sample size" (contract: fewer than
      ``MIN_RELIABLE_SAMPLE_SIZE`` exited vehicles) without altering the
      reported PTI value itself.
    """
    if not exited_vehicles:
        return 1.0, 0

    travel_times = []
    for v in exited_vehicles:
        spawn = getattr(v, "spawn_time", 0.0)
        exit_t = getattr(v, "exit_time", None)
        if exit_t is not None:
            travel_times.append(max(0.0, exit_t - spawn))

    if not travel_times:
        return 1.0, 0

    sample_size = len(travel_times)
    median_t = _calculate_median(travel_times)
    if median_t <= 0:
        return None, sample_size

    p95_t = _calculate_percentile(travel_times, 95.0)
    return p95_t / median_t, sample_size
