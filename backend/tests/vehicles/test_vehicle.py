import pytest

try:
    from src.core.enums import VehicleState
    from src.metrics.definitions.stop_count import update_vehicle_stops
    from src.roads.lane import Lane
    from src.vehicles.vehicle import Vehicle
except ImportError:
    pytest.skip("Vehicle modules not implemented yet", allow_module_level=True)


@pytest.fixture
def sample_route() -> list[Lane]:
    lane_1 = Lane("lane_1", 0.0, 0.0, 0.0, 100.0)  # Length 100
    lane_2 = Lane("lane_2", 0.0, 100.0, 100.0, 100.0)  # Length 100
    return [lane_1, lane_2]


def test_vehicle_initialization(sample_route: list[Lane]) -> None:
    v = Vehicle("v1", length=4.5, width=2.0, desired_speed=15.0, route=sample_route)
    assert v.vehicle_id == "v1"
    assert v.length == 4.5
    assert v.width == 2.0
    assert v.desired_speed == 15.0
    assert v.route == sample_route
    assert v.lane == sample_route[0]
    assert v.lane_id == sample_route[0].lane_id
    assert v.position == 0.0
    assert v.speed == 0.0
    assert v.acceleration == 0.0
    assert v.state == VehicleState.WAITING  # 0.0 speed is < wait threshold
    assert v.wait_time == 0.0
    assert v.stop_count == 1  # starts stopped


def test_vehicle_invalid_initialization(sample_route: list[Lane]) -> None:
    # Empty route
    with pytest.raises(ValueError, match="Vehicle route cannot be empty"):
        Vehicle("v1", 4.5, 2.0, 15.0, [])
    # Zero or negative dimensions
    with pytest.raises(ValueError, match="Vehicle dimensions .* must be positive"):
        Vehicle("v1", 0.0, 2.0, 15.0, sample_route)
    with pytest.raises(ValueError, match="Desired speed must be positive"):
        Vehicle("v1", 4.5, 2.0, -1.0, sample_route)
    with pytest.raises(ValueError, match="Initial speed cannot be negative"):
        Vehicle("v1", 4.5, 2.0, 15.0, sample_route, initial_speed=-1.0)


def test_vehicle_kinematics(sample_route: list[Lane]) -> None:
    v = Vehicle("v1", 4.5, 2.0, 15.0, sample_route, initial_speed=10.0)
    assert v.stop_count == 0  # starts moving

    # Update with constant acceleration 2.0 m/s^2 for 0.5s
    v.update_state(acceleration=2.0, dt=0.5)
    assert v.speed == 11.0  # 10 + 2 * 0.5
    assert v.position == 5.5  # 0 + 11.0 * 0.5
    assert v.state == VehicleState.APPROACHING

    # Stop tracking hysteresis — stop_count itself is maintained by
    # update_vehicle_stops() (metrics/definitions/stop_count.py), which the
    # simulation engine invokes every tick via MetricCollector. update_state()
    # only manages speed/position/state to avoid double-counting stops.
    v.update_state(acceleration=-24.0, dt=0.5)  # decelerates to 0
    assert v.speed == 0.0
    assert v.state == VehicleState.WAITING  # type: ignore[comparison-overlap]

    update_vehicle_stops(v)
    assert v.stop_count == 1


def test_vehicle_lane_transition(sample_route: list[Lane]) -> None:
    v = Vehicle(
        "v1",
        length=4.5,
        width=2.0,
        desired_speed=15.0,
        route=sample_route,
        start_position=90.0,
        initial_speed=20.0,
    )
    assert v.lane == sample_route[0]

    # Moves 10 meters, transitions to lane_2
    v.update_state(acceleration=0.0, dt=0.6)
    # Position: 90 + 20*0.6 = 102. 102 - 100 = 2 meters on lane_2.
    assert v.lane == sample_route[1]
    assert pytest.approx(v.position) == 2.0
    assert v.state == VehicleState.APPROACHING

    # Move past the end of route (exited)
    v.update_state(acceleration=0.0, dt=10.0)
    assert v.state == VehicleState.EXITED  # type: ignore[comparison-overlap]
    assert v.lane_id == ""
    assert v.speed == 0.0


def test_vehicle_bounding_box(sample_route: list[Lane]) -> None:
    v = Vehicle("v1", length=4.0, width=2.0, desired_speed=15.0, route=sample_route)
    # Center is at (0, 0)
    assert v.coords == (0.0, 0.0)
    assert v.heading == 0.0  # Heading of lane_1 (facing North)

    corners = v.get_bounding_box()
    # Facing North (positive Y):
    # Front-Left: center + L/2 along heading - W/2 perp right
    # Heading vector: (0, 1). Right vector: (1, 0)
    # FL: (0 - 1.0, 0 + 2.0) = (-1.0, 2.0)
    # FR: (0 + 1.0, 0 + 2.0) = (1.0, 2.0)
    # RR: (1.0, -2.0)
    # RL: (-1.0, -2.0)
    assert corners[0] == (-1.0, 2.0)
    assert corners[1] == (1.0, 2.0)
    assert corners[2] == (1.0, -2.0)
    assert corners[3] == (-1.0, -2.0)


def test_vehicle_none_lane_and_exited_behavior(sample_route: list[Lane]) -> None:
    v = Vehicle("v_none", 4.0, 2.0, 10.0, sample_route)
    v.lane = None

    assert v.coords == (0.0, 0.0)
    assert v.heading == 0.0
    assert v.lane_id == ""

    # update_state when exited does nothing
    v.state = VehicleState.EXITED
    v.update_state(10.0, 0.1)
    assert v.speed == 0.0


def test_vehicle_lane_transition_fallback(sample_route: list[Lane]) -> None:
    foreign_lane = Lane("foreign_lane", 0.0, 0.0, 10.0, 0.0)
    v = Vehicle("v_foreign", 4.0, 2.0, 10.0, sample_route)
    # Put vehicle on a lane that is not in its route
    v.lane = foreign_lane
    v.position = 20.0  # past foreign_lane length

    v.update_state(0.0, 0.1)
    assert v.lane is None
    assert v.state == VehicleState.EXITED
