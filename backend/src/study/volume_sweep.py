import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from src.database.dao import (
    RunMetricsDAO,
    SimulationRunDAO,
    SweepSessionDAO,
)
from src.database.db import DB_PATH, get_db_connection, init_db  # noqa: F401
from src.snapshot.dual_orchestrator import DualSimulationOrchestrator

logger = logging.getLogger(__name__)

DEFAULT_ARRIVAL_RATES = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]


def run_volume_sweep_experiment(
    arrival_rates: Optional[List[float]] = None,
    duration: float = 60.0,
    time_step: float = 0.1,
    random_seed: int = 42,
    custom_config: Optional[Dict[str, Any]] = None,
    name: str = "Comparative Volume Sweep",
) -> Dict[str, Any]:
    """
    Executes an automated multi-volume parameter sweep comparing Fixed-Time Signals
    and Modern Roundabouts across specified vehicle arrival rates under identical seeds.
    """
    init_db()

    rates = (
        arrival_rates
        if arrival_rates and len(arrival_rates) > 0
        else DEFAULT_ARRIVAL_RATES
    )
    session_id = str(uuid.uuid4())

    base_config: Dict[str, Any] = {
        "simulation": {
            "timeStep": time_step,
            "duration": duration,
            "warmupTime": 15.0,
            "randomSeed": random_seed,
        },
        "roads": {
            "approachLength": 200.0,
            "laneWidth": 3.5,
            "lanesPerApproach": {
                "north": 2,
                "south": 2,
                "east": 2,
                "west": 2,
            },
        },
        "traffic": {
            "arrivalRate": 0.3,
            "arrivalDistribution": "poisson",
        },
        "vehicleGeneration": {
            "stopSpeedThreshold": 0.1,
            "waitSpeedThreshold": 0.5,
            "maxAcceleration": 3.0,
            "comfortDeceleration": 3.5,
            "desiredSpeed": {
                "min": 18.0,
                "max": 25.0,
            },
        },
    }

    if custom_config:
        # Merge custom configs
        for k, v in custom_config.items():
            if isinstance(v, dict) and k in base_config:
                base_config[k].update(v)
            else:
                base_config[k] = v

    steps_to_run = int(duration / time_step)
    runs_data: List[Dict[str, Any]] = []

    signal_delays: List[float] = []
    roundabout_delays: List[float] = []
    signal_delay_stds: List[float] = []
    roundabout_delay_stds: List[float] = []
    signal_delay_mins: List[float] = []
    roundabout_delay_mins: List[float] = []
    signal_delay_maxs: List[float] = []
    roundabout_delay_maxs: List[float] = []
    signal_throughputs: List[float] = []
    roundabout_throughputs: List[float] = []
    signal_queues: List[float] = []
    roundabout_queues: List[float] = []
    signal_queue_stds: List[float] = []
    roundabout_queue_stds: List[float] = []
    signal_queue_maxs: List[float] = []
    roundabout_queue_maxs: List[float] = []

    crossover_rate: Optional[float] = None

    with get_db_connection() as conn:
        for rate in rates:
            step_config = json.loads(json.dumps(base_config))
            step_config["traffic"]["arrivalRate"] = rate
            step_config["simulation"]["randomSeed"] = random_seed

            orchestrator = DualSimulationOrchestrator(step_config)

            # Fast headless simulation execution
            for _ in range(steps_to_run):
                orchestrator.engine_signal.step()
                orchestrator.engine_roundabout.step()

            # Collect metrics
            elapsed_sig = orchestrator.clock_signal.get_elapsed_time()
            sig_metrics = orchestrator.collector_signal.get_metrics(
                elapsed_sig,
                orchestrator.engine_signal.pool.active_vehicles,
                orchestrator.engine_signal.pool.exited_vehicles,
                orchestrator.engine_signal.spawner.spawned_count
                if orchestrator.engine_signal.spawner
                else 0,
            )

            elapsed_round = orchestrator.clock_roundabout.get_elapsed_time()
            round_metrics = orchestrator.collector_roundabout.get_metrics(
                elapsed_round,
                orchestrator.engine_roundabout.pool.active_vehicles,
                orchestrator.engine_roundabout.pool.exited_vehicles,
                orchestrator.engine_roundabout.spawner.spawned_count
                if orchestrator.engine_roundabout.spawner
                else 0,
            )

            sig_delay = round(
                sig_metrics.get(
                    "averageDelay", sig_metrics.get("averageWaitTime", 0.0)
                ),
                2,
            )
            round_delay = round(
                round_metrics.get(
                    "averageDelay", round_metrics.get("averageWaitTime", 0.0)
                ),
                2,
            )
            sig_delay_std = round(sig_metrics.get("delayStdDev", 0.0), 2)
            round_delay_std = round(round_metrics.get("delayStdDev", 0.0), 2)
            sig_delay_min = round(sig_metrics.get("minDelay", 0.0), 2)
            round_delay_min = round(round_metrics.get("minDelay", 0.0), 2)
            sig_delay_max = round(sig_metrics.get("maxDelay", sig_delay), 2)
            round_delay_max = round(round_metrics.get("maxDelay", round_delay), 2)
            sig_delay_med = round(sig_metrics.get("medianDelay", sig_delay), 2)
            round_delay_med = round(round_metrics.get("medianDelay", round_delay), 2)
            sig_delay_p95 = round(sig_metrics.get("p95Delay", sig_delay), 2)
            round_delay_p95 = round(round_metrics.get("p95Delay", round_delay), 2)

            sig_tp = round(sig_metrics.get("throughput", 0.0), 1)
            round_tp = round(round_metrics.get("throughput", 0.0), 1)
            sig_tp_rate = round(sig_metrics.get("throughputRate", 0.0), 2)
            round_tp_rate = round(round_metrics.get("throughputRate", 0.0), 2)

            sig_q = round(sig_metrics.get("averageQueueLength", 0.0), 1)
            round_q = round(round_metrics.get("averageQueueLength", 0.0), 1)
            sig_q_max = round(sig_metrics.get("maxQueueLength", sig_q), 1)
            round_q_max = round(round_metrics.get("maxQueueLength", round_q), 1)
            sig_q_std = round(sig_metrics.get("queueStdDev", 0.0), 2)
            round_q_std = round(round_metrics.get("queueStdDev", 0.0), 2)

            signal_delays.append(sig_delay)
            roundabout_delays.append(round_delay)
            signal_delay_stds.append(sig_delay_std)
            roundabout_delay_stds.append(round_delay_std)
            signal_delay_mins.append(sig_delay_min)
            roundabout_delay_mins.append(round_delay_min)
            signal_delay_maxs.append(sig_delay_max)
            roundabout_delay_maxs.append(round_delay_max)

            signal_throughputs.append(sig_tp)
            roundabout_throughputs.append(round_tp)
            signal_queues.append(sig_q)
            roundabout_queues.append(round_q)
            signal_queue_stds.append(sig_q_std)
            roundabout_queue_stds.append(round_q_std)
            signal_queue_maxs.append(sig_q_max)
            roundabout_queue_maxs.append(round_q_max)

            # Detect crossover objectively when delay advantage inverts
            if crossover_rate is None and len(roundabout_delays) > 1:
                prev_diff = roundabout_delays[-2] - signal_delays[-2]
                curr_diff = round_delay - sig_delay
                if (prev_diff < 0 and curr_diff > 0) or (
                    prev_diff > 0 and curr_diff < 0
                ):
                    crossover_rate = rate

            # Save to database
            sig_run_id = f"sweep_{session_id[:8]}_sig_{int(rate * 100)}"
            round_run_id = f"sweep_{session_id[:8]}_rnd_{int(rate * 100)}"

            sig_config = json.loads(json.dumps(step_config))
            sig_config["geometry"] = {"intersectionType": "fixed_time_signal"}
            round_config = json.loads(json.dumps(step_config))
            round_config["geometry"] = {"intersectionType": "roundabout"}

            SimulationRunDAO.save(
                conn,
                sig_run_id,
                "completed",
                elapsed_sig,
                intersection_type="fixed_time_signal",
                random_seed=random_seed,
                arrival_rate=rate,
                duration=duration,
                batch_id=session_id,
                config=sig_config,
                summary_metrics=sig_metrics,
            )
            RunMetricsDAO.save(conn, sig_run_id, steps_to_run, sig_metrics)

            SimulationRunDAO.save(
                conn,
                round_run_id,
                "completed",
                elapsed_round,
                intersection_type="roundabout",
                random_seed=random_seed,
                arrival_rate=rate,
                duration=duration,
                batch_id=session_id,
                config=round_config,
                summary_metrics=round_metrics,
            )
            RunMetricsDAO.save(conn, round_run_id, steps_to_run, round_metrics)

            # Objective winner and symmetric delta calculations
            delay_diff = round_delay - sig_delay
            delay_delta_pct = (
                round(((round_delay - sig_delay) / max(sig_delay, 0.01)) * 100, 1)
                if sig_delay > 0
                else 0.0
            )
            tp_delta_pct = (
                round(((round_tp - sig_tp) / max(sig_tp, 1.0)) * 100, 1)
                if sig_tp > 0
                else 0.0
            )
            queue_delta_pct = (
                round(((round_q - sig_q) / max(sig_q, 0.1)) * 100, 1)
                if sig_q > 0
                else 0.0
            )

            # Objective parity tolerance: difference <= 0.2s or < 2% is a statistical tie
            if abs(delay_diff) <= 0.2 or abs(delay_delta_pct) < 2.0:
                winner = "tie"
            elif round_delay < sig_delay:
                winner = "roundabout"
            else:
                winner = "signal"

            runs_data.append(
                {
                    "arrivalRate": rate,
                    "hourlyVolumeVehPerHour": int(
                        rate * 3600 * 4
                    ),  # 4 approaches total
                    "signal": {
                        "runId": sig_run_id,
                        "delay": sig_delay,
                        "delayMedian": sig_delay_med,
                        "delayStdDev": sig_delay_std,
                        "delayMin": sig_delay_min,
                        "delayMax": sig_delay_max,
                        "delayP95": sig_delay_p95,
                        "throughput": sig_tp,
                        "throughputRate": sig_tp_rate,
                        "queue": sig_q,
                        "queueMax": sig_q_max,
                        "queueStdDev": sig_q_std,
                        "metrics": sig_metrics,
                    },
                    "roundabout": {
                        "runId": round_run_id,
                        "delay": round_delay,
                        "delayMedian": round_delay_med,
                        "delayStdDev": round_delay_std,
                        "delayMin": round_delay_min,
                        "delayMax": round_delay_max,
                        "delayP95": round_delay_p95,
                        "throughput": round_tp,
                        "throughputRate": round_tp_rate,
                        "queue": round_q,
                        "queueMax": round_q_max,
                        "queueStdDev": round_q_std,
                        "metrics": round_metrics,
                    },
                    "winner": winner,
                    "delayDeltaPercent": delay_delta_pct,
                    "throughputDeltaPercent": tp_delta_pct,
                    "queueDeltaPercent": queue_delta_pct,
                }
            )

        summary_curves = {
            "rates": rates,
            "volumesVehPerHour": [int(r * 3600 * 4) for r in rates],
            "signal": {
                "delays": signal_delays,
                "delayStds": signal_delay_stds,
                "delayMins": signal_delay_mins,
                "delayMaxs": signal_delay_maxs,
                "throughputs": signal_throughputs,
                "queues": signal_queues,
                "queueStds": signal_queue_stds,
                "queueMaxs": signal_queue_maxs,
            },
            "roundabout": {
                "delays": roundabout_delays,
                "delayStds": roundabout_delay_stds,
                "delayMins": roundabout_delay_mins,
                "delayMaxs": roundabout_delay_maxs,
                "throughputs": roundabout_throughputs,
                "queues": roundabout_queues,
                "queueStds": roundabout_queue_stds,
                "queueMaxs": roundabout_queue_maxs,
            },
            "crossoverArrivalRate": crossover_rate,
            "crossoverHourlyVolume": int(crossover_rate * 3600 * 4)
            if crossover_rate
            else None,
        }

        sweep_result = {
            "sessionId": session_id,
            "name": name,
            "duration": duration,
            "randomSeed": random_seed,
            "curves": summary_curves,
            "runs": runs_data,
        }

        # Persist session in DB
        SweepSessionDAO.save(conn, session_id, name, base_config, sweep_result)
        conn.commit()

    return sweep_result
