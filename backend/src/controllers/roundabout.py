import math
from typing import Any, Dict, List

from src.controllers.base import BaseController
from src.controllers.virtual_obstacle import VirtualObstacle
from src.core.enums import Direction, TurnIntent
from src.roads.network import RoadNetwork
from src.vehicles.vehicle import Vehicle


class RoundaboutController(BaseController):
    """Manages entry yielding logic and circulating traffic flow inside a roundabout intersection."""

    def __init__(self, config: Dict[str, Any], network: RoadNetwork) -> None:
        self.config: Dict[str, Any] = config
        self.network: RoadNetwork = network

        ctrl_cfg = config.get("controller", {})
        self.inner_radius: float = ctrl_cfg.get("innerRadius", 10.0)
        self.outer_radius: float = ctrl_cfg.get("outerRadius", 20.0)
        self.circulating_lanes: int = ctrl_cfg.get("circulatingLanes", 1)
        self.critical_gap: float = ctrl_cfg.get("criticalGap", 2.5)
        self.follow_up_time: float = ctrl_cfg.get("followUpTime", 1.5)
        self.entry_speed: float = ctrl_cfg.get("entrySpeed", 5.0)
        self.circulating_speed: float = ctrl_cfg.get("circulatingSpeed", 8.0)

        self.time_in_current_state: float = 0.0
        self.reset()

    def reset(self) -> None:
        self.time_in_current_state = 0.0
        # Clear all entry obstacles initially
        for d in Direction:
            try:
                approach = self.network.get_incoming_approach(d)
                for lane in approach.get_lanes():
                    lane.virtual_obstacle = None
            except KeyError:
                pass

    def update(self, delta_time: float, active_vehicles: List[Vehicle]) -> None:
        self.update_active_vehicles_ref(active_vehicles)
        self.time_in_current_state += delta_time

        # Identify all circulating vehicles (those on connection/circulating lanes)
        circulating_vehicles = [
            v
            for v in active_vehicles
            if v.lane is not None and v.lane.lane_id.startswith("conn")
        ]

        for d in Direction:
            try:
                approach = self.network.get_incoming_approach(d)
                total_in_lanes = len(approach.get_lanes())
                for lane in approach.get_lanes():
                    # Calculate if there is an oncoming circulating vehicle that blocks entry.
                    # We check circulating vehicles approaching this direction's entry node.
                    # The entry point of this lane is lane.end_coords.
                    entry_pt = lane.end_coords
                    theta_entry = math.atan2(entry_pt[1], entry_pt[0])

                    entering_lane_idx = int(lane.lane_id.split("_")[-1])
                    w_ring = self.outer_radius - self.inner_radius
                    lane_radius = self.inner_radius + (entering_lane_idx + 0.5) * (
                        w_ring / total_in_lanes
                    )

                    should_yield = False

                    # Safe look-ahead distance threshold
                    threshold = max(15.0, self.critical_gap * self.circulating_speed)

                    for cv in circulating_vehicles:
                        # Match circulating lane index and ignore downstream/exiting vehicles
                        if cv.lane is not None:
                            try:
                                cv_parts = cv.lane.lane_id.split("_")
                                if len(cv_parts) >= 4 and cv_parts[0] == "conn":
                                    cv_origin_dir_str = cv_parts[1]
                                    cv_lane_idx = int(cv_parts[2])
                                    cv_turn_str = cv_parts[3]

                                    # 1. Skip if the vehicle entered from the same approach (it is downstream)
                                    if cv_origin_dir_str == d.value:
                                        continue

                                    # 2. Skip if the vehicle is in a different circulating lane index
                                    if cv_lane_idx != entering_lane_idx:
                                        continue

                                    # 3. Skip if the vehicle is exiting at this approach
                                    dir_map = {
                                        "n": Direction.NORTH,
                                        "s": Direction.SOUTH,
                                        "e": Direction.EAST,
                                        "w": Direction.WEST,
                                    }
                                    turn_map = {
                                        "left": TurnIntent.LEFT,
                                        "straight": TurnIntent.STRAIGHT,
                                        "right": TurnIntent.RIGHT,
                                    }
                                    cv_origin = dir_map[cv_origin_dir_str]
                                    cv_turn = turn_map[cv_turn_str]
                                    cv_target = self.network._resolve_target_direction(
                                        cv_origin, cv_turn
                                    )
                                    if cv_target == d:
                                        continue
                            except (ValueError, IndexError):
                                pass

                        cv_x, cv_y = cv.coords
                        dist_to_entry_euclidean = (
                            (cv_x - entry_pt[0]) ** 2 + (cv_y - entry_pt[1]) ** 2
                        ) ** 0.5

                        if dist_to_entry_euclidean < threshold:
                            theta_cv = math.atan2(cv_y, cv_x)
                            # Angular distance from circulating vehicle to entry point (counter-clockwise)
                            angular_gap = (theta_entry - theta_cv) % (2 * math.pi)

                            # If angular_gap < pi, it is upstream / approaching the entry point
                            if angular_gap < math.pi:
                                dist_along_circle = lane_radius * angular_gap
                                if dist_along_circle < threshold:
                                    eff_speed = (
                                        max(cv.speed, 2.0)
                                        if hasattr(cv, "speed") and cv.speed > 0
                                        else self.circulating_speed
                                    )
                                    time_gap = dist_along_circle / eff_speed
                                    if time_gap < self.critical_gap:
                                        should_yield = True
                                        break

                    if should_yield:
                        lane.virtual_obstacle = VirtualObstacle(position=lane.length)
                    else:
                        lane.virtual_obstacle = None
            except KeyError:
                pass

    def get_state(self) -> Dict[str, Any]:
        # Count circulating vehicles
        circulating_count = 0
        yielding_count = 0

        # Count yielding vehicles (near stop line on incoming approaches with low speed)
        for d in Direction:
            try:
                approach = self.network.get_incoming_approach(d)
                for lane in approach.get_lanes():
                    for v in lane.get_vehicles():
                        if v.position >= lane.length - 5.0 and v.speed < 0.5:
                            yielding_count += 1
            except KeyError:
                pass

        active_vehs = getattr(self, "_active_vehicles", [])
        circulating_count = sum(
            1
            for v in active_vehs
            if v.lane is not None and v.lane.lane_id.startswith("conn")
        )

        return {
            "type": "roundabout",
            "timeInCurrentState": round(self.time_in_current_state, 2),
            "innerRadius": self.inner_radius,
            "outerRadius": self.outer_radius,
            "circulatingCount": circulating_count,
            "yieldingCount": yielding_count,
            "gapAcceptance": self.critical_gap,
        }

    def update_active_vehicles_ref(self, active_vehicles: List[Vehicle]) -> None:
        self._active_vehicles = active_vehicles
