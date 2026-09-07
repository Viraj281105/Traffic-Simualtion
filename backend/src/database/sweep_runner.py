import sqlite3
import uuid
from typing import Any, Dict

from src.controllers.fixed_time_signal import FixedTimeSignalController
from src.controllers.roundabout import RoundaboutController
from src.core.clock import Clock
from src.core.engine import SimulationEngine
from src.database.dao import ConfigurationDAO, RunMetricsDAO, SimulationRunDAO
from src.database.db import DB_PATH, init_db
from src.metrics.collector import MetricCollector


def run_volume_sweep() -> Dict[str, Any]:
    """Runs a batch volume sweep across arrival rates 0.1 to 0.7 for signals and roundabouts, storing runs in DB."""
    init_db()

    arrival_rates = [0.1, 0.3, 0.5, 0.7]
    intersection_types = ["fixed_time_signal", "roundabout"]

    results = []

    conn = sqlite3.connect(DB_PATH)
    try:
        for rate in arrival_rates:
            for itype in intersection_types:
                # 1. Generate Config
                config_id = f"cfg_sweep_rate_{rate}_{itype}"
                config: Dict[str, Any] = {
                    "simulation": {
                        "timeStep": 0.1,
                        "duration": 5.0,
                        "warmupTime": 1.0,
                        "randomSeed": 100,
                    },
                    "traffic": {
                        "arrivalRate": rate,
                        "totalVehicles": 50,
                    },
                    "geometry": {
                        "intersectionType": itype,
                        "intersectionCenter": {"x": 0.0, "y": 0.0},
                        "boundingRadius": 15.0,
                    },
                    "controller": {
                        "greenDuration": 30,
                        "yellowDuration": 5,
                        "allRedDuration": 2,
                    },
                    "vehicleGeneration": {
                        "stopSpeedThreshold": 0.1,
                        "waitSpeedThreshold": 0.5,
                    },
                }

                # Save Configuration
                ConfigurationDAO.save(conn, config_id, config)

                # 2. Setup simulation elements
                clock = Clock(time_step=0.1)
                engine = SimulationEngine(clock, duration=5.0, config=config)

                controller: Any
                if itype == "fixed_time_signal":
                    controller = FixedTimeSignalController(config, engine.network)
                else:
                    controller = RoundaboutController(config, engine.network)

                collector = MetricCollector(config)

                def tick_callback() -> None:
                    controller.update(clock.time_step, engine.pool.active_vehicles)
                    collector.update(
                        clock.get_elapsed_time(),
                        engine.pool.active_vehicles,
                        engine.pool.exited_vehicles,
                        {},
                    )

                engine.register_tick_callback(tick_callback)

                # Step 50 ticks (5s)
                run_id = str(uuid.uuid4())
                for _ in range(50):
                    engine.step()

                # Get final metrics
                final_metrics = collector.get_metrics(
                    clock.get_elapsed_time(),
                    engine.pool.active_vehicles,
                    engine.pool.exited_vehicles,
                    engine.spawner.spawned_count if engine.spawner else 0,
                )

                # Save Run and final metrics to DB
                SimulationRunDAO.save(
                    conn,
                    run_id,
                    "completed",
                    clock.get_elapsed_time(),
                    intersection_type=itype,
                    random_seed=100,
                    arrival_rate=rate,
                    duration=5.0,
                    batch_id="sweep_runner",
                    config=config,
                    summary_metrics=final_metrics,
                )
                RunMetricsDAO.save(conn, run_id, 50, final_metrics)

                results.append(
                    {
                        "run_id": run_id,
                        "arrival_rate": rate,
                        "intersection_type": itype,
                        "metrics": final_metrics,
                    }
                )

        conn.commit()
    finally:
        conn.close()

    return {"status": "success", "runs_executed": len(results)}


if __name__ == "__main__":
    res = run_volume_sweep()
    print(f"Sweep run complete: {res}")
