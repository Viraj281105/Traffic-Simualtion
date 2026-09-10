import math
from typing import List, Optional, Tuple

from src.core.enums import TurnIntent, VehicleState
from src.roads.lane import Lane


class Vehicle:
    """Represents a single microscopic vehicle moving along a predefined route of lanes.

    Each vehicle carries its ``turn_intent`` so the conflict manager and signal
    controller can make priority / phase decisions.  Position is clamped during
    lane transitions to prevent overshoot artifacts.
    """

    def __init__(
        self,
        vehicle_id: str,
        length: float,
        width: float,
        desired_speed: float,
        route: List[Lane],
        start_position: float = 0.0,
        initial_speed: float = 0.0,
        turn_intent: Optional[TurnIntent] = None,
        spawn_time: float = 0.0,
        wait_speed_threshold: float = 0.5,
    ) -> None:
        if not route:
            raise ValueError("Vehicle route cannot be empty")
        if length <= 0 or width <= 0:
            raise ValueError("Vehicle dimensions (length, width) must be positive")
        if desired_speed <= 0:
            raise ValueError("Desired speed must be positive")
        if initial_speed < 0:
            raise ValueError("Initial speed cannot be negative")

        self.vehicle_id: str = vehicle_id
        self.length: float = length
        self.width: float = width
        self.desired_speed: float = desired_speed
        self.route: List[Lane] = route

        self.lane: Optional[Lane] = route[0]
        self.position: float = start_position
        self.speed: float = initial_speed
        self.acceleration: float = 0.0

        # Turn intent for priority arbitration & signal phase matching
        self.turn_intent: Optional[TurnIntent] = turn_intent

        # Timing metadata
        self.spawn_time: float = spawn_time
        self.exit_time: Optional[float] = None

        # Wait threshold speed — vehicles below this speed are considered
        # "waiting" for wait-time accounting. Matches the project-wide
        # configurable waitSpeedThreshold used by MetricCollector and the
        # queue_length/idle_loss metric definitions (default 0.5 m/s).
        self._wait_threshold: float = wait_speed_threshold

        # Register vehicle to the first lane
        self.lane.add_vehicle(self)

        # Tracking variables
        self.wait_time: float = 0.0
        if self.speed < self._wait_threshold:
            self.state: VehicleState = VehicleState.WAITING
            self.stop_count: int = 1
        else:
            self.state = VehicleState.APPROACHING
            self.stop_count = 0

        # Used by stop-count hysteresis in metrics/definitions/stop_count.py
        self._hysteresis_stopped: bool = self.speed < self._wait_threshold

    @property
    def coords(self) -> Tuple[float, float]:
        if self.lane is None:
            return (0.0, 0.0)
        return self.lane.get_point_at_distance(self.position)

    @property
    def heading(self) -> float:
        if self.lane is None:
            return 0.0
        if hasattr(self.lane, "get_heading_at_distance"):
            return self.lane.get_heading_at_distance(self.position)
        return self.lane.heading

    @property
    def lane_id(self) -> str:
        if self.lane is None:
            return ""
        return self.lane.lane_id

    def update_state(self, acceleration: float, dt: float) -> None:
        if self.state == VehicleState.EXITED:
            return

        self.acceleration = acceleration

        # Calculate new speed (cannot be negative)
        self.speed = max(0.0, self.speed + acceleration * dt)

        # Update position — clamp displacement so we never overshoot more
        # than one lane boundary per tick (prevents coordinate glitches)
        displacement = self.speed * dt
        self.position += displacement

        # Manage state transitions. Stop counting is handled exclusively by
        # update_vehicle_stops() in metrics/definitions/stop_count.py (which
        # applies hysteresis via vehicle._hysteresis_stopped) — do not
        # increment stop_count here as well, or stops get double-counted.
        is_stopped = self.speed < self._wait_threshold

        if is_stopped:
            self.state = VehicleState.WAITING
            self.wait_time += dt
        else:
            self.state = VehicleState.APPROACHING

        # Handle lane transitions — process at most one transition per tick
        # to maintain deterministic ordering
        if self.lane is not None and self.position >= self.lane.length:
            try:
                curr_idx = self.route.index(self.lane)
                if curr_idx < len(self.route) - 1:
                    next_lane = self.route[curr_idx + 1]
                    overflow = self.position - self.lane.length
                    # Clamp overflow to avoid teleporting far into the next lane
                    overflow = min(overflow, next_lane.length * 0.5)
                    self.lane.remove_vehicle(self)
                    self.lane = next_lane
                    self.position = overflow
                    self.lane.add_vehicle(self)
                else:
                    # Traversed past the end of the last lane
                    self.lane.remove_vehicle(self)
                    self.lane = None
                    self.state = VehicleState.EXITED
                    self.speed = 0.0
            except ValueError:
                # Fallback if current lane is somehow not in the route
                if self.lane is not None:
                    self.lane.remove_vehicle(self)
                self.lane = None
                self.state = VehicleState.EXITED
                self.speed = 0.0

    def get_bounding_box(self) -> List[Tuple[float, float]]:

        cx, cy = self.coords
        heading_rad = math.radians(self.heading)

        h_x = math.sin(heading_rad)
        h_y = math.cos(heading_rad)

        r_x = h_y
        r_y = -h_x

        half_l = self.length / 2.0
        half_w = self.width / 2.0

        # Front-Left: center + L/2 * H - W/2 * R
        fl_x = cx + half_l * h_x - half_w * r_x
        fl_y = cy + half_l * h_y - half_w * r_y

        # Front-Right: center + L/2 * H + W/2 * R
        fr_x = cx + half_l * h_x + half_w * r_x
        fr_y = cy + half_l * h_y + half_w * r_y

        # Rear-Right: center - L/2 * H + W/2 * R
        rr_x = cx - half_l * h_x + half_w * r_x
        rr_y = cy - half_l * h_y + half_w * r_y

        # Rear-Left: center - L/2 * H - W/2 * R
        rl_x = cx - half_l * h_x - half_w * r_x
        rl_y = cy - half_l * h_y - half_w * r_y

        return [(fl_x, fl_y), (fr_x, fr_y), (rr_x, rr_y), (rl_x, rl_y)]
