"""Realistic multi-phase fixed-time signal controller.

Models a real-world intersection signal cycle for right-hand traffic (vehicles
drive on the right side of the road):

    For each direction (N → S → E → W), the cycle contains:
        1. **Straight + Right green** (long duration, ~25 s)
           Right-turners and straight traffic can proceed — they don't cross
           oncoming traffic on a right-hand-drive road.
        2. **Left-turn protected green** (short duration, ~10 s)
           Left-turners get a dedicated phase because they must cross oncoming
           traffic.
        3. **Yellow** (transitional, ~4 s)
        4. **All-Red clearance** (~2 s)

    The full cycle processes one direction at a time, which is the standard
    approach used at most signalised intersections.

Per-lane blocking uses virtual obstacles.  Lanes are tagged by turn intent:
    - With 1 lane per approach: all movements share the lane.
    - With 2 lanes: lane 0 → left; lane 1 → straight + right.
    - With 3+ lanes: lane 0 → left; middle → straight; last → right.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from src.controllers.base import BaseController
from src.controllers.virtual_obstacle import VirtualObstacle
from src.core.enums import Direction, TurnIntent
from src.roads.network import RoadNetwork
from src.vehicles.vehicle import Vehicle

# ---------------------------------------------------------------------------
# Phase descriptor
# ---------------------------------------------------------------------------


class Phase:
    """Describes one phase of the signal cycle."""

    __slots__ = ("name", "direction", "allowed_turns", "duration", "color")

    def __init__(
        self,
        name: str,
        direction: Direction,
        allowed_turns: Tuple[TurnIntent, ...],
        duration: float,
        color: str,
    ) -> None:
        self.name = name
        self.direction = direction
        self.allowed_turns = allowed_turns
        self.duration = duration
        self.color = color  # "green", "yellow", "red"


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------


class FixedTimeSignalController(BaseController):
    """Controls intersection traffic using a realistic multi-phase signal plan.

    The phase plan cycles one direction at a time:
        direction_straight_right → direction_left → direction_yellow → all_red
    repeated for N, S, E, W (configurable order).
    """

    # Default direction order
    _DEFAULT_DIRECTION_ORDER: Tuple[Direction, ...] = (
        Direction.NORTH,
        Direction.SOUTH,
        Direction.EAST,
        Direction.WEST,
    )

    def __init__(self, config: Dict[str, Any], network: RoadNetwork) -> None:
        self.config: Dict[str, Any] = config
        self.network: RoadNetwork = network

        ctrl_cfg = config.get("controller", {})

        # Configurable durations (seconds)
        self.straight_right_duration: float = ctrl_cfg.get(
            "straightRightDuration", 15.0
        )
        self.left_duration: float = ctrl_cfg.get("leftDuration", 5.0)
        self.yellow_duration: float = ctrl_cfg.get("yellowDuration", 3.0)
        self.all_red_duration: float = ctrl_cfg.get("allRedDuration", 2.0)

        # Also support legacy keys for backward compat
        if "greenDuration" in ctrl_cfg and "straightRightDuration" not in ctrl_cfg:
            self.straight_right_duration = ctrl_cfg["greenDuration"]
        if "greenTime" in ctrl_cfg and "straightRightDuration" not in ctrl_cfg:
            self.straight_right_duration = ctrl_cfg["greenTime"]
        if "yellowTime" in ctrl_cfg and "yellowDuration" not in ctrl_cfg:
            self.yellow_duration = ctrl_cfg["yellowTime"]
        if "allRedTime" in ctrl_cfg and "allRedDuration" not in ctrl_cfg:
            self.all_red_duration = ctrl_cfg["allRedTime"]

        # Direction processing order
        self.direction_order: Tuple[Direction, ...] = self._DEFAULT_DIRECTION_ORDER

        # Build phase sequence
        self.phases: List[Phase] = self._build_phase_sequence()

        self.time_in_current_state: float = 0.0
        self.cycle_number: int = 0
        self.current_phase_idx: int = 0

        self.reset()

    def _build_phase_sequence(self) -> List[Phase]:
        """Construct the full cycle of phases."""
        phases: List[Phase] = []

        for direction in self.direction_order:
            # Phase 1: Straight + Right (long green)
            phases.append(
                Phase(
                    name=f"{direction.value}_straight_right",
                    direction=direction,
                    allowed_turns=(TurnIntent.STRAIGHT, TurnIntent.RIGHT),
                    duration=self.straight_right_duration,
                    color="green",
                )
            )
            # Phase 2: Left only (short green)
            phases.append(
                Phase(
                    name=f"{direction.value}_left",
                    direction=direction,
                    allowed_turns=(TurnIntent.LEFT,),
                    duration=self.left_duration,
                    color="green",
                )
            )
            # Phase 3: Yellow (all movements for this direction)
            phases.append(
                Phase(
                    name=f"{direction.value}_yellow",
                    direction=direction,
                    allowed_turns=(
                        TurnIntent.LEFT,
                        TurnIntent.STRAIGHT,
                        TurnIntent.RIGHT,
                    ),
                    duration=self.yellow_duration,
                    color="yellow",
                )
            )
            # Phase 4: All-red clearance
            phases.append(
                Phase(
                    name="all_red",
                    direction=direction,  # direction is irrelevant for all-red
                    allowed_turns=(),
                    duration=self.all_red_duration,
                    color="red",
                )
            )

        return phases

    # ------------------------------------------------------------------
    # Lane → turn-intent mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _lane_turn_intent(lane_index: int, total_lanes: int) -> Tuple[TurnIntent, ...]:
        """Determine which turn intents a lane serves based on its index.

        Policy:
            - 1 lane: serves all movements (LEFT, STRAIGHT, RIGHT).
            - 2 lanes: lane 0 = dedicated LEFT; lane 1 = STRAIGHT + RIGHT.
            - 3+ lanes: lane 0 = dedicated LEFT; middle lanes = STRAIGHT; last lane = RIGHT.
        """
        if total_lanes <= 1:
            return (TurnIntent.LEFT, TurnIntent.STRAIGHT, TurnIntent.RIGHT)
        elif total_lanes == 2:
            if lane_index == 0:
                return (TurnIntent.LEFT,)
            return (TurnIntent.STRAIGHT, TurnIntent.RIGHT)
        else:
            if lane_index == 0:
                return (TurnIntent.LEFT,)
            elif lane_index == total_lanes - 1:
                return (TurnIntent.RIGHT,)
            return (TurnIntent.STRAIGHT,)

    # ------------------------------------------------------------------
    # BaseController interface
    # ------------------------------------------------------------------

    def reset(self) -> None:
        self.time_in_current_state = 0.0
        self.cycle_number = 0
        self.current_phase_idx = 0
        self._apply_signals()

    @property
    def current_phase(self) -> Phase:
        return self.phases[self.current_phase_idx]

    @property
    def phase_time_remaining(self) -> float:
        return max(0.0, self.current_phase.duration - self.time_in_current_state)

    def update(self, delta_time: float, active_vehicles: List[Vehicle]) -> None:
        self.time_in_current_state += delta_time
        phase = self.current_phase

        if self.time_in_current_state >= phase.duration:
            self.time_in_current_state -= phase.duration
            old_idx = self.current_phase_idx
            self.current_phase_idx = (self.current_phase_idx + 1) % len(self.phases)

            if self.current_phase_idx < old_idx:
                self.cycle_number += 1

        self._apply_signals()

    def _apply_signals(self) -> None:
        """Set virtual obstacles on every lane based on the active phase."""
        phase = self.current_phase

        for d in Direction:
            try:
                approach = self.network.get_incoming_approach(d)
            except KeyError:
                continue

            lane_list = approach.get_lanes()
            total_lanes = len(lane_list)

            for lane_idx, lane in enumerate(lane_list):
                lane_turns = self._lane_turn_intent(lane_idx, total_lanes)

                # Determine if this lane should be green or yellow clearance
                should_be_green = False
                is_yellow_phase = False

                if phase.direction == d and any(t in phase.allowed_turns for t in lane_turns):
                    if phase.color == "green":
                        should_be_green = True
                    elif phase.color == "yellow":
                        is_yellow_phase = True

                if should_be_green:
                    lane.virtual_obstacle = None
                elif is_yellow_phase:
                    # Allow dilemma zone clearance during yellow phase
                    lane.virtual_obstacle = VirtualObstacle(position=lane.length, is_yellow=True)
                else:
                    # Block the lane with a virtual obstacle at the stop line
                    lane.virtual_obstacle = VirtualObstacle(position=lane.length, is_yellow=False)

    # ------------------------------------------------------------------
    # State snapshot (for the frontend / API)
    # ------------------------------------------------------------------

    def get_state(self) -> Dict[str, Any]:
        phase = self.current_phase

        signals: List[Dict[str, Any]] = []
        for d in Direction:
            try:
                self.network.get_incoming_approach(d)
            except KeyError:
                signals.append(
                    {"direction": d.value, "color": "red", "allowedTurns": []}
                )
                continue

            # lanes not needed

            # Determine aggregate color and allowed turns for this direction
            if phase.direction == d and phase.color in ("green", "yellow"):
                color = phase.color
                allowed = [t.value for t in phase.allowed_turns]
            else:
                color = "red"
                allowed = []

            signals.append(
                {
                    "direction": d.value,
                    "color": color,
                    "allowedTurns": allowed,
                }
            )

        return {
            "type": "fixed_time_signal",
            "timeInCurrentState": round(self.time_in_current_state, 2),
            "currentPhase": phase.name,
            "phaseTimeRemaining": round(self.phase_time_remaining, 2),
            "cycleNumber": self.cycle_number,
            "activeDirection": phase.direction.value,
            "activeColor": phase.color,
            "signals": signals,
        }
