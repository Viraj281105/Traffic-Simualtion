import pytest

from src.controllers.base import BaseController
from src.controllers.fixed_time_signal import FixedTimeSignalController
from src.controllers.roundabout import RoundaboutController
from src.core.enums import Direction, TurnIntent
from src.roads.network import RoadNetwork
from src.vehicles.vehicle import Vehicle


def test_fixed_time_signal_transitions() -> None:
    """Test the new multi-phase signal controller cycles through phases correctly."""
    network = RoadNetwork()
    network.setup_default_intersection(
        approach_length=100.0, lane_width=3.5, lanes_per_approach=2
    )

    config = {
        "controller": {
            "straightRightDuration": 10,
            "leftDuration": 5,
            "yellowDuration": 3,
            "allRedDuration": 2,
        }
    }

    controller = FixedTimeSignalController(config, network)

    # Phase 0: north_straight_right (green, 10s)
    phase = controller.current_phase
    assert phase.name == "north_straight_right"
    assert phase.color == "green"
    assert controller.phase_time_remaining == 10.0

    # Advance by 5s — still in north_straight_right
    controller.update(5.0, [])
    assert controller.current_phase.name == "north_straight_right"
    assert controller.phase_time_remaining == 5.0

    # Advance by 5.1s — transition to north_left (5s)
    controller.update(5.1, [])
    assert controller.current_phase.name == "north_left"
    assert controller.current_phase.color == "green"
    assert pytest.approx(controller.phase_time_remaining, abs=0.2) == 4.9

    # Check signal state dictionary
    state = controller.get_state()
    assert state["type"] == "fixed_time_signal"
    assert state["currentPhase"] == "north_left"
    assert state["activeDirection"] == "north"

    # North should be green, others red
    for sig in state["signals"]:
        if sig["direction"] == "north":
            assert sig["color"] == "green"
            assert "left" in sig["allowedTurns"]
        else:
            assert sig["color"] == "red"

    # Advance through rest of north phases and verify south starts
    # north_left: 4.9s remaining
    controller.update(5.0, [])  # → north_yellow (3s)
    assert controller.current_phase.name == "north_yellow"

    controller.update(3.0, [])  # → all_red (2s)
    assert controller.current_phase.name == "all_red"

    controller.update(2.0, [])  # → south_straight_right
    assert controller.current_phase.name == "south_straight_right"
    assert controller.current_phase.color == "green"


def test_roundabout_controller() -> None:
    network = RoadNetwork()
    network.setup_default_intersection(
        approach_length=100.0, lane_width=3.5, lanes_per_approach=2
    )

    config = {
        "controller": {
            "innerRadius": 10.0,
            "outerRadius": 20.0,
            "criticalGap": 4.0,
            "circulatingSpeed": 8.0,
        }
    }

    controller = RoundaboutController(config, network)
    state = controller.get_state()
    assert state["type"] == "roundabout"
    assert state["innerRadius"] == 10.0
    assert state["outerRadius"] == 20.0
    assert state["gapAcceptance"] == 4.0


def test_roundabout_yielding() -> None:
    """Verifies that vehicles yield when time_gap < critical_gap, and proceed when gap > critical_gap."""
    from src.core.enums import Direction
    from src.roads.lane import Lane
    from src.vehicles.vehicle import Vehicle

    network = RoadNetwork()
    network.setup_default_intersection(100.0, 3.5, 2)
    config = {
        "controller": {
            "innerRadius": 10.0,
            "outerRadius": 20.0,
            "criticalGap": 4.0,
            "circulatingSpeed": 8.0,
        }
    }
    controller = RoundaboutController(config, network)

    # Place a circulating vehicle close to North entry point (approx 1.75, 15.0)
    # conn_circ lane ID must start with "conn" so that the controller identifies it as circulating
    conn_lane = Lane("conn_circ", 1.75, 16.0, 10.0, 16.0)
    circ_vehicle = Vehicle(
        "circ_1",
        length=4.5,
        width=2.0,
        desired_speed=8.0,
        route=[conn_lane],
        start_position=0.0,
        initial_speed=8.0,
    )

    # Update controller
    controller.update(0.1, [circ_vehicle])

    # Incoming North lane should have virtual obstacle active (yield)
    lane = network.get_incoming_approach(Direction.NORTH).get_lanes()[0]
    assert lane.virtual_obstacle is not None

    # Move circulating vehicle far away by updating its position along a long route
    conn_lane_far = Lane("conn_circ_far", 100.0, 100.0, 200.0, 100.0)
    circ_vehicle.lane = conn_lane_far
    circ_vehicle.position = 0.0

    controller.update(0.1, [circ_vehicle])

    # Obstacle should be cleared
    assert lane.virtual_obstacle is None


def test_base_controller_abstract_methods() -> None:
    class DummyController(BaseController):
        def update(self, delta_time: float, active_vehicles: list) -> None:
            super().update(delta_time, active_vehicles)

        def get_state(self) -> dict:
            return super().get_state()

        def reset(self) -> None:
            super().reset()

    dummy = DummyController()
    dummy.update(1.0, [])
    assert dummy.get_state() is None
    dummy.reset()


def test_fixed_time_signal_legacy_config_and_lane_intents() -> None:
    network = RoadNetwork()
    network.setup_default_intersection(
        approach_length=100.0, lane_width=3.5, lanes_per_approach=3
    )

    config_legacy = {
        "controller": {
            "greenDuration": 15.0,
            "yellowTime": 3.5,
            "allRedTime": 1.5,
        }
    }
    ctrl = FixedTimeSignalController(config_legacy, network)
    assert ctrl.straight_right_duration == 15.0
    assert ctrl.yellow_duration == 3.5
    assert ctrl.all_red_duration == 1.5

    config_legacy2 = {
        "controller": {
            "greenTime": 18.0,
        }
    }
    ctrl2 = FixedTimeSignalController(config_legacy2, network)
    assert ctrl2.straight_right_duration == 18.0

    # Test _lane_turn_intent
    assert len(FixedTimeSignalController._lane_turn_intent(0, 1)) == 3
    assert FixedTimeSignalController._lane_turn_intent(0, 2) == (TurnIntent.LEFT,)
    assert FixedTimeSignalController._lane_turn_intent(1, 2) == (
        TurnIntent.STRAIGHT,
        TurnIntent.RIGHT,
    )
    assert FixedTimeSignalController._lane_turn_intent(0, 3) == (TurnIntent.LEFT,)
    assert FixedTimeSignalController._lane_turn_intent(1, 3) == (TurnIntent.STRAIGHT,)
    assert FixedTimeSignalController._lane_turn_intent(2, 3) == (TurnIntent.RIGHT,)


def test_fixed_time_signal_cycle_wrap_and_missing_approach() -> None:
    network = RoadNetwork()
    # Empty network without approaches triggers KeyError in _apply_signals and get_state
    config = {
        "controller": {
            "straightRightDuration": 1.0,
            "leftDuration": 1.0,
            "yellowDuration": 1.0,
            "allRedDuration": 1.0,
        }
    }
    ctrl = FixedTimeSignalController(config, network)
    state = ctrl.get_state()
    assert len(state["signals"]) == 4

    # Advance through each phase step by step to wrap around cycle
    initial_cycles = ctrl.cycle_number
    for p in ctrl.phases:
        ctrl.update(p.duration + 0.01, [])
    assert ctrl.cycle_number > initial_cycles


def test_roundabout_missing_approach_and_yielding_metrics() -> None:
    network = RoadNetwork()
    network.setup_default_intersection(
        approach_length=50.0, lane_width=3.5, lanes_per_approach=1
    )
    config = {
        "controller": {
            "innerRadius": 8.0,
            "outerRadius": 16.0,
            "criticalGap": 3.0,
        }
    }
    ctrl = RoundaboutController(config, network)
    ctrl.reset()

    # Add a stopped vehicle near end of north lane
    lane = network.get_incoming_approach(Direction.NORTH).get_lanes()[0]
    veh = Vehicle(
        "v_yield",
        length=4.0,
        width=2.0,
        desired_speed=10.0,
        route=[lane],
        start_position=46.0,
        initial_speed=0.0,
    )
    lane.add_vehicle(veh)

    state = ctrl.get_state()
    assert state["yieldingCount"] == 1

    # Empty network KeyError branch
    empty_net = RoadNetwork()
    ctrl_empty = RoundaboutController(config, empty_net)
    ctrl_empty.reset()
    ctrl_empty.update(0.1, [])
    state_empty = ctrl_empty.get_state()
    assert state_empty["yieldingCount"] == 0


def test_roundabout_circular_leader_detection() -> None:
    from src.core.enums import Direction, TurnIntent
    from src.vehicles.router import find_leader

    network = RoadNetwork()
    network.setup_default_intersection(
        approach_length=100.0, lane_width=3.5, lanes_per_approach=2, is_roundabout=True
    )
    # Vehicle A is circulating in the roundabout
    lane_a = network.generate_route(Direction.NORTH, 0, TurnIntent.STRAIGHT)[1]
    veh_a = Vehicle(
        "veh_a",
        length=4.5,
        width=2.0,
        desired_speed=8.0,
        route=[lane_a],
        start_position=5.0,
    )
    lane_a.add_vehicle(veh_a)

    # Vehicle B is behind Vehicle A on the roundabout
    lane_b = network.generate_route(Direction.EAST, 0, TurnIntent.STRAIGHT)[1]
    veh_b = Vehicle(
        "veh_b",
        length=4.5,
        width=2.0,
        desired_speed=8.0,
        route=[lane_b],
        start_position=0.0,
    )
    lane_b.add_vehicle(veh_b)

    leader, gap = find_leader(veh_b, network=network, active_vehicles=[veh_a, veh_b])
    # It should identify veh_a as the leader
    assert leader is veh_a
