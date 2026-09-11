from typing import Any

from src.study.validation import run_invariant_checks, run_statistical_validation


def test_statistical_validation() -> None:
    res = run_statistical_validation(num_seeds=3, duration=4.0, time_step=0.1)

    assert res["numSeeds"] == 3
    assert len(res["seeds"]) == 3
    assert len(res["individualRuns"]) == 3

    # Check that statistics dictionary is properly calculated
    for strategy in ["signal", "roundabout"]:
        assert "delay" in res[strategy]
        assert "throughput" in res[strategy]
        assert "queue" in res[strategy]
        assert "mean" in res[strategy]["delay"]
        assert "std" in res[strategy]["delay"]
        assert "ci95" in res[strategy]["delay"]


def test_invariant_and_repeatability_checks() -> None:
    res = run_invariant_checks(duration=4.0, time_step=0.1, random_seed=4242)

    assert res["valid"] is True
    assert res["isDeterministic"] is True
    assert res["massConservationValid"] is True
    assert res["ticksTested"] == 40
    assert len(res["violations"]) == 0


def test_validation_passes_actual_collision_count_to_metrics(
    monkeypatch: Any,
) -> None:
    """Regression test: verifies that validation.py passes the actual VehiclePool
    collision_count to get_metrics() for both signal and roundabout simulations,
    preventing validation/study comparisons from falsely reporting collisionCount=0."""
    from typing import List, Tuple

    from src.metrics.collector import MetricCollector
    from src.roads.lane import Lane
    from src.snapshot.dual_orchestrator import DualSimulationOrchestrator
    from src.vehicles.vehicle import Vehicle

    captured_metrics: List[Tuple[int, int]] = []
    test_collectors: set[Any] = set()
    orig_get_metrics = MetricCollector.get_metrics

    def spy_get_metrics(self: Any, *args: Any, **kwargs: Any) -> Any:
        res = orig_get_metrics(self, *args, **kwargs)
        if self in test_collectors:
            coll_arg = kwargs.get("collision_count", args[4] if len(args) > 4 else 0)
            captured_metrics.append((coll_arg, res.get("collisionCount", 0)))
        return res

    monkeypatch.setattr(MetricCollector, "get_metrics", spy_get_metrics)

    orig_init = DualSimulationOrchestrator.__init__

    def injected_init(self: Any, *args: Any, **kwargs: Any) -> None:
        orig_init(self, *args, **kwargs)
        test_collectors.add(self.collector_signal)
        test_collectors.add(self.collector_roundabout)
        # Force a deterministic collision in both signal and roundabout pools
        # using the canonical intersecting vehicle pattern from test_pool.py
        lane_a = Lane("lane_a", 0.0, 0.0, 10.0, 0.0)
        lane_b = Lane("lane_b", 5.0, -5.0, 5.0, 5.0)
        va_sig = Vehicle(
            "va_sig", 4.0, 2.0, 5.0, [lane_a], start_position=5.0, initial_speed=5.0
        )
        vb_sig = Vehicle(
            "vb_sig", 4.0, 2.0, 2.0, [lane_b], start_position=5.5, initial_speed=2.0
        )
        va_rnd = Vehicle(
            "va_rnd", 4.0, 2.0, 5.0, [lane_a], start_position=5.0, initial_speed=5.0
        )
        vb_rnd = Vehicle(
            "vb_rnd", 4.0, 2.0, 2.0, [lane_b], start_position=5.5, initial_speed=2.0
        )
        self.engine_signal.pool.add_vehicle(va_sig)
        self.engine_signal.pool.add_vehicle(vb_sig)
        self.engine_roundabout.pool.add_vehicle(va_rnd)
        self.engine_roundabout.pool.add_vehicle(vb_rnd)

    monkeypatch.setattr(DualSimulationOrchestrator, "__init__", injected_init)

    # 1. Test run_statistical_validation (covers both signal and roundabout call sites)
    run_statistical_validation(num_seeds=1, duration=1.0, time_step=0.1)

    assert len(captured_metrics) == 2  # 1 for signal, 1 for roundabout
    for coll_arg, collision_count in captured_metrics:
        assert (
            coll_arg >= 1
        ), f"Expected non-zero collision_count passed, got {coll_arg}"
        assert (
            collision_count >= 1
        ), f"Expected non-zero collisionCount in metrics, got {collision_count}"
        assert coll_arg == collision_count

    # 2. Test run_invariant_checks (covers the two invariant-check call sites)
    captured_metrics.clear()
    run_invariant_checks(duration=1.0, time_step=0.1, random_seed=999)

    assert len(captured_metrics) == 2  # orchestrator1 and orchestrator2
    for coll_arg, collision_count in captured_metrics:
        assert (
            coll_arg >= 1
        ), f"Expected non-zero collision_count passed in invariants, got {coll_arg}"
        assert (
            collision_count >= 1
        ), f"Expected non-zero collisionCount in invariant metrics, got {collision_count}"
        assert coll_arg == collision_count

