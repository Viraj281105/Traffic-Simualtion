import math
from typing import Any, Dict, List, Set

from src.controllers.base import BaseController
from src.controllers.virtual_obstacle import VirtualObstacle
from src.core.enums import Direction, TurnIntent
from src.roads.network import RoadNetwork
from src.vehicles.vehicle import Vehicle

# Distance from the entry point (lane end) within which a vehicle is
# considered "at the roundabout entry" for both the entrySpeed cap and
# follow-up-time bookkeeping below.
_ENTRY_ZONE: float = 5.0


class RoundaboutController(BaseController):
    """Manages entry yielding logic and circulating traffic flow inside a roundabout intersection."""

    def __init__(self, config: Dict[str, Any], network: RoadNetwork) -> None:
        self.config: Dict[str, Any] = config
        self.network: RoadNetwork = network

        ctrl_cfg = config.get("controller", {})
        self.inner_radius: float = ctrl_cfg.get("innerRadius", 10.0)
        self.outer_radius: float = ctrl_cfg.get("outerRadius", 20.0)
        self.circulating_lanes: int = ctrl_cfg.get("circulatingLanes", 1)
        self.critical_gap: float = ctrl_cfg.get("criticalGap", 4.0)
        self.follow_up_time: float = ctrl_cfg.get("followUpTime", 2.5)
        self.entry_speed: float = ctrl_cfg.get("entrySpeed", 5.0)
        self.circulating_speed: float = ctrl_cfg.get("circulatingSpeed", 8.0)

        self.time_in_current_state: float = 0.0
        # Per-lane timestamp (in self.time_in_current_state units) of the
        # most recent tick a vehicle was observed completing its entry from
        # that lane — used to enforce follow_up_time spacing between
        # consecutive entries (see update()).
        self._last_entry_time: Dict[str, float] = {}
        # Per-lane set of vehicle_ids that were within _ENTRY_ZONE as of
        # the previous tick, so a "completed entry" can be detected as a
        # vehicle that was in the zone and has now left the lane entirely
        # (rather than merely still sitting in the zone).
        self._prev_zone_occupants: Dict[str, Set[str]] = {}
        # Per-vehicle-id desired_speed as it was before the entrySpeed cap
        # was first applied, so it can be restored once the vehicle starts
        # circulating (see update()).
        self._pre_entry_desired_speed: Dict[str, float] = {}
        self.reset()

    def reset(self) -> None:
        self.time_in_current_state = 0.0
        self._last_entry_time = {}
        self._prev_zone_occupants = {}
        self._pre_entry_desired_speed = {}
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

        # entrySpeed: "Maximum speed at roundabout entry" — cap each
        # vehicle's desired speed while it is within _ENTRY_ZONE of an
        # incoming lane's entry point, so the IDM free-road term brings it
        # down to entry_speed before it circulates. Restore the vehicle's
        # original desired speed once it is actually circulating, so this
        # only governs the entry itself, not the rest of its journey.
        for v in active_vehicles:
            if v.lane is None:
                continue
            lane_id = v.lane.lane_id.lower()
            if lane_id.startswith("conn"):
                original_speed = self._pre_entry_desired_speed.pop(v.vehicle_id, None)
                if original_speed is not None:
                    v.desired_speed = original_speed
            elif "_in_" in lane_id and (v.lane.length - v.position) <= _ENTRY_ZONE:
                original_speed = self._pre_entry_desired_speed.get(v.vehicle_id)
                if original_speed is None:
                    original_speed = v.desired_speed
                    self._pre_entry_desired_speed[v.vehicle_id] = original_speed
                v.desired_speed = min(original_speed, self.entry_speed)

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

                    # followUpTime: "Time between consecutive entering
                    # vehicles" — even once a circulating gap is accepted,
                    # hold the lane for follow_up_time after the previous
                    # entry from it, modeling the minimum headway queued
                    # vehicles need between each other (HCM roundabout
                    # capacity: critical gap + follow-up time).
                    last_entry = self._last_entry_time.get(lane.lane_id)
                    if last_entry is not None and (
                        self.time_in_current_state - last_entry
                        < self.follow_up_time
                    ):
                        should_yield = True

                    if should_yield:
                        lane.virtual_obstacle = VirtualObstacle(position=lane.length)
                    else:
                        lane.virtual_obstacle = None

                    # Detect a completed entry: a vehicle that was within
                    # _ENTRY_ZONE last tick and has now left this lane
                    # entirely (crossed into the roundabout). Using actual
                    # departure from the lane — rather than mere continued
                    # presence in the zone — avoids a vehicle re-arming its
                    # own follow-up timer every tick it is held waiting
                    # right at the entry, which would otherwise deadlock it.
                    current_lane_vehicle_ids = {
                        v.vehicle_id for v in lane.get_vehicles()
                    }
                    prev_zone_occupants = self._prev_zone_occupants.get(
                        lane.lane_id, set()
                    )
                    if prev_zone_occupants - current_lane_vehicle_ids:
                        self._last_entry_time[lane.lane_id] = (
                            self.time_in_current_state
                        )
                    self._prev_zone_occupants[lane.lane_id] = {
                        v.vehicle_id
                        for v in lane.get_vehicles()
                        if (lane.length - v.position) <= _ENTRY_ZONE
                    }
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
