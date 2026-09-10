import logging
import math
import random
from typing import Any, Dict, List, Optional

from src.core.enums import Direction, TurnIntent
from src.roads.lane import Lane
from src.roads.network import RoadNetwork
from src.vehicles.vehicle import Vehicle

logger = logging.getLogger(__name__)


class VehicleSpawner:
    """Spawns vehicles onto the road network using arrival processes (Poisson or Uniform).

    Lane assignment is turn-intent-aware:
        - 1 lane:  all turns share the lane.
        - 2 lanes: lane 0 = left-turn, lane 1 = straight/right.
        - 3+ lanes: lane 0 = left, middle = straight, last = right.
    """

    def __init__(self, config: Dict[str, Any], network: RoadNetwork) -> None:
        self.config: Dict[str, Any] = config
        self.network: RoadNetwork = network

        traffic_cfg = config.get("traffic", {})
        # setdefault (not get) so that if we generate a fallback seed below,
        # writing it into sim_cfg is visible to every other holder of this
        # same config dict (engine, API handlers, persistence/reproduction
        # code) via config["simulation"]["randomSeed"].
        sim_cfg = config.setdefault("simulation", {})
        veh_gen_cfg = config.get("vehicleGeneration", {})

        self.random_seed: int = sim_cfg.get("randomSeed", veh_gen_cfg.get("seed", None))
        if self.random_seed is None:
            # Never fall back to the shared global `random` module — its
            # state is process-wide and can be perturbed by unrelated code
            # (including other concurrent simulations), which is exactly
            # the kind of silent, hidden non-determinism a "randomSeed"
            # config knob is meant to avoid. Use a private, independently
            # OS-seeded Random instance instead, purely to pick this
            # simulation's own seed.
            self.random_seed = random.Random().randint(1, 10_000_000)
            logger.warning(
                "No simulation.randomSeed configured; generated seed=%d "
                "for this run. Pass randomSeed explicitly for reproducible "
                "runs.",
                self.random_seed,
            )
            # Persist the resolved seed back into the shared config so it
            # can be captured/logged/persisted by callers (e.g. the run
            # history and reproduce endpoints in main.py).
            sim_cfg["randomSeed"] = self.random_seed
        self.rng: random.Random = random.Random(self.random_seed)

        self.total_vehicles_limit: int = traffic_cfg.get("totalVehicles", 200)
        self.arrival_rate: float = traffic_cfg.get(
            "arrivalRate", veh_gen_cfg.get("arrivalRate", 0.5)
        )
        self.arrival_distribution: str = traffic_cfg.get(
            "arrivalDistribution", "poisson"
        )

        if (
            "directionalSplit" in traffic_cfg
            and traffic_cfg["directionalSplit"] is not None
        ):
            self.directional_split: Dict[str, float] = traffic_cfg["directionalSplit"]
        else:
            # Generate stochastic non-uniform weights for the 4 approaches
            raw_weights = [self.rng.uniform(0.5, 2.0) for _ in Direction]
            total_w = sum(raw_weights)
            self.directional_split = {
                d.value: raw_weights[i] / total_w for i, d in enumerate(Direction)
            }

        if (
            "turnProbabilities" in traffic_cfg
            and traffic_cfg["turnProbabilities"] is not None
        ):
            self.turn_probabilities: Dict[str, float] = traffic_cfg["turnProbabilities"]
        else:
            # Realistic randomized turn probabilities with natural variance per run
            p_straight = self.rng.uniform(0.50, 0.70)
            rem = 1.0 - p_straight
            p_left = self.rng.uniform(0.3, 0.7) * rem
            p_right = rem - p_left
            self.turn_probabilities = {
                "left": p_left,
                "straight": p_straight,
                "right": p_right,
            }

        # Vehicle physical parameter bounds
        self.len_min: float = veh_gen_cfg.get("vehicleLength", {}).get("min", 4.0)
        self.len_max: float = veh_gen_cfg.get("vehicleLength", {}).get("max", 5.0)
        self.width_min: float = veh_gen_cfg.get("vehicleWidth", {}).get("min", 1.8)
        self.width_max: float = veh_gen_cfg.get("vehicleWidth", {}).get("max", 2.2)
        self.speed_min: float = veh_gen_cfg.get("desiredSpeed", {}).get("min", 18.0)
        self.speed_max: float = veh_gen_cfg.get("desiredSpeed", {}).get("max", 25.0)

        # Safety distance
        self.minimum_gap: float = veh_gen_cfg.get("minimumGap", 2.0)

        # Speed below which a vehicle is considered "waiting" — must match
        # MetricCollector's wait_speed_threshold so wait-time accounting is
        # consistent between the vehicle and the metrics layer.
        self.wait_speed_threshold: float = veh_gen_cfg.get("waitSpeedThreshold", 0.5)

        # Vehicles spawned count
        self.spawned_count: int = 0

        # Cumulative simulation time — used to set vehicle spawn_time
        self._elapsed_time: float = 0.0

        # Spawn timers for each direction
        self.timers: Dict[Direction, float] = {}
        self.reset()

    def reset(self, new_seed: Optional[int] = None) -> None:
        if new_seed is not None:
            self.random_seed = new_seed
        self.rng = random.Random(self.random_seed)
        self.spawned_count = 0
        self._elapsed_time = 0.0
        self.timers.clear()

        traffic_cfg = self.config.get("traffic", {})
        if (
            "directionalSplit" not in traffic_cfg
            or traffic_cfg.get("directionalSplit") is None
        ):
            raw_weights = [self.rng.uniform(0.5, 2.0) for _ in Direction]
            total_w = sum(raw_weights)
            self.directional_split = {
                d.value: raw_weights[i] / total_w for i, d in enumerate(Direction)
            }
        if (
            "turnProbabilities" not in traffic_cfg
            or traffic_cfg.get("turnProbabilities") is None
        ):
            p_straight = self.rng.uniform(0.50, 0.70)
            rem = 1.0 - p_straight
            p_left = self.rng.uniform(0.3, 0.7) * rem
            p_right = rem - p_left
            self.turn_probabilities = {
                "left": p_left,
                "straight": p_straight,
                "right": p_right,
            }

        for d in Direction:
            self.timers[d] = self._generate_next_arrival_time(d)

    def _generate_next_arrival_time(self, direction: Direction) -> float:
        split = self.directional_split.get(direction.value, 0.25)
        dir_rate = self.arrival_rate * split
        if dir_rate <= 0:
            return float("inf")

        if self.arrival_distribution == "poisson":
            u = self.rng.random()
            # Prevent log(0)
            u = max(1e-9, u)
            return -math.log(u) / dir_rate
        if self.arrival_distribution == "uniform":
            return 1.0 / dir_rate
        if self.arrival_distribution == "burst":
            raise NotImplementedError(
                "arrivalDistribution='burst' is not implemented in VehicleSpawner"
            )
        raise ValueError(
            f"Unsupported arrivalDistribution: {self.arrival_distribution!r}"
        )

    def step(self, dt: float) -> List[Vehicle]:
        """Ticks spawner and returns a list of newly spawned vehicles."""
        self._elapsed_time += dt
        new_vehicles: List[Vehicle] = []

        # Check total vehicle limit
        if self.spawned_count >= self.total_vehicles_limit:
            return new_vehicles

        for d in Direction:
            if self.timers[d] != float("inf"):
                self.timers[d] -= dt
                if self.timers[d] <= 0:
                    # Attempt spawning
                    vehicle = self._attempt_spawn(d)
                    if vehicle is not None:
                        new_vehicles.append(vehicle)
                        self.spawned_count += 1
                        self.timers[d] = self._generate_next_arrival_time(d)
                        if self.spawned_count >= self.total_vehicles_limit:
                            break
                    else:
                        # If blocked, try again next tick
                        self.timers[d] = 0.0

        return new_vehicles

    def _select_lane_for_turn(self, lanes: List[Lane], turn: TurnIntent) -> int:
        """Return the best lane index for the given turn intent.

        Policy (right-hand traffic):
            1 lane  → lane 0 for everything.
            2 lanes → lane 0 = left, lane 1 = straight / right.
            3+ lanes → lane 0 = left, middle lanes = straight, last = right.
        """
        n = len(lanes)
        if n <= 1:
            return 0

        if n == 2:
            if turn == TurnIntent.LEFT:
                return 0
            return 1  # straight or right

        # 3+ lanes
        if turn == TurnIntent.LEFT:
            return 0
        elif turn == TurnIntent.RIGHT:
            return n - 1
        else:
            # Straight → pick a middle lane
            return n // 2

    def _attempt_spawn(self, direction: Direction) -> Optional[Vehicle]:
        incoming_approach = self.network.get_incoming_approach(direction)
        lanes = incoming_approach.get_lanes()
        if not lanes:
            return None

        # Decide Turn Intent first (so we can pick the correct lane)
        turns = [TurnIntent.LEFT, TurnIntent.STRAIGHT, TurnIntent.RIGHT]
        weights = [
            self.turn_probabilities.get("left", 0.2),
            self.turn_probabilities.get("straight", 0.6),
            self.turn_probabilities.get("right", 0.2),
        ]
        turn = self.rng.choices(turns, weights=weights)[0]

        # Select the preferred lane for this turn intent
        preferred_idx = self._select_lane_for_turn(lanes, turn)

        # Try preferred lane first. Turning vehicles must spawn in their designated lane.
        if turn in (TurnIntent.LEFT, TurnIntent.RIGHT):
            ordered_indices = [preferred_idx]
        else:
            ordered_indices = [preferred_idx] + [
                i for i in range(len(lanes)) if i != preferred_idx
            ]

        target_lane: Optional[Lane] = None
        target_idx: int = preferred_idx

        for idx in ordered_indices:
            lane = lanes[idx]
            vehicles = lane.get_vehicles()
            if not vehicles:
                target_lane = lane
                target_idx = idx
                break
            # Find vehicle with the minimum position in the lane
            preceding = min(vehicles, key=lambda v: v.position)
            # Tail of preceding vehicle: preceding.position - preceding.length / 2
            # We need it to be >= minimum_gap + new_vehicle_length
            if (
                preceding.position - preceding.length / 2.0
                >= self.minimum_gap + self.len_max
            ):
                target_lane = lane
                target_idx = idx
                break

        if target_lane is None:
            return None

        # Generate vehicle parameters
        v_len = self.rng.uniform(self.len_min, self.len_max)
        v_width = self.rng.uniform(self.width_min, self.width_max)
        v_desired_speed = self.rng.uniform(self.speed_min, self.speed_max)

        # Generate Route using the selected lane index and turn intent
        route = self.network.generate_route(direction, target_idx, turn)

        # Create Vehicle
        vehicle_id = f"veh_{self.spawned_count}"

        # Vehicle starts at position L/2 so that its rear bumper is at 0.0
        start_pos = v_len / 2.0

        vehicle = Vehicle(
            vehicle_id=vehicle_id,
            length=v_len,
            width=v_width,
            desired_speed=v_desired_speed,
            route=route,
            start_position=start_pos,
            initial_speed=v_desired_speed,  # starts moving at free-flow speed
            turn_intent=turn,
            spawn_time=self._elapsed_time,
            wait_speed_threshold=self.wait_speed_threshold,
        )

        return vehicle
