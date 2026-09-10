from typing import Dict, List

from src.core.enums import Direction
from src.metrics.definitions.queue_length import get_current_queue_lengths
from src.vehicles.vehicle import Vehicle


def calculate_idle_loss_tick(
    active_vehicles: List[Vehicle],
    signals_state: Dict[Direction, str],
    wait_speed_threshold: float = 0.5,
) -> bool:
    """Checks if capacity is wasted in the current tick.

    Returns True if an approach is stopped on RED with waiting vehicles, while
    all approaches currently on GREEN have zero *queued* vehicles.

    Both sides of this check are evaluated via get_current_queue_lengths —
    the same Q_d(t) definition (speed < wait_speed_threshold) used by the
    queue_length metric — so a vehicle merely passing through a green
    approach (not queued) does not by itself prevent an idle-loss tick from
    being flagged, matching docs/architecture/07-metric-contract.md §4.1's
    Q_d(t)-based definition for both R(t) and G(t).
    """
    # Categorize approaches into green and red
    green_approaches = set()
    red_approaches = set()

    for d, color in signals_state.items():
        if color == "green":
            green_approaches.add(d.value.lower())
        else:
            red_approaches.add(d.value.lower())

    if not green_approaches or not red_approaches:
        return False

    queues = get_current_queue_lengths(active_vehicles, wait_speed_threshold)
    has_waiting_on_red = any(queues.get(d, 0) > 0 for d in red_approaches)
    green_all_empty = all(queues.get(d, 0) == 0 for d in green_approaches)

    # Idle loss condition: red has waiting vehicles, but green is completely empty
    return has_waiting_on_red and green_all_empty
