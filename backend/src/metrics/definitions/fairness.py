from typing import List

from src.vehicles.vehicle import Vehicle


def calculate_directional_fairness(exited_vehicles: List[Vehicle]) -> float:
    """Computes Jain's Fairness Index across wait times of the 4 approaches.

    Returns 1.0 if all wait times are zero.
    """
    if not exited_vehicles:
        return 1.0

    # Group wait times by direction
    from typing import Dict

    waits: Dict[str, List[float]] = {"north": [], "south": [], "east": [], "west": []}
    # Lane IDs use single-letter direction prefixes (e.g. "n_in_0"); map them to
    # the full direction names used as keys above (same convention as
    # queue_length.py / idle_loss.py).
    mapping = {"n": "north", "s": "south", "e": "east", "w": "west"}

    for v in exited_vehicles:
        # Get start direction from route
        if v.route:
            lane_id = v.route[0].lane_id.lower()
            dir_char = lane_id.split("_")[0]
            direction = mapping.get(dir_char)
            if direction in waits:
                waits[direction].append(v.wait_time)

    # Average wait time per approach
    x = []
    for d in ["north", "south", "east", "west"]:
        if waits[d]:
            x.append(sum(waits[d]) / len(waits[d]))
        else:
            x.append(0.0)

    sum_x = sum(x)
    if sum_x <= 0:
        return 1.0

    sum_sq_x = sum(val**2 for val in x)
    n = len(x)
    return float((sum_x**2) / (n * sum_sq_x))
