from typing import Any, Dict

from src.controllers.fixed_time_signal import FixedTimeSignalController
from src.core.clock import Clock
from src.core.engine import SimulationEngine
from src.metrics.collector import MetricCollector


def test_full_simulation_run_integration() -> None:
    """Verifies that a simulation engine can run for a series of ticks, update metrics and complete cleanly."""
    config: Dict[str, Any] = {
        "simulation": {
            "timeStep": 0.1,
            "duration": 5.0,  # 5 seconds duration
            "warmupTime": 1.0,
        },
        "geometry": {
            "intersectionType": "fixed_time_signal",
            "intersectionCenter": {"x": 0.0, "y": 0.0},
            "boundingRadius": 15.0,
        },
        "controller": {
            "greenDuration": 10,
            "yellowDuration": 3,
            "allRedDuration": 2,
        },
        "vehicleGeneration": {
            "arrivalRate": 0.2,
            "stopSpeedThreshold": 0.1,
            "waitSpeedThreshold": 0.5,
        },
    }

    clock = Clock(time_step=0.1)
    engine = SimulationEngine(clock, duration=5.0, config=config)
    controller = FixedTimeSignalController(config, engine.network)
    collector = MetricCollector(config)

    # Register callback
    def tick_callback() -> None:
        controller.update(clock.time_step, engine.pool.active_vehicles)
        collector.update(
            clock.get_elapsed_time(),
            engine.pool.active_vehicles,
            engine.pool.exited_vehicles,
            {},
        )

    engine.register_tick_callback(tick_callback)

    # Run for 50 steps (5.0s / 0.1s)
    for _ in range(50):
        engine.step()

    # Verify simulation ended or completed progress
    assert engine.clock.get_tick_count() == 50
    assert engine.clock.get_elapsed_time() >= 5.0

    # Verify metrics collection post warmup
    metrics = collector.get_metrics(
        engine.clock.get_elapsed_time(),
        engine.pool.active_vehicles,
        engine.pool.exited_vehicles,
        engine.spawner.spawned_count if engine.spawner else 0,
        engine.pool.collision_count,
    )
    assert "averageWaitTime" in metrics
    assert "averageTravelSpeed" in metrics
    assert "queueStabilityIndex" in metrics
    assert "spaceFootprintConsumed" in metrics
    assert "intersectionUtilization" in metrics
    assert "criticalSaturationVolume" in metrics
    # End-to-end wiring check: the engine's own pool.collision_count
    # (0 for this uneventful short run) reaches the metrics output exactly,
    # via the same engine.pool.collision_count call-site pattern used by
    # every REST/report/snapshot caller in backend/src/main.py and
    # backend/src/snapshot/builder.py.
    assert metrics["collisionCount"] == engine.pool.collision_count == 0
