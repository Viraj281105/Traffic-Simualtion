"""Vehicle pool — manages all active and exited vehicles.

Integrates with the :class:`ConflictManager` by passing it through to
:func:`find_leader`, and runs a post-update collision audit to catch (and
log) any remaining overlaps as a safety net.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Tuple

from src.core.enums import Direction, TurnIntent, VehicleState
from src.vehicles.router import find_leader
from src.vehicles.vehicle import Vehicle

logger = logging.getLogger(__name__)

# Minimum centre-to-centre distance before we flag a collision.
_COLLISION_THRESHOLD: float = 0.5  # meters


def _check_sat_overlap(
    poly_a: List[Tuple[float, float]], poly_b: List[Tuple[float, float]]
) -> bool:
    """Check if two convex polygons (oriented bounding boxes) overlap using the Separating Axis Theorem."""
    for poly in (poly_a, poly_b):
        for i in range(len(poly)):
            p1 = poly[i]
            p2 = poly[(i + 1) % len(poly)]
            edge_x = p2[0] - p1[0]
            edge_y = p2[1] - p1[1]
            axis_x = -edge_y
            axis_y = edge_x
            axis_len = math.hypot(axis_x, axis_y)
            if axis_len < 1e-6:
                continue
            axis_x /= axis_len
            axis_y /= axis_len

            min_a = max_a = poly_a[0][0] * axis_x + poly_a[0][1] * axis_y
            for p in poly_a[1:]:
                proj = p[0] * axis_x + p[1] * axis_y
                if proj < min_a:
                    min_a = proj
                if proj > max_a:
                    max_a = proj

            min_b = max_b = poly_b[0][0] * axis_x + poly_b[0][1] * axis_y
            for p in poly_b[1:]:
                proj = p[0] * axis_x + p[1] * axis_y
                if proj < min_b:
                    min_b = proj
                if proj > max_b:
                    max_b = proj

            if max_a < min_b or max_b < min_a:
                return False
    return True


class VehiclePool:
    """Manages active and exited vehicles, coordinating their movement and lifecycle."""

    def __init__(self) -> None:
        self.active_vehicles: List[Vehicle] = []
        self.exited_vehicles: List[Vehicle] = []
        self._collision_count: int = 0
        self._last_lane_change: Dict[str, float] = {}

    def add_vehicle(self, vehicle: Vehicle) -> None:
        if vehicle not in self.active_vehicles:
            self.active_vehicles.append(vehicle)

    def get_active_vehicles(self) -> List[Vehicle]:
        return self.active_vehicles

    def get_exited_vehicles(self) -> List[Vehicle]:
        return self.exited_vehicles

    @property
    def collision_count(self) -> int:
        return self._collision_count

    def update(self, dt: float, engine: Any) -> None:
        """Tick all active vehicles, find leaders, update states, and cleanup exited vehicles."""
        # Get IDM physics from engine or configuration
        idm = getattr(engine, "idm", None)
        config = getattr(engine, "config", {})
        if idm is None:
            from src.vehicles.idm import IntelligentDriverModel

            veh_gen = config.get("vehicleGeneration", {})
            idm = IntelligentDriverModel(
                max_acceleration=veh_gen.get("maxAcceleration", 2.0),
                comfort_deceleration=veh_gen.get("comfortDeceleration", 3.0),
                desired_time_headway=veh_gen.get("desiredTimeHeadway", 1.5),
                minimum_gap=veh_gen.get("minimumGap", 2.0),
                idm_delta=veh_gen.get("idmDelta", 4.0),
            )

        # ConflictManager pre-computes conflict/crossing points from straight
        # chords between each connection lane's start/end coordinates (see
        # ConflictManager.compute_conflict_points). That approximation holds
        # for fixed-time-signal connection lanes (short straight or gently
        # curved turn paths near the intersection box), so it is enabled
        # there — it is what makes permissive lefts (e.g. an "ns_green"
        # phase where NORTH/SOUTH share a green and left-turners cross
        # opposing straight traffic) safe once phaseSequence-driven paired
        # phases are used (see FixedTimeSignalController).
        #
        # For roundabouts, connection lanes are long curved circulating arcs
        # (see RoadNetwork._get_or_create_connection_lane) that can span most
        # of the circle; a straight chord between their endpoints cuts
        # across the roundabout and would produce geometrically incorrect
        # conflict points (spurious crossings with lanes that never actually
        # meet, and missed real crossings). Rather than force an
        # incompatible model onto curved geometry, multi-lane roundabout
        # cross-conflicts (vehicles in different circulating lane indices,
        # e.g. weaving between inner/outer rings near entries and exits) are
        # instead caught by the emergency-proximity check in
        # router.find_leader (Layer 4), which works on live Euclidean
        # positions and needs no lane-geometry assumptions.
        geom_type = config.get("geometry", {}).get(
            "intersectionType", "fixed_time_signal"
        )
        if geom_type == "roundabout":
            conflict_manager = None
        else:
            conflict_manager = getattr(engine, "conflict_manager", None)

        current_time = 0.0
        clock = getattr(engine, "clock", None)
        if clock is not None:
            current_time = clock.get_elapsed_time()

        # Update conflict manager reservations if active
        if conflict_manager is not None:
            conflict_manager.update_reservations(current_time)

        # Update each vehicle
        to_remove: List[Vehicle] = []

        for vehicle in self.active_vehicles:
            if vehicle.state == VehicleState.EXITED:
                to_remove.append(vehicle)
                continue

            self._attempt_lane_change(vehicle, current_time, engine)

            # Leader detection with all safety layers
            leader, gap = find_leader(
                vehicle,
                getattr(engine, "network", None),
                self.active_vehicles,
                conflict_manager=conflict_manager,
                current_time=current_time,
            )

            # Calculate acceleration using IDM
            acc = idm.calculate_acceleration(
                speed=vehicle.speed,
                desired_speed=vehicle.desired_speed,
                lead_speed=leader.speed if leader is not None else None,
                gap=gap if leader is not None else None,
            )

            # Update kinematics
            vehicle.update_state(acc, dt)

            if vehicle.state == VehicleState.EXITED:  # type: ignore[comparison-overlap]
                vehicle.exit_time = current_time
                # Release any conflict zone reservations
                if conflict_manager is not None:
                    conflict_manager.release_vehicle(vehicle.vehicle_id)
                to_remove.append(vehicle)

        # Move exited vehicles from active to exited list
        for vehicle in to_remove:
            if vehicle in self.active_vehicles:
                self.active_vehicles.remove(vehicle)
            if vehicle not in self.exited_vehicles:
                self.exited_vehicles.append(vehicle)

        # ── Post-update collision audit ────────────────────────────────
        self._collision_audit()

    def _collision_audit(self) -> None:
        """Scan for overlapping vehicles using Separating Axis Theorem on bounding boxes."""
        n = len(self.active_vehicles)
        for i in range(n):
            va = self.active_vehicles[i]
            if va.lane is None:
                continue

            for j in range(i + 1, n):
                vb = self.active_vehicles[j]
                if vb.lane is None:
                    continue

                # Skip vehicles on the same lane — close following is normal
                if va.lane is vb.lane:
                    continue

                # Skip parallel lanes of the same street (starting with same direction prefix)
                id_a = va.lane.lane_id.lower()
                id_b = vb.lane.lane_id.lower()

                def get_dir(lane_id: str) -> str:
                    lid = lane_id.lower()
                    if lid.startswith("conn_"):
                        return lid.split("_")[1][0]
                    if lid and lid[0] in ("n", "s", "e", "w"):
                        return lid[0]
                    return lane_id

                if get_dir(id_a) == get_dir(id_b):
                    continue

                # Skip vehicles that share any lane in their routes (same path)
                va_lane_ids = (
                    {lane_obj.lane_id for lane_obj in va.route} if va.route else set()
                )
                vb_lane_ids = (
                    {lane_obj.lane_id for lane_obj in vb.route} if vb.route else set()
                )
                if va_lane_ids & vb_lane_ids:
                    continue

                # Quick bounding radius check before running full SAT
                ax, ay = va.coords
                bx, by = vb.coords
                dx = bx - ax
                dy = by - ay
                dist_sq = dx * dx + dy * dy
                max_radius = (va.length + vb.length) * 0.6
                if dist_sq > max_radius * max_radius:
                    continue

                # Exact SAT collision check on Oriented Bounding Boxes
                box_a = va.get_bounding_box()
                box_b = vb.get_bounding_box()
                if _check_sat_overlap(box_a, box_b):
                    self._collision_count += 1
                    slower = va if va.speed <= vb.speed else vb
                    slower.speed = 0.0
                    slower.acceleration = 0.0
                    logger.warning(
                        "Collision detected: %s ↔ %s (lanes: %s ↔ %s)",
                        va.vehicle_id,
                        vb.vehicle_id,
                        va.lane.lane_id,
                        vb.lane.lane_id,
                    )

    def get_active_counts(self) -> Dict[Direction, Dict[VehicleState, int]]:
        """Returns active count summaries categorized by direction and current vehicle state."""
        summary = {d: {s: 0 for s in VehicleState} for d in Direction}

        for v in self.active_vehicles:
            if not v.route or v.state == VehicleState.EXITED:
                continue

            # Infer origin direction from route start lane ID
            lane_id = v.route[0].lane_id.lower()
            direction = None
            if lane_id.startswith("n"):
                direction = Direction.NORTH
            elif lane_id.startswith("s"):
                direction = Direction.SOUTH
            elif lane_id.startswith("e"):
                direction = Direction.EAST
            elif lane_id.startswith("w"):
                direction = Direction.WEST

            if direction is not None:
                summary[direction][v.state] += 1

        return summary

    def _attempt_lane_change(
        self, vehicle: Vehicle, current_time: float, engine: Any
    ) -> None:
        """Attempt to perform a lane change if conditions permit and it is beneficial."""
        current_lane = vehicle.lane
        can_change_lane = (
            getattr(vehicle, "turn_intent", None) == TurnIntent.STRAIGHT
            and current_lane is not None
            and vehicle.route
            and current_lane == vehicle.route[0]
            and (current_lane.length - vehicle.position >= 20.0)
            and (
                current_time - self._last_lane_change.get(vehicle.vehicle_id, -999.0)
                >= 3.0
            )
        )

        if not (can_change_lane and current_lane is not None):
            return

        network = getattr(engine, "network", None)
        if network is None:
            return

        # Determine approach direction
        lane_id = current_lane.lane_id.lower()
        direction = None
        if lane_id.startswith("n_in_"):
            direction = Direction.NORTH
        elif lane_id.startswith("s_in_"):
            direction = Direction.SOUTH
        elif lane_id.startswith("e_in_"):
            direction = Direction.EAST
        elif lane_id.startswith("w_in_"):
            direction = Direction.WEST

        if direction is None:
            return

        try:
            approach = network.get_incoming_approach(direction)
            lanes = approach.get_lanes()
            if len(lanes) <= 1:
                return

            curr_idx = lanes.index(current_lane)
            # Candidates: adjacent lanes
            candidates = []
            if curr_idx > 0:
                candidates.append(curr_idx - 1)
            if curr_idx < len(lanes) - 1:
                candidates.append(curr_idx + 1)

            # Evaluate current gap
            curr_gap = float("inf")
            curr_leader = None
            for v in current_lane.get_vehicles():
                if v is vehicle:
                    continue
                dist = v.position - vehicle.position
                if 0 < dist < curr_gap:
                    curr_gap = dist
                    curr_leader = v

            # Also check if we are blocked by a red light
            is_blocked_by_light = False
            virtual_obs = getattr(current_lane, "virtual_obstacle", None)
            if virtual_obs is not None:
                obs_dist = virtual_obs.position - vehicle.position
                if 0 < obs_dist < min(curr_gap, 25.0):
                    curr_gap = obs_dist
                    is_blocked_by_light = True

            # We want to switch if our path is blocked or we are stuck behind a slower leader
            is_slow_leader = (
                curr_leader is not None
                and curr_leader.speed < vehicle.speed - 2.0
                and curr_gap < 20.0
            )
            if is_slow_leader or is_blocked_by_light:
                best_target_idx = None
                best_target_gap = -1.0

                for target_idx in candidates:
                    target_lane = lanes[target_idx]
                    # Check safety
                    ahead_gap = float("inf")
                    behind_gap = float("inf")
                    behind_veh = None

                    for v in target_lane.get_vehicles():
                        dist = v.position - vehicle.position
                        if dist >= 0:
                            if dist < ahead_gap:
                                ahead_gap = dist
                        else:
                            dist_behind = -dist
                            if dist_behind < behind_gap:
                                behind_gap = dist_behind
                                behind_veh = v

                    # Also check target lane virtual obstacle
                    target_virtual_obs = getattr(target_lane, "virtual_obstacle", None)
                    if target_virtual_obs is not None:
                        obs_dist = target_virtual_obs.position - vehicle.position
                        if 0 < obs_dist < ahead_gap:
                            ahead_gap = obs_dist

                    # Safety threshold: at least minimum gap + vehicle length
                    safe_behind = True
                    if behind_veh is not None:
                        speed_diff = max(0.0, behind_veh.speed - vehicle.speed)
                        safe_behind = behind_gap > (
                            vehicle.length + 3.0 + speed_diff * 1.5
                        )
                    else:
                        safe_behind = behind_gap > (vehicle.length + 3.0)

                    safe_ahead = ahead_gap > (vehicle.length + 3.0)

                    if safe_behind and safe_ahead:
                        if ahead_gap > curr_gap + 12.0 or ahead_gap > 35.0:
                            if ahead_gap > best_target_gap:
                                best_target_gap = ahead_gap
                                best_target_idx = target_idx

                if best_target_idx is not None:
                    target_lane = lanes[best_target_idx]
                    current_lane.remove_vehicle(vehicle)
                    vehicle.lane = target_lane
                    target_lane.add_vehicle(vehicle)
                    self._last_lane_change[vehicle.vehicle_id] = current_time
                    # Regenerate route with new lane index
                    vehicle.route = network.generate_route(
                        direction, best_target_idx, vehicle.turn_intent
                    )
        except Exception as e:
            logger.error(f"Error changing lane for vehicle {vehicle.vehicle_id}: {e}")
