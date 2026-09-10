"""Simulation engine — orchestrates the discrete-time traffic simulation.

Creates and owns the :class:`ConflictManager` so that it is available to the
vehicle pool during updates.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from src.core.clock import Clock
from src.core.enums import SimulationStatus
from src.intersection.conflict_manager import ConflictManager
from src.roads.network import RoadNetwork
from src.vehicles.idm import IntelligentDriverModel
from src.vehicles.pool import VehiclePool
from src.vehicles.spawner import VehicleSpawner

logger = logging.getLogger(__name__)


class SimulationEngine:
    """Orchestrates the entire discrete-time traffic simulation lifecycle and execution loop."""

    def __init__(
        self, clock: Clock, duration: float, config: Optional[Dict[str, Any]] = None
    ) -> None:
        if duration <= 0:
            raise ValueError("duration must be greater than zero")

        self.clock: Clock = clock
        self.duration: float = duration
        self.config: Dict[str, Any] = config if config is not None else {}

        self.status: SimulationStatus = SimulationStatus.INITIALIZED

        self._tick_callbacks: List[Callable[[], None]] = []
        self._status_callbacks: List[Callable[[SimulationStatus], None]] = []

        # Setup subsystems if config is provided
        self.network: RoadNetwork = RoadNetwork()
        self.pool: VehiclePool = VehiclePool()
        self.spawner: Optional[VehicleSpawner] = None
        self.idm: Optional[IntelligentDriverModel] = None
        self.conflict_manager: ConflictManager = ConflictManager()
        self.controller: Optional[Any] = None

        if self.config:
            # Setup default network
            road_cfg = self.config.get("roads", {})
            geom_cfg = self.config.get("geometry", {})
            ctrl_cfg = self.config.get("controller", {})
            is_roundabout = geom_cfg.get("intersectionType") == "roundabout"
            inner_radius = ctrl_cfg.get("innerRadius", 10.0)
            outer_radius = ctrl_cfg.get("outerRadius", 20.0)

            self.network.setup_default_intersection(
                approach_length=road_cfg.get("approachLength", 200.0),
                lane_width=road_cfg.get("laneWidth", 3.5),
                lanes_per_approach=road_cfg.get("lanesPerApproach", 2),
                is_roundabout=is_roundabout,
                inner_radius=inner_radius,
                outer_radius=outer_radius,
            )

            # Register all connection lanes with the conflict manager and
            # pre-compute crossing points
            for conn_lane in self.network.get_all_connection_lanes():
                self.conflict_manager.register_connection_lane(conn_lane)
            self.conflict_manager.compute_conflict_points()

            logger.info(
                "ConflictManager initialized: %d connection lanes, %d conflict points",
                len(self.network.get_all_connection_lanes()),
                len(self.conflict_manager.get_all_conflict_points()),
            )

            self.spawner = VehicleSpawner(self.config, self.network)

            veh_gen = self.config.get("vehicleGeneration", {})
            self.idm = IntelligentDriverModel(
                max_acceleration=veh_gen.get("maxAcceleration", 2.0),
                comfort_deceleration=veh_gen.get("comfortDeceleration", 3.0),
                desired_time_headway=veh_gen.get("desiredTimeHeadway", 1.5),
                minimum_gap=veh_gen.get("minimumGap", 2.0),
                idm_delta=veh_gen.get("idmDelta", 4.0),
            )

        self._thread: Optional[threading.Thread] = None
        self._stop_event: threading.Event = threading.Event()
        # RLock (not Lock): step() holds this for its entire body, and tick
        # callbacks invoked from within step() (e.g. SnapshotBuilder.build(),
        # see snapshot/builder.py) re-acquire it on the same thread. A plain
        # Lock would deadlock in that case.
        self._lock: threading.RLock = threading.RLock()

    @property
    def lock(self) -> threading.RLock:
        """Public accessor for the engine's synchronization lock.

        Any code that reads live simulation state (``pool.active_vehicles``,
        ``pool.exited_vehicles``, or anything derived from them) from outside
        the simulation's own background thread — REST handlers, snapshot
        builders, WebSocket loops — must hold this lock for the duration of
        the read. ``step()`` mutates that state while holding the same lock,
        so this guarantees readers only ever see a fully-completed tick, not
        a torn/partially-updated one, and never iterate a list while it is
        being mutated.
        """
        return self._lock

    def register_tick_callback(self, callback: Callable[[], None]) -> None:
        self._tick_callbacks.append(callback)

    def register_status_callback(
        self, callback: Callable[[SimulationStatus], None]
    ) -> None:
        self._status_callbacks.append(callback)

    def _transition_to(self, new_status: SimulationStatus) -> None:
        self.status = new_status
        for cb in self._status_callbacks:
            cb(new_status)

    def start(self) -> None:
        with self._lock:
            if self.status != SimulationStatus.INITIALIZED:
                raise RuntimeError("Cannot start simulation")

            self._transition_to(SimulationStatus.RUNNING)
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            with self._lock:
                status = self.status
                if status != SimulationStatus.RUNNING:
                    break

            start_time = time.time()

            try:
                self.step()
            except Exception:
                logger.exception("Error in simulation step")
                with self._lock:
                    self._transition_to(SimulationStatus.ERROR)
                break

            with self._lock:
                status = self.status
                if status == SimulationStatus.COMPLETED:
                    break

            elapsed = time.time() - start_time
            sleep_time = max(0.0, self.clock.time_step - elapsed)
            time.sleep(sleep_time)

    def pause(self) -> None:
        with self._lock:
            if self.status == SimulationStatus.RUNNING:
                self._transition_to(SimulationStatus.PAUSED)
                self._stop_event.set()

    def resume(self) -> None:
        thread_to_join: Optional[threading.Thread] = None
        with self._lock:
            if self.status != SimulationStatus.PAUSED:
                return
            thread_to_join = self._thread

        if (
            thread_to_join is not None
            and thread_to_join is not threading.current_thread()
        ):
            thread_to_join.join()

        with self._lock:
            if self.status == SimulationStatus.PAUSED:
                self._transition_to(SimulationStatus.RUNNING)
                self._stop_event.clear()
                self._thread = threading.Thread(target=self._run_loop, daemon=True)
                self._thread.start()

    def stop(self) -> None:
        with self._lock:
            if self.status in (SimulationStatus.RUNNING, SimulationStatus.PAUSED):
                self._stop_event.set()
                self._transition_to(SimulationStatus.COMPLETED)

    def reset(self) -> None:
        thread_to_join: Optional[threading.Thread] = None
        with self._lock:
            self._stop_event.set()
            thread_to_join = self._thread

        if (
            thread_to_join is not None
            and thread_to_join is not threading.current_thread()
        ):
            thread_to_join.join()

        with self._lock:
            self.clock.reset()
            if self.spawner is not None:
                self.spawner.reset()
            self.pool.active_vehicles.clear()
            self.pool.exited_vehicles.clear()
            self._transition_to(SimulationStatus.INITIALIZED)

    def step(self) -> None:
        # Holding the lock for the whole tick ensures any concurrent reader
        # (REST handlers, SnapshotBuilder, WebSocket loops — see the `lock`
        # property above) either observes the fully-completed previous tick
        # or waits for this one to finish; it never sees pool.active_vehicles
        # mid-mutation or changing size while being iterated.
        with self._lock:
            if self.status == SimulationStatus.COMPLETED:
                raise RuntimeError("Cannot step simulation in 'completed' status")

            self.clock.tick()

            # Generate new arrivals
            if self.spawner is not None:
                new_vehs = self.spawner.step(self.clock.time_step)
                for v in new_vehs:
                    self.pool.add_vehicle(v)

            # Update controller BEFORE physics update to ensure zero-latency yield/signal response
            controller = getattr(self, "controller", None)
            if controller is not None:
                controller.update(self.clock.time_step, self.pool.active_vehicles)

            # Update spatial states of all vehicles (pool reads conflict_manager from engine)
            self.pool.update(self.clock.time_step, self)

            # Run registered tick callbacks
            for cb in self._tick_callbacks:
                cb()

            # Stop conditions check
            if self.clock.get_elapsed_time() >= self.duration:
                self._transition_to(SimulationStatus.COMPLETED)
