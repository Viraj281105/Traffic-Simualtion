import json
from typing import Any, Dict

from src.controllers.factory import build_tick_callback, create_controller
from src.core.clock import Clock
from src.core.engine import SimulationEngine
from src.metrics.collector import MetricCollector
from src.snapshot.builder import SnapshotBuilder


class DualSimulationOrchestrator:
    """Orchestrates two parallel simulations (Fixed-Time Signal and Roundabout) in lockstep with matching random seeds."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config

        # Make deep copies of the configuration for both instances
        self.config_signal = json.loads(json.dumps(config))
        self.config_signal["geometry"] = self.config_signal.get("geometry", {})
        self.config_signal["geometry"]["intersectionType"] = "fixed_time_signal"

        self.config_roundabout = json.loads(json.dumps(config))
        self.config_roundabout["geometry"] = self.config_roundabout.get("geometry", {})
        self.config_roundabout["geometry"]["intersectionType"] = "roundabout"

        # ── Inject proper controller configs for each mode ──────────────
        # Signal controller needs signal timing parameters
        self.config_signal["controller"] = self.config_signal.get("controller", {})
        if "straightRightDuration" not in self.config_signal["controller"]:
            self.config_signal["controller"].setdefault("straightRightDuration", 15.0)
            self.config_signal["controller"].setdefault("leftDuration", 5.0)
            self.config_signal["controller"].setdefault("yellowDuration", 3.0)
            self.config_signal["controller"].setdefault("allRedDuration", 2.0)

        # Roundabout controller needs gap-acceptance / geometry parameters
        round_ctrl = config.get("roundaboutController", config.get("controller", {}))
        self.config_roundabout["controller"] = {
            "innerRadius": 10.0,
            "outerRadius": 20.0,
            "circulatingLanes": 1,
            "criticalGap": float(round_ctrl.get("criticalGap", 4.0)),
            "followUpTime": float(round_ctrl.get("followUpTime", 2.5)),
            "entrySpeed": 5.0,
            "circulatingSpeed": 8.0,
        }

        # Propagate random seed to align spawn sequences for fair comparison
        seed = config.get("simulation", {}).get("randomSeed")
        if seed is None:
            import random

            seed = random.randint(1, 10000000)
            if "simulation" not in self.config:
                self.config["simulation"] = {}
            self.config["simulation"]["randomSeed"] = seed

        if "simulation" not in self.config_signal:
            self.config_signal["simulation"] = {}
        if "simulation" not in self.config_roundabout:
            self.config_roundabout["simulation"] = {}
        self.config_signal["simulation"]["randomSeed"] = seed
        self.config_roundabout["simulation"]["randomSeed"] = seed

        # ── Build Signal Simulation ─────────────────────────────────────
        self.clock_signal = Clock(time_step=0.1)
        duration = config.get("simulation", {}).get("duration", 300)
        self.engine_signal = SimulationEngine(
            self.clock_signal, duration=duration, config=self.config_signal
        )
        self.controller_signal = create_controller(
            self.config_signal, self.engine_signal.network
        )

        # CRITICAL: Assign controller to engine so engine.step() calls
        # controller.update() BEFORE vehicle physics (zero-latency response)
        self.engine_signal.controller = self.controller_signal

        self.collector_signal = MetricCollector(self.config_signal)
        self.builder_signal = SnapshotBuilder(
            "dual_signal",
            "dual_cfg",
            self.engine_signal,
            self.collector_signal,
            self.controller_signal,
        )

        self.engine_signal.register_tick_callback(
            build_tick_callback(
                self.controller_signal,
                self.clock_signal,
                self.engine_signal,
                self.collector_signal,
            )
        )

        # ── Build Roundabout Simulation ─────────────────────────────────
        self.clock_roundabout = Clock(time_step=0.1)
        self.engine_roundabout = SimulationEngine(
            self.clock_roundabout, duration=duration, config=self.config_roundabout
        )
        self.controller_roundabout = create_controller(
            self.config_roundabout, self.engine_roundabout.network
        )

        # CRITICAL: Assign controller to engine so engine.step() calls
        # controller.update() BEFORE vehicle physics (zero-latency yield response)
        self.engine_roundabout.controller = self.controller_roundabout

        self.collector_roundabout = MetricCollector(self.config_roundabout)
        self.builder_roundabout = SnapshotBuilder(
            "dual_roundabout",
            "dual_cfg",
            self.engine_roundabout,
            self.collector_roundabout,
            self.controller_roundabout,
        )

        self.engine_roundabout.register_tick_callback(
            build_tick_callback(
                self.controller_roundabout,
                self.clock_roundabout,
                self.engine_roundabout,
                self.collector_roundabout,
            )
        )

    def start(self) -> None:
        self.engine_signal.start()
        self.engine_roundabout.start()

    def resume(self) -> None:
        self.engine_signal.resume()
        self.engine_roundabout.resume()

    def pause(self) -> None:
        self.engine_signal.pause()
        self.engine_roundabout.pause()

    def stop(self) -> None:
        self.engine_signal.stop()
        self.engine_roundabout.stop()

    def get_status(self) -> str:
        return self.engine_signal.status.value.lower()

    def get_dual_snapshot(self) -> Dict[str, Any]:
        return {
            "tick": self.clock_signal.get_tick_count(),
            "elapsed": round(self.clock_signal.get_elapsed_time(), 2),
            "signal": self.builder_signal.build(),
            "roundabout": self.builder_roundabout.build(),
        }
