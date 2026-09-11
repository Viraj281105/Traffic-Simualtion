import math
from typing import Any, Dict, List, Optional, Tuple

from src.core.enums import Direction, TurnIntent
from src.roads.approach import Approach
from src.roads.lane import Lane


class RoadNetwork:
    """Manages the network topology of the intersection, containing approaches and lanes.

    Connection lanes (the lanes that traverse the intersection) are created once
    and cached so that every vehicle travelling the same path shares the *same*
    ``Lane`` instance.  This is critical for correct leader detection — vehicles
    on the same physical path must see each other through the lane's vehicle list.
    """

    def __init__(self) -> None:
        self._incoming: Dict[Direction, Approach] = {}
        self._outgoing: Dict[Direction, Approach] = {}

        # Cache of connection lanes: (origin_dir, lane_idx, turn_intent) → Lane
        self._connection_lane_cache: Dict[Tuple[Direction, int, TurnIntent], Lane] = {}

    def add_incoming_approach(self, approach: Approach) -> None:
        self._incoming[approach.direction] = approach

    def add_outgoing_approach(self, approach: Approach) -> None:
        self._outgoing[approach.direction] = approach

    def get_incoming_approach(self, direction: Direction) -> Approach:
        if direction not in self._incoming:
            raise KeyError(f"No incoming approach for direction {direction}")
        return self._incoming[direction]

    def get_outgoing_approach(self, direction: Direction) -> Approach:
        if direction not in self._outgoing:
            raise KeyError(f"No outgoing approach for direction {direction}")
        return self._outgoing[direction]

    def get_all_connection_lanes(self) -> List[Lane]:
        """Return every cached connection lane (useful for conflict pre-computation)."""
        return list(self._connection_lane_cache.values())

    def validate_connectivity(self) -> None:
        # Check all directions are present in both incoming and outgoing
        for d in Direction:
            if d not in self._incoming:
                raise ValueError("Missing incoming approach")
            if d not in self._outgoing:
                raise ValueError("Missing outgoing approach")

            if len(self._incoming[d].get_lanes()) == 0:
                raise ValueError(f"Incoming approach {d} has zero lanes")
            if len(self._outgoing[d].get_lanes()) == 0:
                raise ValueError(f"Outgoing approach {d} has zero lanes")

    def setup_default_intersection(
        self,
        approach_length: float = 100.0,
        lane_width: float = 3.5,
        lanes_per_approach: Any = 2,
        is_roundabout: bool = False,
        inner_radius: float = 10.0,
        outer_radius: float = 20.0,
    ) -> None:
        self.is_roundabout = is_roundabout
        self.inner_radius = inner_radius
        self.outer_radius = outer_radius

        # Clear existing
        self._incoming.clear()
        self._outgoing.clear()
        self._connection_lane_cache.clear()

        for d in Direction:
            in_approach = Approach(d)
            out_approach = Approach(d)

            # Support both int and dict configurations
            if isinstance(lanes_per_approach, dict):
                lane_count = lanes_per_approach.get(d.value, 2)
            else:
                lane_count = int(lanes_per_approach)

            boundary = outer_radius if is_roundabout else (lane_count * lane_width)

            for i in range(lane_count):
                if d == Direction.NORTH:
                    # Incoming: North to South (moves down, x < 0)
                    in_x = -(i + 0.5) * lane_width
                    in_lane = Lane(
                        f"n_in_{i}",
                        start_x=in_x,
                        start_y=approach_length,
                        end_x=in_x,
                        end_y=boundary,
                    )
                    # Outgoing: South to North (moves up, x > 0)
                    out_x = (i + 0.5) * lane_width
                    out_lane = Lane(
                        f"n_out_{i}",
                        start_x=out_x,
                        start_y=boundary,
                        end_x=out_x,
                        end_y=approach_length,
                    )

                elif d == Direction.SOUTH:
                    # Incoming: South to North (moves up, x > 0)
                    in_x = (i + 0.5) * lane_width
                    in_lane = Lane(
                        f"s_in_{i}",
                        start_x=in_x,
                        start_y=-approach_length,
                        end_x=in_x,
                        end_y=-boundary,
                    )
                    # Outgoing: North to South (moves down, x < 0)
                    out_x = -(i + 0.5) * lane_width
                    out_lane = Lane(
                        f"s_out_{i}",
                        start_x=out_x,
                        start_y=-boundary,
                        end_x=out_x,
                        end_y=-approach_length,
                    )

                elif d == Direction.EAST:
                    # Incoming: East to West (moves left, y > 0)
                    in_y = (i + 0.5) * lane_width
                    in_lane = Lane(
                        f"e_in_{i}",
                        start_x=approach_length,
                        start_y=in_y,
                        end_x=boundary,
                        end_y=in_y,
                    )
                    # Outgoing: West to East (moves right, y < 0)
                    out_y = -(i + 0.5) * lane_width
                    out_lane = Lane(
                        f"e_out_{i}",
                        start_x=boundary,
                        start_y=out_y,
                        end_x=approach_length,
                        end_y=out_y,
                    )

                elif d == Direction.WEST:
                    # Incoming: West to East (moves right, y < 0)
                    in_y = -(i + 0.5) * lane_width
                    in_lane = Lane(
                        f"w_in_{i}",
                        start_x=-approach_length,
                        start_y=in_y,
                        end_x=-boundary,
                        end_y=in_y,
                    )
                    # Outgoing: East to West (moves left, y > 0)
                    out_y = (i + 0.5) * lane_width
                    out_lane = Lane(
                        f"w_out_{i}",
                        start_x=-boundary,
                        start_y=out_y,
                        end_x=-approach_length,
                        end_y=out_y,
                    )

                in_approach.add_lane(in_lane)
                out_approach.add_lane(out_lane)

            self.add_incoming_approach(in_approach)
            self.add_outgoing_approach(out_approach)

        # Pre-create all possible connection lanes
        self._precompute_connection_lanes()

    # ------------------------------------------------------------------
    # Connection lane management
    # ------------------------------------------------------------------

    def _precompute_connection_lanes(self) -> None:
        """Create and cache every possible connection lane.

        This ensures that all vehicles taking the same path through the
        intersection share the *same* Lane object, which is essential for
        correct lane-based leader detection.
        """
        for direction in Direction:
            try:
                incoming = self.get_incoming_approach(direction)
            except KeyError:
                continue

            for lane_idx in range(len(incoming.get_lanes())):
                for turn in TurnIntent:
                    try:
                        self._get_or_create_connection_lane(direction, lane_idx, turn)
                    except (KeyError, IndexError):
                        # Some combinations might not be valid
                        pass

    @staticmethod
    def _resolve_exit_lane_index(
        lane_index: int,
        total_in_lanes: int,
        total_out_lanes: int,
        turn_intent: TurnIntent,
    ) -> int:
        if total_out_lanes <= 1:
            return 0
        if turn_intent == TurnIntent.LEFT:
            return 0
        elif turn_intent == TurnIntent.RIGHT:
            return total_out_lanes - 1
        else:  # STRAIGHT
            if total_in_lanes <= 1:
                return total_out_lanes // 2
            if lane_index == 0:
                return 0
            if lane_index == total_in_lanes - 1:
                return total_out_lanes - 1
            # Map middle lanes proportionally
            in_ratio = lane_index / (total_in_lanes - 1)
            out_idx = round(in_ratio * (total_out_lanes - 1))
            return max(0, min(out_idx, total_out_lanes - 1))

    def _get_or_create_connection_lane(
        self, origin_direction: Direction, lane_index: int, turn_intent: TurnIntent
    ) -> Lane:
        """Return the cached connection lane, creating it if necessary."""
        key = (origin_direction, lane_index, turn_intent)
        if key in self._connection_lane_cache:
            return self._connection_lane_cache[key]

        incoming_approach = self.get_incoming_approach(origin_direction)
        incoming_lane = incoming_approach.get_lanes()[lane_index]

        target_direction = self._resolve_target_direction(origin_direction, turn_intent)
        outgoing_approach = self.get_outgoing_approach(target_direction)

        total_in_lanes = len(incoming_approach.get_lanes())
        total_out_lanes = len(outgoing_approach.get_lanes())
        exit_lane_index = self._resolve_exit_lane_index(
            lane_index, total_in_lanes, total_out_lanes, turn_intent
        )
        exit_lane = outgoing_approach.get_lanes()[exit_lane_index]

        conn_id = f"conn_{origin_direction.value}_{lane_index}_{turn_intent.value}"
        start_x, start_y = incoming_lane.end_coords
        end_x, end_y = exit_lane.start_coords

        waypoints = None
        target_r: Optional[float] = None
        if getattr(self, "is_roundabout", False):
            # Circular roundabout geometry
            inner_r = getattr(self, "inner_radius", 10.0)
            outer_r = getattr(self, "outer_radius", 20.0)
            total_in_lanes = len(incoming_approach.get_lanes())
            w_ring = outer_r - inner_r
            target_r = inner_r + (lane_index + 0.5) * (w_ring / total_in_lanes)

            # Polar angles
            angle_entry = math.atan2(start_y, start_x)
            angle_exit = math.atan2(end_y, end_x)

            # Roundabout circulates counter-clockwise (increasing angle in standard polar coordinates)
            # Ensure angle_exit > angle_entry
            if angle_exit <= angle_entry:
                angle_exit += 2 * math.pi

            waypoints = []
            num_pts = 30
            for i in range(num_pts + 1):
                t = i / float(num_pts)
                angle = angle_entry + t * (angle_exit - angle_entry)

                # Smoothly transition the radius from entry_radius to target_r, and then to exit_radius
                entry_r = math.hypot(start_x, start_y)
                exit_r = math.hypot(end_x, end_y)

                if t < 0.2:
                    u = t / 0.2
                    r = entry_r + u * (target_r - entry_r)
                elif t > 0.8:
                    u = (t - 0.8) / 0.2
                    r = target_r + u * (exit_r - target_r)
                else:
                    r = target_r

                px = r * math.cos(angle)
                py = r * math.sin(angle)
                waypoints.append((px, py))
        elif turn_intent in (TurnIntent.LEFT, TurnIntent.RIGHT):
            if origin_direction in (Direction.NORTH, Direction.SOUTH):
                cx, cy = start_x, end_y
            else:
                cx, cy = end_x, start_y

            waypoints = []
            num_pts = 12
            for i in range(num_pts + 1):
                t = i / float(num_pts)
                omt = 1.0 - t
                px = omt * omt * start_x + 2.0 * omt * t * cx + t * t * end_x
                py = omt * omt * start_y + 2.0 * omt * t * cy + t * t * end_y
                waypoints.append((px, py))

        connection_lane = Lane(
            conn_id,
            start_x=start_x,
            start_y=start_y,
            end_x=end_x,
            end_y=end_y,
            speed_limit=incoming_approach.speed_limit,
            waypoints=waypoints,
        )
        if target_r is not None:
            connection_lane.circulating_radius = target_r

        self._connection_lane_cache[key] = connection_lane
        return connection_lane

    @staticmethod
    def _resolve_target_direction(origin: Direction, turn: TurnIntent) -> Direction:
        """Determine the exit direction given origin and turn intent.

        Convention (right-hand traffic, driving on the right):
            LEFT:     N→E, E→S, S→W, W→N
            STRAIGHT: N→S, E→W, S→N, W→E
            RIGHT:    N→W, E→N, S→E, W→S
        """
        mapping = {
            TurnIntent.LEFT: {
                Direction.NORTH: Direction.EAST,
                Direction.EAST: Direction.SOUTH,
                Direction.SOUTH: Direction.WEST,
                Direction.WEST: Direction.NORTH,
            },
            TurnIntent.STRAIGHT: {
                Direction.NORTH: Direction.SOUTH,
                Direction.EAST: Direction.WEST,
                Direction.SOUTH: Direction.NORTH,
                Direction.WEST: Direction.EAST,
            },
            TurnIntent.RIGHT: {
                Direction.NORTH: Direction.WEST,
                Direction.EAST: Direction.NORTH,
                Direction.SOUTH: Direction.EAST,
                Direction.WEST: Direction.SOUTH,
            },
        }
        return mapping[turn][origin]

    def generate_route(
        self, origin_direction: Direction, lane_index: int, turn_intent: TurnIntent
    ) -> List[Lane]:
        """Build a three-segment route: incoming lane → connection lane → exit lane.

        The connection lane is *shared* across all vehicles taking the same
        path, so lane-based leader detection works correctly.
        """
        incoming_approach = self.get_incoming_approach(origin_direction)
        incoming_lane = incoming_approach.get_lanes()[lane_index]

        connection_lane = self._get_or_create_connection_lane(
            origin_direction, lane_index, turn_intent
        )

        target_direction = self._resolve_target_direction(origin_direction, turn_intent)
        outgoing_approach = self.get_outgoing_approach(target_direction)

        total_in_lanes = len(incoming_approach.get_lanes())
        total_out_lanes = len(outgoing_approach.get_lanes())
        exit_lane_index = self._resolve_exit_lane_index(
            lane_index, total_in_lanes, total_out_lanes, turn_intent
        )
        exit_lane = outgoing_approach.get_lanes()[exit_lane_index]

        return [incoming_lane, connection_lane, exit_lane]
