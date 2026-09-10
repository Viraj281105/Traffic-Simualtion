from datetime import datetime, timezone
from typing import Any, Dict

from src.core.engine import SimulationEngine
from src.core.enums import Direction
from src.metrics.collector import MetricCollector


class SnapshotBuilder:
    """Assembles the complete state snapshot dictionary from the active simulation engine."""

    def __init__(
        self,
        simulation_id: str,
        config_id: str,
        engine: SimulationEngine,
        collector: MetricCollector,
        controller: Any,
    ) -> None:
        self.simulation_id: str = simulation_id
        self.config_id: str = config_id
        self.engine: SimulationEngine = engine
        self.collector: MetricCollector = collector
        self.controller: Any = controller

    def build(self) -> Dict[str, Any]:
        """Assembles a state dictionary conforming to snapshot.schema.json."""
        # Hold the engine's lock for the whole build so this never reads a
        # torn tick or has pool.active_vehicles/exited_vehicles mutated out
        # from under it mid-iteration (see SimulationEngine.lock / .step()).
        # Safe to call both from a REST/WebSocket handler (a different
        # thread acquiring the lock) and from a tick callback running
        # synchronously inside step() itself (RLock allows the reentrant
        # acquisition on that same thread).
        with self.engine.lock:
            return self._build_locked()

    def _build_locked(self) -> Dict[str, Any]:
        clock = self.engine.clock
        elapsed = clock.get_elapsed_time()
        dt = clock.time_step

        # Gather vehicle states
        vehicles_list = []
        counts = {
            "active": len(self.engine.pool.active_vehicles),
            "approaching": 0,
            "waiting": 0,
            "crossing": 0,
            "inRoundabout": 0,
            "exited": len(self.engine.pool.exited_vehicles),
        }

        dir_map = {
            "n": "north",
            "s": "south",
            "e": "east",
            "w": "west",
            "north": "north",
            "south": "south",
            "east": "east",
            "west": "west",
        }
        is_roundabout = getattr(self.engine.network, "is_roundabout", False)

        # Active vehicles
        for v in self.engine.pool.active_vehicles:
            cx, cy = v.coords
            state_str = v.state.value.lower()
            if v.lane and v.lane.lane_id.startswith("conn"):
                state_str = "in_roundabout" if is_roundabout else "crossing"
            elif v.lane and "roundabout" in v.lane.lane_id:
                state_str = "in_roundabout"

            # Increment count
            if state_str == "approaching":
                counts["approaching"] += 1
            elif state_str == "waiting":
                counts["waiting"] += 1
            elif state_str == "crossing":
                counts["crossing"] += 1
            elif state_str == "in_roundabout":
                counts["inRoundabout"] += 1

            # Infer direction and turn intent conforming to schema enum (north, south, east, west)
            direction_str = "north"
            if v.route:
                raw_dir = v.route[0].lane_id.split("_")[0].lower()
                direction_str = dir_map.get(raw_dir, "north")

            # Turn intent
            turn_str = "straight"
            if len(v.route) > 1:
                # We can deduce intent based on route shape, or spawner can set v.turn_intent
                turn_intent = getattr(v, "turn_intent", None)
                if turn_intent is not None:
                    turn_str = turn_intent.value.lower()

            vehicles_list.append(
                {
                    "id": v.vehicle_id,
                    "x": round(cx, 2),
                    "y": round(cy, 2),
                    "speed": round(v.speed, 2),
                    "acceleration": round(v.acceleration, 2),
                    "heading": round(v.heading % 360, 1),
                    "length": round(v.length, 2),
                    "width": round(v.width, 2),
                    "state": state_str,
                    "laneId": v.lane.lane_id if v.lane else "",
                    "direction": direction_str,
                    "turnIntent": turn_str,
                    "waitTime": round(v.wait_time, 2),
                    "stopCount": v.stop_count,
                    "spawnTime": round(getattr(v, "spawn_time", 0.0), 2),
                    "exitTime": None,
                    "distanceTraveled": round(
                        v.position, 2
                    ),  # approximation along route
                }
            )

        # Exited vehicles - serialize up to the most recent 50 to keep payload bounded
        # while snapshot["vehicleCounts"]["exited"] accurately records the full cumulative total
        exited_to_serialize = self.engine.pool.exited_vehicles
        if len(exited_to_serialize) > 50:
            exited_to_serialize = exited_to_serialize[-50:]

        for v in exited_to_serialize:
            direction_str = "north"
            if v.route:
                raw_dir = v.route[0].lane_id.split("_")[0].lower()
                direction_str = dir_map.get(raw_dir, "north")
            turn_str = "straight"
            turn_intent = getattr(v, "turn_intent", None)
            if turn_intent is not None:
                turn_str = turn_intent.value.lower()

            vehicles_list.append(
                {
                    "id": v.vehicle_id,
                    "x": 0.0,
                    "y": 0.0,
                    "speed": 0.0,
                    "acceleration": 0.0,
                    "heading": 0.0,
                    "length": round(v.length, 2),
                    "width": round(v.width, 2),
                    "state": "exited",
                    "laneId": "",
                    "direction": direction_str,
                    "turnIntent": turn_str,
                    "waitTime": round(v.wait_time, 2),
                    "stopCount": v.stop_count,
                    "spawnTime": round(getattr(v, "spawn_time", 0.0), 2),
                    "exitTime": round(getattr(v, "exit_time", elapsed), 2),
                    "distanceTraveled": round(v.position, 2),
                }
            )

        # Assemble intersection info
        geom_type = self.engine.config.get("geometry", {}).get(
            "intersectionType", "fixed_time_signal"
        )
        geom_center = self.engine.config.get("geometry", {}).get(
            "intersectionCenter", {"x": 0.0, "y": 0.0}
        )
        bounding_radius = self.engine.config.get("geometry", {}).get(
            "boundingRadius", 15.0
        )

        metrics_obj = self.collector.get_metrics(
            elapsed,
            self.engine.pool.active_vehicles,
            self.engine.pool.exited_vehicles,
            self.engine.spawner.spawned_count if self.engine.spawner else 0,
        )

        # Map current queues for intersection object
        current_queues = metrics_obj["currentQueueLengths"]
        approaches_list = []
        for d in Direction:
            dir_str = d.value.lower()
            try:
                lane_count = len(
                    self.engine.network.get_incoming_approach(d).get_lanes()
                )
            except KeyError:
                lane_count = 1
            approaches_list.append(
                {
                    "direction": dir_str,
                    "queueLength": current_queues.get(dir_str, 0),
                    "laneCount": lane_count,
                }
            )

        controller_state = self.controller.get_state()

        return {
            "schemaVersion": "1.0.0",
            "simulationId": self.simulation_id,
            "configId": self.config_id,
            "timestamp": round(elapsed, 2),
            "frameNumber": clock.get_tick_count(),
            "tick": clock.get_tick_count(),
            "wallClockTime": datetime.now(timezone.utc).isoformat(),
            "samplingFrequency": round(1.0 / dt, 1) if dt > 0 else 10.0,
            "deltaTime": round(dt, 3),
            "simulationStatus": self.engine.status.value.lower(),
            "vehicles": vehicles_list,
            "intersection": {
                "type": geom_type,
                "centerX": geom_center.get("x", 0.0),
                "centerY": geom_center.get("y", 0.0),
                "boundingRadius": bounding_radius,
                "approaches": approaches_list,
            },
            "controller": controller_state,
            "metrics": metrics_obj,
            "vehicleCounts": counts,
            "units": {
                "distance": "meters",
                "speed": "meters_per_second",
                "acceleration": "meters_per_second_squared",
                "time": "seconds",
                "angle": "degrees",
            },
        }
