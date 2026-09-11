import pytest

from src.roads.lane import Lane
from src.vehicles.router import find_leader
from src.vehicles.vehicle import Vehicle


def test_find_leader_empty_lane() -> None:
    lane = Lane("w_in_0", -100.0, 0.0, 0.0, 0.0)
    v1 = Vehicle("veh_1", 4.5, 2.0, 10.0, [lane], start_position=5.0)
    lane._vehicles.append(v1)

    leader, gap = find_leader(v1)
    assert leader is None
    assert gap == float("inf")


def test_find_leader_physical_leader() -> None:
    lane = Lane("w_in_0", -100.0, 0.0, 0.0, 0.0)
    v1 = Vehicle("veh_1", 4.5, 2.0, 10.0, [lane], start_position=5.0)
    v2 = Vehicle("veh_2", 4.5, 2.0, 10.0, [lane], start_position=20.0)
    lane._vehicles.extend([v1, v2])

    leader, gap = find_leader(v1)
    assert leader == v2
    # gap = v2.pos - v2.length/2 - (v1.pos + v1.length/2) = 20 - 2.25 - 7.25 = 10.5
    assert pytest.approx(gap) == 10.5


def test_find_leader_none_lane_or_invalid_route() -> None:
    lane1 = Lane("l1", 0, 0, 10, 0)
    v1 = Vehicle("v1", 4.0, 2.0, 10.0, [lane1], start_position=2.0)

    v1.lane = None
    assert find_leader(v1) == (None, float("inf"))

    v1.lane = Lane("l_foreign", 0, 0, 10, 0)
    assert find_leader(v1) == (None, float("inf"))


def test_find_leader_virtual_obstacle() -> None:
    from src.controllers.fixed_time_signal import VirtualObstacle

    lane = Lane("l_obs", 0.0, 0.0, 100.0, 0.0)
    lane.virtual_obstacle = VirtualObstacle(position=50.0)  # type: ignore[attr-defined]

    v = Vehicle("v_obs", 4.0, 2.0, 10.0, [lane], start_position=10.0)
    leader, gap = find_leader(v)
    assert leader is not None
    assert gap > 0


def test_find_leader_conflict_manager_and_active_vehicles() -> None:
    from src.core.enums import TurnIntent
    from src.intersection.conflict_manager import ConflictManager

    lane_in = Lane("n_in_0", 0.0, 100.0, 0.0, 10.0)
    conn_a = Lane("conn_north_0_straight", 0.0, 10.0, 0.0, -10.0)
    conn_b = Lane("conn_east_0_straight", 10.0, 0.0, -10.0, 0.0)

    cm = ConflictManager()
    cm.register_connection_lane(conn_a)
    cm.register_connection_lane(conn_b)
    cm.compute_conflict_points()

    # v1 approaching conn_a
    v1 = Vehicle(
        "v1",
        4.0,
        2.0,
        10.0,
        [lane_in, conn_a],
        start_position=95.0,
        turn_intent=TurnIntent.LEFT,
    )
    # v2 on conn_b
    v2 = Vehicle(
        "v2",
        4.0,
        2.0,
        10.0,
        [conn_b],
        start_position=5.0,
        turn_intent=TurnIntent.STRAIGHT,
    )
    v2.lane = conn_b

    leader, gap = find_leader(
        v1, active_vehicles=[v1, v2], conflict_manager=cm, current_time=0.0
    )
    assert leader is not None

    # Test when v1 is already on conn_a
    v1.lane = conn_a
    v1.position = 5.0
    leader_conn, gap_conn = find_leader(
        v1, active_vehicles=[v1, v2], conflict_manager=cm, current_time=0.0
    )
    assert leader_conn is not None


def test_find_leader_emergency_proximity() -> None:
    lane1 = Lane("l1", 0.0, 0.0, 100.0, 0.0)

    # v_main at (10.0, 0.0) heading East
    v_main = Vehicle("v_main", 4.0, 2.0, 10.0, [lane1], start_position=10.0)

    # Vehicle ahead on a different lane at (11.0, 0.0)
    lane_cross = Lane("l_cross", 11.0, -10.0, 11.0, 10.0)
    v_ahead = Vehicle("v_ahead", 4.0, 2.0, 10.0, [lane_cross], start_position=10.0)

    # Vehicle behind (dot <= 0)
    lane_behind = Lane("l_behind", 0.0, 0.0, 10.0, 0.0)
    v_behind = Vehicle("v_behind", 4.0, 2.0, 10.0, [lane_behind], start_position=5.0)

    # Vehicle far away (> 30m)
    lane_far = Lane("l_far", 90.0, 0.0, 100.0, 0.0)
    v_far = Vehicle("v_far", 4.0, 2.0, 10.0, [lane_far], start_position=0.0)

    leader, gap = find_leader(
        v_main, active_vehicles=[v_main, v_ahead, v_behind, v_far]
    )
    assert leader is not None
    assert leader.vehicle_id == "virtual_stop_line"


def test_find_leader_roundabout_spacing() -> None:
    from src.roads.network import RoadNetwork

    network = RoadNetwork()
    network.is_roundabout = True
    network.inner_radius = 10.0
    network.outer_radius = 20.0

    # R = 15.0. conn1 goes North to South (moves CCW through West)
    conn1 = Lane(
        "conn_n_0_straight",
        start_x=-1.75,
        start_y=20.0,
        end_x=1.75,
        end_y=-20.0,
        waypoints=[(-1.75, 20.0), (-15.0, 0.0), (1.75, -20.0)],
    )

    # v1 is on conn1 at the beginning (North: angle ~ 95 degrees)
    v1 = Vehicle("v1", 4.0, 2.0, 10.0, [conn1], start_position=0.0)
    v1.lane = conn1

    # v2 is ahead of v1 on the same connection lane (West: angle ~ 180 degrees)
    # The middle waypoint is (-15, 0), which is at start_position ~ 20.0. Let's put v2 at start_position=20.0
    v2 = Vehicle("v2", 4.0, 2.0, 10.0, [conn1], start_position=20.0)
    v2.lane = conn1

    leader, gap = find_leader(v1, network=network, active_vehicles=[v1, v2])
    assert leader == v2
    # Same connection-lane object: exact arc-length distance, not the
    # polar-angle/avg_radius estimate — v2.position(20.0) - v1.position(0.0)
    # - (half of each vehicle's length, 2.0+2.0).
    assert gap == 16.0


def test_find_leader_roundabout_cross_lane_object_uses_angular_estimate() -> None:
    """Regression: two vehicles on DIFFERENT connection-lane objects (same
    circulating lane index) must still use the polar-angle/avg_radius
    estimate — this fix only changes the exact-same-Lane-object case above,
    not this cross-lane-object path."""
    import math

    from src.roads.network import RoadNetwork

    network = RoadNetwork()
    network.is_roundabout = True
    network.inner_radius = 10.0
    network.outer_radius = 20.0

    # Ego's current lane: a straight 2-waypoint lane starting at (15, 0),
    # i.e. theta_self = atan2(0, 15) = 0.
    lane_a = Lane("conn_n_0_straight", 15.0, 0.0, -15.0, 0.0)
    vehicle = Vehicle("ego", 4.0, 2.0, 10.0, [lane_a], start_position=0.0)
    vehicle.lane = lane_a

    # Candidate's lane: a DIFFERENT Lane object, same lane index (0), whose
    # start is at (0, 15), i.e. theta_v = atan2(15, 0) = pi/2.
    lane_b = Lane("conn_e_0_straight", 0.0, 15.0, 0.0, -15.0)
    candidate = Vehicle("other", 4.0, 2.0, 10.0, [lane_b], start_position=0.0)
    candidate.lane = lane_b

    leader, gap = find_leader(
        vehicle, network=network, active_vehicles=[vehicle, candidate]
    )

    assert leader is candidate
    # avg_radius = (10+20)/2 = 15.0; diff = pi/2 - 0 = pi/2;
    # arc_dist = 15.0 * pi/2; gap = arc_dist - (2.0+2.0).
    # These lanes have no circulating_radius set (they bypass
    # RoadNetwork._get_or_create_connection_lane), so the fallback
    # avg_radius formula is exactly what should apply here.
    expected_gap = 15.0 * (math.pi / 2.0) - 4.0
    assert gap == pytest.approx(expected_gap, abs=1e-9)


def test_roundabout_connection_lane_stores_circulating_radius() -> None:
    """Fix 2: RoadNetwork._get_or_create_connection_lane must store each
    roundabout connection lane's own steady-state radius
    (Lane.circulating_radius), derived from its lane index — not the ring's
    overall average — so router.find_leader can use the lane-specific
    value instead of the (now fallback-only) avg_radius estimate."""
    from src.core.enums import Direction, TurnIntent
    from src.roads.network import RoadNetwork

    network = RoadNetwork()
    network.setup_default_intersection(
        approach_length=100.0,
        lane_width=3.5,
        lanes_per_approach=2,
        is_roundabout=True,
        inner_radius=10.0,
        outer_radius=20.0,
    )

    lane_idx0 = network.generate_route(Direction.NORTH, 0, TurnIntent.STRAIGHT)[1]
    lane_idx1 = network.generate_route(Direction.NORTH, 1, TurnIntent.STRAIGHT)[1]

    # target_r(idx) = inner_r + (idx + 0.5) * (w_ring / total_in_lanes)
    # w_ring = outer_r - inner_r = 10.0, total_in_lanes = 2
    assert lane_idx0.circulating_radius == pytest.approx(12.5)
    assert lane_idx1.circulating_radius == pytest.approx(17.5)

    # Neither matches the ring-wide average (15.0) the old formula used —
    # confirming this is genuinely lane-specific, not a relabeled average.
    avg_radius = (10.0 + 20.0) / 2.0
    assert lane_idx0.circulating_radius != pytest.approx(avg_radius)
    assert lane_idx1.circulating_radius != pytest.approx(avg_radius)


def test_find_leader_roundabout_cross_lane_object_uses_lane_specific_radius() -> None:
    """Fix 2 regression: once a connection lane carries its own
    circulating_radius (as real roundabout lanes do via network.py — see
    test_roundabout_connection_lane_stores_circulating_radius above), the
    cross-lane-object same-index gap must use THAT radius, not the ring's
    overall average, and the result must differ from the old avg_radius-
    only formula's value."""
    import math

    from src.roads.network import RoadNetwork

    network = RoadNetwork()
    network.is_roundabout = True
    network.inner_radius = 10.0
    network.outer_radius = 20.0

    # Same coordinates as the angular-estimate test above (theta_self=0,
    # theta_v=pi/2), but with an explicit circulating_radius matching
    # target_r(0) for a 2-lane ring (12.5, per the test above) — as a real
    # multi-lane roundabout's inner circulating lane would carry.
    lane_a = Lane("conn_n_0_straight", 15.0, 0.0, -15.0, 0.0)
    lane_a.circulating_radius = 12.5
    vehicle = Vehicle("ego", 4.0, 2.0, 10.0, [lane_a], start_position=0.0)
    vehicle.lane = lane_a

    lane_b = Lane("conn_e_0_straight", 0.0, 15.0, 0.0, -15.0)
    lane_b.circulating_radius = 12.5
    candidate = Vehicle("other", 4.0, 2.0, 10.0, [lane_b], start_position=0.0)
    candidate.lane = lane_b

    leader, gap = find_leader(
        vehicle, network=network, active_vehicles=[vehicle, candidate]
    )

    assert leader is candidate
    # Correct: uses lane_a.circulating_radius (12.5), not avg_radius (15.0).
    expected_gap = 12.5 * (math.pi / 2.0) - 4.0
    assert gap == pytest.approx(expected_gap, abs=1e-9)

    # Explicitly catch a regression back to the old avg_radius-only
    # formula, which would have given a different (larger) gap here.
    old_formula_gap = 15.0 * (math.pi / 2.0) - 4.0
    assert gap != pytest.approx(old_formula_gap, abs=1e-9)


def test_find_leader_roundabout_different_lane_index_not_matched() -> None:
    """A candidate on a different circulating lane index must never be
    treated as a Layer-1 leader, regardless of angular position — this
    batch's radius fix must not affect that skip logic."""
    from src.roads.network import RoadNetwork

    network = RoadNetwork()
    network.is_roundabout = True
    network.inner_radius = 10.0
    network.outer_radius = 20.0

    lane_a = Lane("conn_n_0_straight", 15.0, 0.0, -15.0, 0.0)
    vehicle = Vehicle("ego", 4.0, 2.0, 10.0, [lane_a], start_position=0.0)
    vehicle.lane = lane_a

    # Different lane index (1, not 0) — angularly "ahead" (theta=pi/2), but
    # must be skipped entirely.
    lane_b = Lane("conn_e_1_straight", 0.0, 15.0, 0.0, -15.0)
    other = Vehicle("other", 4.0, 2.0, 10.0, [lane_b], start_position=0.0)
    other.lane = lane_b

    leader, gap = find_leader(
        vehicle, network=network, active_vehicles=[vehicle, other]
    )
    assert leader is None
    assert gap == float("inf")
