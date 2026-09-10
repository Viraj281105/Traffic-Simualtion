from src.core.enums import Direction
from src.metrics.collector import MetricCollector
from src.metrics.definitions.fairness import calculate_directional_fairness
from src.metrics.definitions.idle_loss import calculate_idle_loss_tick
from src.metrics.definitions.queue_length import get_current_queue_lengths
from src.metrics.definitions.speed_variance import calculate_speed_variance_index
from src.metrics.definitions.stop_count import (
    calculate_average_stops,
    update_vehicle_stops,
)
from src.metrics.definitions.throughput import (
    calculate_throughput,
    calculate_throughput_rate,
)
from src.metrics.definitions.travel_time import (
    _calculate_median,
    _calculate_percentile,
    calculate_travel_time_reliability,
)
from src.metrics.definitions.wait_time import calculate_average_wait_time
from src.vehicles.vehicle import Vehicle


class DummyLane:
    def __init__(self, lane_id: str) -> None:
        self.lane_id = lane_id
        self.length = 100.0


class DummyVehicle:
    def __init__(
        self,
        speed: float,
        wait_time: float,
        stop_count: int,
        spawn_time: float = 0.0,
        exit_time: float = None,
        route=None,
    ) -> None:
        self.vehicle_id = "test"
        self.speed = speed
        self.wait_time = wait_time
        self.stop_count = stop_count
        self.spawn_time = spawn_time
        self.exit_time = exit_time
        self.route = route
        self.lane = route[0] if route else None
        self.length = 4.5
        self.width = 2.0
        self.position = 10.0
        self.acceleration = 0.0
        self.heading = 0.0
        self._hysteresis_stopped = speed < 0.1


def test_wait_time_calculator() -> None:
    v1 = DummyVehicle(0.0, 10.0, 2)
    v2 = DummyVehicle(0.0, 20.0, 3)
    assert calculate_average_wait_time([v1, v2]) == 15.0
    assert calculate_average_wait_time([]) == 0.0


def test_throughput_calculators() -> None:
    v1 = DummyVehicle(10.0, 0.0, 0, exit_time=15.0)
    v2 = DummyVehicle(10.0, 0.0, 0, exit_time=45.0)

    assert calculate_throughput([v1, v2]) == 2
    # Setting current_time=60.0 means the actual window is 60.0, rate = (2 / 60) * 60 = 2.0
    assert (
        calculate_throughput_rate([v1, v2], current_time=60.0, window_size=60.0) == 2.0
    )
    assert calculate_throughput_rate([], current_time=0.0) == 0.0
    assert calculate_throughput_rate([v1], current_time=-1.0) == 0.0


def test_queue_length_calculator() -> None:
    lane_n = DummyLane("n_in_0")
    lane_s = DummyLane("s_in_0")
    v1 = DummyVehicle(0.05, 0.0, 0, route=[lane_n])
    v2 = DummyVehicle(10.0, 0.0, 0, route=[lane_s])
    v_no_lane = DummyVehicle(0.0, 0.0, 0, route=[])
    v_no_lane.lane = None

    queues = get_current_queue_lengths([v1, v2, v_no_lane], wait_speed_threshold=0.5)
    assert queues["north"] == 1
    assert queues["south"] == 0


def test_stop_count_hysteresis() -> None:
    class MockVehicle(Vehicle):
        def __init__(self):
            self.vehicle_id = "veh_test"
            self.speed = 10.0
            self.stop_count = 0
            self.length = 4.5
            self._hysteresis_stopped = False

    v = MockVehicle()
    # Initialize the state (speed = 10.0 -> False stopped)
    update_vehicle_stops(v, 0.1)
    assert v._hysteresis_stopped is False
    assert v.stop_count == 0

    # Speed drops below 0.1 -> Stop
    v.speed = 0.05
    update_vehicle_stops(v, 0.1)
    assert v.stop_count == 1
    assert v._hysteresis_stopped is True

    # Speed goes slightly up but below 0.2 -> remains stopped
    v.speed = 0.15
    update_vehicle_stops(v, 0.1)
    assert v.stop_count == 1
    assert v._hysteresis_stopped is True

    # Speed goes above 2 * 0.1 -> unstopped
    v.speed = 0.25
    update_vehicle_stops(v, 0.1)
    assert v._hysteresis_stopped is False

    # Speed drops below 0.1 again -> Stop 2
    v.speed = 0.02
    update_vehicle_stops(v, 0.1)
    assert v.stop_count == 2

    # calculate_average_stops
    assert calculate_average_stops([]) == 0.0
    v1 = DummyVehicle(0.0, 0.0, 2)
    v2 = DummyVehicle(0.0, 0.0, 4)
    assert calculate_average_stops([v1, v2]) == 3.0


def test_speed_variance() -> None:
    v1 = DummyVehicle(10.0, 0.0, 0)
    v2 = DummyVehicle(12.0, 0.0, 0)
    assert calculate_speed_variance_index([v1, v2]) > 0.0
    # No data / fewer than 2 vehicles: 0.0 (no measured variability), not
    # the old 1.0 — this codebase's convention is "no data reports the
    # metric's best-case value" (see e.g. directional_fairness).
    assert calculate_speed_variance_index([]) == 0.0
    assert calculate_speed_variance_index([v1]) == 0.0
    # All vehicles stopped (mean speed 0): CV(t) = 0.0 per the contract's
    # explicit edge case ("all vehicles have the same speed: zero").
    v0 = DummyVehicle(0.0, 0.0, 0)
    assert calculate_speed_variance_index([v0, v0]) == 0.0
    # All vehicles at the same nonzero speed (zero variance) is the most
    # uniform, i.e. best, possible flow: also 0.0, not 1.0.
    assert calculate_speed_variance_index([v1, v1]) == 0.0


def test_travel_time_reliability() -> None:
    v1 = DummyVehicle(10.0, 0.0, 0, spawn_time=0.0, exit_time=10.0)
    v2 = DummyVehicle(10.0, 0.0, 0, spawn_time=0.0, exit_time=20.0)
    pti, sample_size = calculate_travel_time_reliability([v1, v2])
    assert pti is not None and pti > 1.0
    assert sample_size == 2

    assert _calculate_median([]) == 0.0
    assert _calculate_median([5.0]) == 5.0
    assert _calculate_median([1.0, 3.0, 5.0]) == 3.0
    assert _calculate_median([1.0, 3.0]) == 2.0

    assert _calculate_percentile([], 95.0) == 0.0
    assert _calculate_percentile([10.0], 95.0) == 10.0

    # No exited vehicles yet: "no data" reports the best-case value (1.0)
    # with a sample size of 0.
    assert calculate_travel_time_reliability([]) == (1.0, 0)
    v_no_exit = DummyVehicle(10.0, 0.0, 0, exit_time=None)
    assert calculate_travel_time_reliability([v_no_exit]) == (1.0, 0)

    # Real exit-time data whose median travel time is exactly 0 is a data
    # error per the metric contract ("a vehicle cannot have zero travel
    # time") — PTI must be reported as null (None), not a fabricated 1.0.
    v_zero = DummyVehicle(10.0, 0.0, 0, spawn_time=5.0, exit_time=5.0)
    pti_zero, sample_size_zero = calculate_travel_time_reliability([v_zero])
    assert pti_zero is None
    assert sample_size_zero == 1


def test_idle_loss() -> None:
    lane_n = DummyLane("n_in_0")
    lane_s = DummyLane("s_in_0")
    v1 = DummyVehicle(0.05, 0.0, 0, route=[lane_n])
    v_green = DummyVehicle(10.0, 0.0, 0, route=[lane_s])
    v_no_lane = DummyVehicle(0.0, 0.0, 0, route=[])
    v_no_lane.lane = None

    signals = {
        Direction.NORTH: "red",
        Direction.SOUTH: "green",
        Direction.EAST: "red",
        Direction.WEST: "red",
    }
    assert (
        calculate_idle_loss_tick([v1, v_no_lane], signals, wait_speed_threshold=0.5)
        is True
    )
    # A vehicle merely passing through (not queued) on the green approach
    # must NOT prevent an idle-loss tick: the green approach's actual queue
    # (Q_d(t), speed < threshold) is genuinely empty, matching the metric
    # contract's Q_d(t)-based definition rather than raw vehicle presence.
    assert (
        calculate_idle_loss_tick([v1, v_green], signals, wait_speed_threshold=0.5)
        is True
    )
    # But a vehicle that IS queued (stopped) on the green approach means
    # that approach's queue is genuinely non-empty, so no idle loss.
    v_green_queued = DummyVehicle(0.05, 0.0, 0, route=[lane_s])
    assert (
        calculate_idle_loss_tick(
            [v1, v_green_queued], signals, wait_speed_threshold=0.5
        )
        is False
    )

    signals_all_green = {Direction.NORTH: "green", Direction.SOUTH: "green"}
    assert calculate_idle_loss_tick([v1], signals_all_green) is False


def test_directional_fairness() -> None:
    lane_n = DummyLane("north_in_0")
    lane_s = DummyLane("south_in_0")
    v1 = DummyVehicle(0.0, 10.0, 0, route=[lane_n])
    v2 = DummyVehicle(0.0, 20.0, 0, route=[lane_s])
    assert 0.0 < calculate_directional_fairness([v1, v2]) <= 1.0
    assert calculate_directional_fairness([]) == 1.0

    v_zero = DummyVehicle(0.0, 0.0, 0, route=[lane_n])
    assert calculate_directional_fairness([v_zero]) == 1.0


def test_average_wait_and_stops_exclude_warmup_contribution() -> None:
    """A vehicle already active when warmup ends must not have its
    pre-warmup wait time / stop count counted in averageWaitTime /
    averageStopsPerVehicle — mirrors how averageDelay already clips its
    contribution at the warmup boundary via effective_spawn_t."""
    config = {
        "simulation": {"warmupTime": 5.0, "timeStep": 1.0},
        "vehicleGeneration": {"stopSpeedThreshold": 0.1, "waitSpeedThreshold": 0.5},
        "geometry": {"intersectionType": "fixed_time_signal"},
    }
    collector = MetricCollector(config)
    lane_n = DummyLane("n_in_0")
    signals = {
        Direction.NORTH: "red",
        Direction.SOUTH: "green",
        Direction.EAST: "red",
        Direction.WEST: "red",
    }

    v = DummyVehicle(0.0, 3.0, 2, spawn_time=0.0, route=[lane_n])
    v.vehicle_id = "veh_1"

    # Ticks during warmup: wait_time=3.0 / stop_count=2 were entirely
    # accrued before warmup ended.
    collector.update(2.0, [v], [], signals)
    collector.update(4.0, [v], [], signals)

    # First post-warmup tick: this is where the baseline for "veh_1"
    # (wait_time=3.0, stop_count=2) should be captured.
    collector.update(6.0, [v], [], signals)

    # Vehicle accrues more wait/stops after warmup, then exits.
    v.wait_time = 3.0 + 1.5
    v.stop_count = 2 + 1
    v.exit_time = 10.0

    metrics = collector.get_metrics(10.0, [], [v], total_spawned=1)
    # Only the post-warmup portion (1.5s wait, 1 stop) should be counted —
    # not the full 4.5s / 3 stops accrued across the vehicle's whole life.
    assert metrics["averageWaitTime"] == 1.5
    assert metrics["averageStopsPerVehicle"] == 1.0
    # totalStops previously used an unrelated scalar (stops of vehicles
    # that had already exited *during* warmup — none here) subtracted from
    # the raw post-warmup-exited stop sum, instead of the same per-vehicle
    # warmup baseline used by averageStopsPerVehicle above. It must be
    # consistent with averageStopsPerVehicle: with a single exited
    # vehicle, totalStops == averageStopsPerVehicle * 1.
    assert metrics["totalStops"] == 1


def test_metric_collector_full_lifecycle() -> None:
    config = {
        "simulation": {"warmupTime": 5.0, "timeStep": 0.1},
        "vehicleGeneration": {"stopSpeedThreshold": 0.1, "waitSpeedThreshold": 0.5},
        "geometry": {"intersectionType": "fixed_time_signal"},
        "roads": {"lanesPerApproach": 2, "laneWidth": 3.5},
    }
    collector = MetricCollector(config)

    lane_n = DummyLane("n_in_0")
    waiting_vehs = [DummyVehicle(0.0, 10.0, 1, route=[lane_n]) for _ in range(6)]
    moving_vehs = [DummyVehicle(10.0, 0.0, 0, route=[lane_n])]
    signals = {
        Direction.NORTH: "red",
        Direction.SOUTH: "green",
        Direction.EAST: "red",
        Direction.WEST: "red",
    }

    # 1. Warmup tick
    collector.update(2.0, waiting_vehs, [], signals)
    assert collector.total_ticks_post_warmup == 0

    # 2. Post-warmup tick with moving vehicles
    collector.update(6.0, moving_vehs, [], signals)
    assert collector.total_ticks_post_warmup == 1
    assert collector.service_ticks == 1

    # 3. Post-warmup tick with queue > 5 and idle loss
    collector.update(7.0, waiting_vehs, [], signals)
    assert collector.total_ticks_post_warmup == 2
    assert collector.congestion_recovery_time > 0
    assert collector.idle_loss_ticks == 1

    # 4. Get metrics with exited vehicle
    v_exit = DummyVehicle(10.0, 2.0, 1, spawn_time=6.0, exit_time=10.0, route=[lane_n])
    metrics = collector.get_metrics(10.0, waiting_vehs, [v_exit], total_spawned=10)
    assert metrics["throughput"] == 1
    assert metrics["idleOpportunityLoss"] > 0
    assert "masterEfficiencyScore" in metrics

    # 5. Get metrics with empty queue history
    collector_empty = MetricCollector(config)
    metrics_empty = collector_empty.get_metrics(0.0, [], [], total_spawned=0)
    assert metrics_empty["maxQueueLength"] == 0
    assert metrics_empty["averageQueueLength"] == 0.0
