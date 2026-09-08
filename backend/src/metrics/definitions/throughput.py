from typing import List

from src.vehicles.vehicle import Vehicle


def calculate_throughput(exited_vehicles: List[Vehicle]) -> int:
    """Returns the total number of exited vehicles."""
    return len(exited_vehicles)


def calculate_throughput_rate(
    exited_vehicles: List[Vehicle],
    current_time: float,
    window_size: float = 60.0,
    warmup_time: float = 0.0,
) -> float:
    """Computes the rolling throughput rate in vehicles per minute over a sliding window, excluding warmup."""
    effective_time = max(0.0, current_time - warmup_time)
    if not exited_vehicles or effective_time <= 0:
        return 0.0

    # Collect exit times of vehicles that exited within the post-warmup sliding window
    start_window = max(warmup_time, current_time - window_size)
    window_count = 0

    for v in exited_vehicles:
        exit_time = getattr(v, "exit_time", None)
        if exit_time is not None and start_window <= exit_time <= current_time:
            window_count += 1

    actual_window = min(effective_time, window_size)
    if actual_window <= 0:
        return 0.0
    return (window_count / actual_window) * 60.0
