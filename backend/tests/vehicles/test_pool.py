from src.core.enums import Direction, TurnIntent, VehicleState
from src.roads.lane import Lane
from src.roads.network import RoadNetwork
from src.vehicles.pool import VehiclePool
from src.vehicles.vehicle import Vehicle


def test_vehicle_pool_lifecycle_and_counts() -> None:
    pool = VehiclePool()
    assert pool.get_active_vehicles() == []
    assert pool.get_exited_vehicles() == []
    assert pool.collision_count == 0

    lane_n = Lane("n_in_0", 0.0, 100.0, 0.0, 10.0)
    lane_s = Lane("s_in_0", 0.0, -100.0, 0.0, -10.0)
    lane_e = Lane("e_in_0", 100.0, 0.0, 10.0, 0.0)
    lane_w = Lane("w_in_0", -100.0, 0.0, -10.0, 0.0)

    v_n = Vehicle("v_n", 4.0, 2.0, 10.0, [lane_n], start_position=5.0)
    v_s = Vehicle("v_s", 4.0, 2.0, 10.0, [lane_s], start_position=5.0)
    v_e = Vehicle("v_e", 4.0, 2.0, 10.0, [lane_e], start_position=5.0)
    v_w = Vehicle("v_w", 4.0, 2.0, 10.0, [lane_w], start_position=5.0)

    for v in [v_n, v_s, v_e, v_w]:
        pool.add_vehicle(v)

    counts = pool.get_active_counts()
    assert counts[Direction.NORTH][v_n.state] == 1
    assert counts[Direction.SOUTH][v_s.state] == 1
    assert counts[Direction.EAST][v_e.state] == 1
    assert counts[Direction.WEST][v_w.state] == 1

    # Test get_active_counts with empty route or EXITED vehicle
    v_empty = Vehicle("v_empty", 4.0, 2.0, 10.0, [lane_n], start_position=5.0)
    v_empty.route = []
    v_exited = Vehicle("v_exited", 4.0, 2.0, 10.0, [lane_n], start_position=5.0)
    v_exited.state = VehicleState.EXITED
    pool.add_vehicle(v_empty)
    pool.add_vehicle(v_exited)
    counts2 = pool.get_active_counts()
    assert counts2[Direction.NORTH][v_n.state] == 1


def test_vehicle_pool_update_and_exited() -> None:
    from src.core.clock import Clock
    from src.intersection.conflict_manager import ConflictManager

    lane = Lane("n_in_0", 0.0, 10.0, 0.0, 0.0)
    v = Vehicle("v1", 4.0, 2.0, 10.0, [lane], start_position=8.0, initial_speed=10.0)
    v_exited = Vehicle("v_ex", 4.0, 2.0, 10.0, [lane], start_position=10.0)
    v_exited.state = VehicleState.EXITED

    pool = VehiclePool()
    pool.add_vehicle(v)
    pool.add_vehicle(v_exited)

    cm = ConflictManager()

    class MockEngine:
        def __init__(self):
            self.network = RoadNetwork()
            self.config = {"vehicleGeneration": {}}
            self.clock = Clock(0.1)
            self.conflict_manager = cm

    engine = MockEngine()

    pool.update(0.5, engine)
    assert len(pool.get_exited_vehicles()) == 2
    assert len(pool.get_active_vehicles()) == 0


def test_vehicle_pool_collision_audit_separation() -> None:
    lane_a = Lane("lane_a", 0.0, 0.0, 10.0, 0.0)
    lane_b = Lane("lane_b", 5.0, -5.0, 5.0, 5.0)
    lane_c = Lane("lane_c", 0.0, 0.0, 10.0, 0.0)

    # va and vb intersect on different lanes/routes
    va = Vehicle("va", 4.0, 2.0, 5.0, [lane_a], start_position=5.0, initial_speed=5.0)
    vb = Vehicle("vb", 4.0, 2.0, 2.0, [lane_b], start_position=5.5, initial_speed=2.0)

    pool = VehiclePool()
    pool.add_vehicle(va)
    pool.add_vehicle(vb)
    pool._collision_audit()
    assert pool.collision_count == 1
    assert vb.speed == 0.0
    assert vb.acceleration == 0.0

    # Test collision audit skips:
    pool2 = VehiclePool()
    vc = Vehicle("vc", 4.0, 2.0, 5.0, [lane_a], start_position=1.0, initial_speed=5.0)
    vd = Vehicle(
        "vd", 4.0, 2.0, 5.0, [lane_c, lane_a], start_position=2.0, initial_speed=5.0
    )
    ve = Vehicle("ve", 4.0, 2.0, 5.0, [lane_a], start_position=5.0)
    ve.lane = None
    for v in [va, vc, vd, ve]:
        pool2.add_vehicle(v)
    pool2._collision_audit()
    assert pool2.collision_count == 0


def test_vehicle_pool_collision_debounced_across_ticks() -> None:
    """A persistent overlap between the same two vehicles is one collision
    event (counted once on the tick it starts), not one per tick the
    overlap continues; a fresh overlap after separation is a new,
    separately counted event."""
    lane_a = Lane("lane_a", 0.0, 0.0, 10.0, 0.0)
    lane_b = Lane("lane_b", 5.0, -5.0, 5.0, 5.0)

    va = Vehicle("va", 4.0, 2.0, 5.0, [lane_a], start_position=5.0, initial_speed=5.0)
    vb = Vehicle("vb", 4.0, 2.0, 2.0, [lane_b], start_position=5.5, initial_speed=2.0)

    pool = VehiclePool()
    pool.add_vehicle(va)
    pool.add_vehicle(vb)

    pool._collision_audit()
    assert pool.collision_count == 1

    # Overlap persists (positions unchanged) across further ticks — no
    # additional collision should be counted for the same ongoing overlap.
    pool._collision_audit()
    pool._collision_audit()
    assert pool.collision_count == 1

    # Vehicles separate (vb moves well outside the collision-audit radius).
    vb.position = 0.0
    pool._collision_audit()
    assert pool.collision_count == 1

    # Vehicles overlap again: this is a distinct, new collision event.
    vb.position = 5.5
    pool._collision_audit()
    assert pool.collision_count == 2


def test_collision_audit_flags_different_lane_index_conn_pairs() -> None:
    """Regression for the collision-audit "parallel lane" skip bug: two
    conn_* vehicles from the same origin but a DIFFERENT circulating lane
    index are a genuine cross-lane-index roundabout weave conflict — the
    exact case router.find_leader's Layer 4 is responsible for catching —
    and must remain eligible for this audit, not be skipped as merely
    "parallel". Same coordinates as test_vehicle_pool_collision_audit_
    separation's proven-overlapping pair, just with conn_* lane ids."""
    lane_a = Lane("conn_n_0_straight", 0.0, 0.0, 10.0, 0.0)
    lane_b = Lane("conn_n_1_left", 5.0, -5.0, 5.0, 5.0)

    va = Vehicle("va", 4.0, 2.0, 5.0, [lane_a], start_position=5.0, initial_speed=5.0)
    vb = Vehicle("vb", 4.0, 2.0, 2.0, [lane_b], start_position=5.5, initial_speed=2.0)

    pool = VehiclePool()
    pool.add_vehicle(va)
    pool.add_vehicle(vb)
    pool._collision_audit()

    assert pool.collision_count == 1
    assert vb.speed == 0.0


def test_collision_audit_still_skips_same_lane_index_conn_pairs() -> None:
    """Two conn_* lanes from the same origin AND the same circulating lane
    index (different turn intents) are one continuous physical path per
    Layer 1's same-lane-index following (router.find_leader) — they must
    stay grouped/skipped by the audit, exactly as before this fix."""
    lane_a = Lane("conn_n_0_straight", 0.0, 0.0, 10.0, 0.0)
    lane_b = Lane("conn_n_0_left", 5.0, -5.0, 5.0, 5.0)

    va = Vehicle("va", 4.0, 2.0, 5.0, [lane_a], start_position=5.0, initial_speed=5.0)
    vb = Vehicle("vb", 4.0, 2.0, 2.0, [lane_b], start_position=5.5, initial_speed=2.0)

    pool = VehiclePool()
    pool.add_vehicle(va)
    pool.add_vehicle(vb)
    pool._collision_audit()

    assert pool.collision_count == 0


def test_collision_audit_still_skips_ordinary_parallel_lanes() -> None:
    """Ordinary same-direction parallel approach lanes (e.g. n_in_0 vs
    n_in_1) must retain their existing skip — this fix only changes how
    conn_* lanes are grouped, not the plain-direction branch."""
    lane_a = Lane("n_in_0", 0.0, 0.0, 10.0, 0.0)
    lane_b = Lane("n_in_1", 5.0, -5.0, 5.0, 5.0)

    va = Vehicle("va", 4.0, 2.0, 5.0, [lane_a], start_position=5.0, initial_speed=5.0)
    vb = Vehicle("vb", 4.0, 2.0, 2.0, [lane_b], start_position=5.5, initial_speed=2.0)

    pool = VehiclePool()
    pool.add_vehicle(va)
    pool.add_vehicle(vb)
    pool._collision_audit()

    assert pool.collision_count == 0


def test_attempt_lane_change_handles_unregistered_direction_gracefully() -> None:
    """Regression for narrowing pool.py's _attempt_lane_change from a bare
    `except Exception` to (KeyError, ValueError, IndexError): a vehicle
    whose approach direction isn't registered on the network (a genuine,
    expected "lane data unavailable" condition — network.get_incoming_
    approach() raises KeyError, matching the pattern used throughout
    roundabout.py/router.py) must be handled gracefully, not crash the
    caller, exactly as the previous bare except did for this case."""
    lane = Lane("n_in_0", 0.0, 0.0, 0.0, 40.0)
    vehicle = Vehicle(
        "v1",
        4.0,
        2.0,
        10.0,
        [lane],
        start_position=0.0,
        turn_intent=TurnIntent.STRAIGHT,
    )

    class BareNetwork:
        """A network with no approaches registered at all, so
        get_incoming_approach() raises KeyError for every direction."""

        def get_incoming_approach(self, direction: Direction) -> None:
            raise KeyError(direction)

    class DummyEngine:
        def __init__(self) -> None:
            self.network = BareNetwork()

    pool = VehiclePool()
    pool.add_vehicle(vehicle)

    # Must not raise — the narrowed except must still catch this.
    pool._attempt_lane_change(vehicle, current_time=100.0, engine=DummyEngine())

    # No lane change occurred (network had nothing to offer).
    assert vehicle.lane is lane
