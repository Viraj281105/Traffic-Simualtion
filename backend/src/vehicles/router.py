"""Layered leader-detection and collision avoidance for vehicles.

Safety layers (checked in order):
    1. **Same-lane following** — vehicles ahead on the current / upcoming route
       lanes (including shared connection lanes).
    2. **Virtual obstacles** — signal stop-line barriers placed by the traffic
       controller.
    3. **Conflict zone reservation** — queries the :class:`ConflictManager` for
       blocked intersection zones and inserts virtual obstacles before them.
    4. **Emergency proximity check** — bounding-box proximity scan; if any
       vehicle is dangerously close, returns an emergency braking obstacle.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from src.controllers.virtual_obstacle import VirtualObstacle
from src.core.enums import TurnIntent
from src.roads.network import RoadNetwork
from src.vehicles.vehicle import Vehicle

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_EMERGENCY_DIST: float = 2.5  # meters — triggers emergency braking
_SENSOR_RANGE: float = 30.0  # meters — max 360° sensor reach
_LOOK_AHEAD_LANES: int = 3  # how many route lanes to scan forward


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_blocked_before_lane(vehicle: Vehicle, target_lane: Any) -> bool:
    """Check if there is a vehicle or virtual obstacle on the route before target_lane."""
    if vehicle.lane is None:
        return True
    try:
        curr_idx = vehicle.route.index(vehicle.lane)
        target_idx = vehicle.route.index(target_lane)
    except ValueError:
        return True

    accumulated_dist = -vehicle.position
    for i in range(curr_idx, target_idx):
        lane = vehicle.route[i]
        # Check for virtual obstacle on this intermediate lane
        if getattr(lane, "virtual_obstacle", None) is not None:
            return True
        # Check for any vehicles ahead of us on this intermediate lane
        for v in lane.get_vehicles():
            if v is vehicle:
                continue
            v_dist = accumulated_dist + v.position
            if v_dist > 0:
                # There is a vehicle ahead of us before the target lane
                return True
        accumulated_dist += lane.length
    return False


def find_leader(
    vehicle: Vehicle,
    network: Optional[RoadNetwork] = None,
    active_vehicles: Optional[List[Vehicle]] = None,
    conflict_manager: Any = None,
    current_time: float = 0.0,
) -> Tuple[Optional[Any], float]:
    """Find the effective leader (or virtual obstacle) for *vehicle*.

    Returns ``(leader_object, gap)`` where *gap* is bumper-to-bumper distance.
    If no obstacle is found the gap is ``float('inf')``.
    """
    if vehicle.lane is None or not vehicle.route:
        return None, float("inf")

    try:
        curr_idx = vehicle.route.index(vehicle.lane)
    except ValueError:
        return None, float("inf")

    best_leader: Optional[Any] = None
    best_gap: float = float("inf")

    # ── Layer 1: Same-lane following ────────────────────────────────────
    accumulated_dist = -vehicle.position

    end_idx = min(curr_idx + _LOOK_AHEAD_LANES, len(vehicle.route))
    for i in range(curr_idx, end_idx):
        lane = vehicle.route[i]

        # Special logic for roundabouts: connection lanes circle the same roundabout, so
        # vehicles can be on different connection lane objects but physically follow each other if they are in the same lane index.
        if getattr(network, "is_roundabout", False) and lane.lane_id.startswith("conn"):
            inner_r = getattr(network, "inner_radius", 10.0)
            outer_r = getattr(network, "outer_radius", 20.0)
            avg_radius = (inner_r + outer_r) / 2.0

            try:
                my_lane_idx = int(lane.lane_id.split("_")[2])
            except (ValueError, IndexError):
                my_lane_idx = 0

            if lane is vehicle.lane:
                my_x, my_y = vehicle.coords
                theta_self = math.atan2(my_y, my_x)
                dist_to_lane_start = 0.0
            else:
                start_x, start_y = lane.start_coords
                theta_self = math.atan2(start_y, start_x)
                dist_to_lane_start = accumulated_dist

            for v in active_vehicles or []:
                if (
                    v is vehicle
                    or v.lane is None
                    or not v.lane.lane_id.startswith("conn")
                ):
                    continue

                try:
                    v_lane_idx = int(v.lane.lane_id.split("_")[2])
                    if v_lane_idx != my_lane_idx:
                        continue
                except (ValueError, IndexError):
                    pass

                v_x, v_y = v.coords
                theta_v = math.atan2(v_y, v_x)

                # Counter-clockwise angular distance from theta_self to theta_v
                diff = (theta_v - theta_self) % (2 * math.pi)

                # Only consider vehicles that are actually ahead of us in forward circular flow (within 180 degrees)
                if 0.0 < diff <= math.pi:
                    arc_dist = avg_radius * diff
                    v_dist = dist_to_lane_start + arc_dist

                    if v_dist > 0:
                        gap = v_dist - (vehicle.length / 2.0 + v.length / 2.0)
                        gap = max(0.0, gap)
                        if gap < best_gap:
                            best_gap = gap
                            best_leader = v
        else:
            # Scan vehicles on this lane
            for v in lane.get_vehicles():
                if v is vehicle:
                    continue
                v_dist = accumulated_dist + v.position
                if v_dist > 0:
                    gap = v_dist - (vehicle.length / 2.0 + v.length / 2.0)
                    gap = max(0.0, gap)
                    if gap < best_gap:
                        best_gap = gap
                        best_leader = v

        # ── Layer 2: Virtual obstacles (signal stop-lines) ─────────────
        virtual_obs = getattr(lane, "virtual_obstacle", None)
        if virtual_obs is not None:
            # Check if this is a yellow clearance obstacle
            is_yellow = getattr(virtual_obs, "is_yellow", False)
            if is_yellow and i == curr_idx:
                # Dilemma zone calculation: if vehicle cannot safely stop comfortably before line, permit clearance
                stopping_dist = (vehicle.speed**2) / (
                    2.0 * max(getattr(vehicle, "comfort_deceleration", 3.0), 1.0)
                )
                dist_to_line = max(0.0, virtual_obs.position - vehicle.position)
                if dist_to_line <= stopping_dist + vehicle.length:
                    virtual_obs = None

            if virtual_obs is not None:
                obs_dist = accumulated_dist + virtual_obs.position
                if obs_dist > 0:
                    gap = obs_dist - (vehicle.length / 2.0 + virtual_obs.length / 2.0)
                    gap = max(0.0, gap)
                    if gap < best_gap:
                        best_gap = gap
                        best_leader = virtual_obs

        # If we already found something on this lane, no need to look further
        if best_leader is not None and i == curr_idx:
            # Only short-circuit on the current lane — for future lanes we
            # still want to check conflict zones
            pass

        accumulated_dist += lane.length

    # ── Layer 3: Conflict zone reservation check ───────────────────────
    if conflict_manager is not None:
        # Build info list for all vehicles currently on connection lanes
        conn_vehicles_info: List[Dict[str, Any]] = []
        if active_vehicles:
            for av in active_vehicles:
                if av is vehicle:
                    continue
                if av.lane is not None and av.lane.lane_id.startswith("conn"):
                    conn_vehicles_info.append(
                        {
                            "vehicle_id": av.vehicle_id,
                            "turn_intent": getattr(
                                av, "turn_intent", TurnIntent.STRAIGHT
                            ),
                            "connection_lane_id": av.lane.lane_id,
                            "position_on_lane": av.position,
                        }
                    )

        # Check each connection lane in the vehicle's upcoming route
        acc_dist_for_conflict = -vehicle.position
        for i in range(curr_idx, end_idx):
            lane = vehicle.route[i]

            if lane.lane_id.startswith("conn"):
                # Check if we are blocked before this connection lane
                if is_blocked_before_lane(vehicle, lane):
                    acc_dist_for_conflict += lane.length
                    continue

                # Position on this connection lane
                if lane is vehicle.lane:
                    pos_on_conn = vehicle.position
                else:
                    pos_on_conn = 0.0  # haven't entered yet

                turn = (
                    getattr(vehicle, "turn_intent", TurnIntent.STRAIGHT)
                    or TurnIntent.STRAIGHT
                )

                block_dist = conflict_manager.get_conflict_distance(
                    vehicle_id=vehicle.vehicle_id,
                    vehicle_turn_intent=turn,
                    connection_lane_id=lane.lane_id,
                    vehicle_position_on_lane=pos_on_conn,
                    current_time=current_time,
                    all_vehicles_info=conn_vehicles_info,
                )

                if block_dist < float("inf"):
                    # Convert block distance (relative to connection lane start)
                    # to distance from the vehicle's current position
                    if lane is vehicle.lane:
                        total_block_dist = block_dist
                    else:
                        total_block_dist = acc_dist_for_conflict + block_dist

                    gap = max(0.0, total_block_dist - vehicle.length / 2.0)
                    if gap < best_gap:
                        best_gap = gap
                        best_leader = VirtualObstacle(
                            position=0.0, speed=0.0, length=0.0
                        )

                # Update reservation clear time if vehicle has passed through
                if lane is vehicle.lane and pos_on_conn > 0:
                    conflict_manager.update_reservation_clear_time(
                        vehicle.vehicle_id, lane.lane_id, current_time
                    )

            acc_dist_for_conflict += lane.length

    # ── Layer 4: Emergency proximity check ─────────────────────────────
    if active_vehicles:
        my_x, my_y = vehicle.coords
        heading_rad = math.radians(vehicle.heading)
        fwd_x = math.sin(heading_rad)
        fwd_y = math.cos(heading_rad)

        for other in active_vehicles:
            if other is vehicle or other.lane is None:
                continue

            # Skip parallel lanes of the same street (non-connection lanes starting with same direction prefix)
            id_a = vehicle.lane.lane_id.lower()
            id_b = other.lane.lane_id.lower()
            if getattr(network, "is_roundabout", False):
                # In a roundabout, skip straight-line emergency check if either vehicle is on a connection lane
                # because they are already tracked by the circular/arc-length logic in Layer 1.
                if id_a.startswith("conn") or id_b.startswith("conn"):
                    continue
            else:
                if not id_a.startswith("conn") and not id_b.startswith("conn"):
                    if id_a[0] in ("n", "s", "e", "w") and id_a[:2] == id_b[:2]:
                        continue

            ox, oy = other.coords
            dx = ox - my_x
            dy = oy - my_y

            # Forward distance along our heading
            fwd_dist = dx * fwd_x + dy * fwd_y
            if fwd_dist <= 0:
                # Other vehicle is behind or beside us — not a forward threat
                continue

            # Lateral distance perpendicular to our heading
            lat_dist = abs(-dx * fwd_y + dy * fwd_x)
            corridor_width = (vehicle.width + other.width) / 2.0 + 0.3  # ~2.2m

            if lat_dist > corridor_width:
                # Outside our lane envelope (e.g. adjacent lane, waiting at perpendicular red light)
                continue

            # Emergency braking if directly ahead in our corridor
            min_safe_dist = _EMERGENCY_DIST + (vehicle.length + other.length) / 2.0
            if fwd_dist < min_safe_dist:
                gap = max(0.0, fwd_dist - (vehicle.length + other.length) / 2.0)
                if gap < best_gap:
                    best_gap = gap
                    best_leader = VirtualObstacle(
                        position=0.0, speed=other.speed, length=other.length
                    )

    return best_leader, best_gap
