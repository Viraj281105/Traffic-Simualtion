import json
import queue
import threading

from src.controllers.factory import build_tick_callback
from src.controllers.fixed_time_signal import FixedTimeSignalController
from src.core.clock import Clock
from src.core.engine import SimulationEngine
from src.core.enums import TurnIntent, VehicleState
from src.metrics.collector import MetricCollector
from src.roads.lane import Lane
from src.snapshot.buffer import SnapshotBuffer
from src.snapshot.builder import SnapshotBuilder
from src.snapshot.dual_orchestrator import DualSimulationOrchestrator
from src.vehicles.vehicle import Vehicle


def test_snapshot_buffer(tmp_path) -> None:
    buf = SnapshotBuffer(max_frames=2)
    assert buf.get_all() == []

    buf.append({"tick": 1, "data": "f1"})
    buf.append({"tick": 2, "data": "f2"})
    assert len(buf.get_all()) == 2

    # Overflow capacity
    buf.append({"tick": 3, "data": "f3"})
    assert len(buf.get_all()) == 2
    assert buf.get_frame(1) is None
    assert buf.get_frame(2) == {"tick": 2, "data": "f2"}

    # Export to file
    out_file = str(tmp_path / "snapshots.json")
    buf.export_to_file(out_file)
    with open(out_file, "r", encoding="utf-8") as f:
        loaded = json.load(f)
    assert len(loaded) == 2

    # Clear
    buf.clear()
    assert len(buf.get_all()) == 0


def test_snapshot_buffer_get_all_returns_isolated_snapshot() -> None:
    """get_all() must return a copy, not the live internal list: mutating
    the returned list must never corrupt the buffer's own state, and a
    snapshot taken before further appends must not grow after the fact."""
    buf = SnapshotBuffer(max_frames=10)
    buf.append({"tick": 1})
    buf.append({"tick": 2})

    snapshot = buf.get_all()
    assert snapshot is not buf.buffer
    assert len(snapshot) == 2

    # Mutating the returned list must not affect the buffer.
    snapshot.append({"tick": 999})
    snapshot.clear()
    assert len(buf.get_all()) == 2

    # A snapshot taken before more appends must stay frozen at its own
    # length -- it is not a live view onto the buffer.
    frozen_snapshot = buf.get_all()
    buf.append({"tick": 3})
    buf.append({"tick": 4})
    assert len(frozen_snapshot) == 2
    assert len(buf.get_all()) == 4


def test_snapshot_buffer_concurrent_append_and_read_no_corruption() -> None:
    """Concurrent writer threads (simulating the engine's tick thread
    appending) and reader threads (simulating REST history handlers
    calling get_all()/get_frame() with no synchronization of their own)
    must never corrupt the buffer's internal list or raise -- and the
    existing capacity/uniqueness semantics must still hold once every
    thread has finished."""
    max_frames = 200
    buf = SnapshotBuffer(max_frames=max_frames)
    num_writer_threads = 8
    appends_per_writer = 100
    num_reader_threads = 8
    reads_per_reader = 200

    errors: "queue.Queue[BaseException]" = queue.Queue()

    def writer(writer_id: int) -> None:
        try:
            for seq in range(appends_per_writer):
                # Globally unique tick per (writer, seq) pair so post-hoc
                # duplicate detection actually proves no frame was
                # corrupted/duplicated by a racing append.
                buf.append({"tick": writer_id * appends_per_writer + seq})
        except BaseException as exc:  # noqa: BLE001 - must capture every failure mode
            errors.put(exc)

    def reader() -> None:
        try:
            for i in range(reads_per_reader):
                frames = buf.get_all()
                # Iterating the returned list must never explode even
                # while writers are actively appending/evicting.
                for frame in frames:
                    assert "tick" in frame
                buf.get_frame(i)
        except BaseException as exc:  # noqa: BLE001 - must capture every failure mode
            errors.put(exc)

    threads = [
        threading.Thread(target=writer, args=(i,)) for i in range(num_writer_threads)
    ] + [threading.Thread(target=reader) for _ in range(num_reader_threads)]

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    assert not any(t.is_alive() for t in threads), "a thread failed to finish (deadlock?)"
    if not errors.empty():
        raise errors.get()

    # Capacity semantics preserved: never grew past max_frames despite
    # num_writer_threads * appends_per_writer (800) total appends.
    final = buf.get_all()
    assert len(final) == max_frames

    # No duplicated/corrupted entries: every surviving frame's tick is
    # unique (append()/pop(0) under the lock cannot have interleaved into
    # a torn read-modify-write).
    ticks = [frame["tick"] for frame in final]
    assert len(ticks) == len(set(ticks))


def test_snapshot_buffer_no_deadlock_with_real_engine_tick_pattern() -> None:
    """Reproduces the actual production access pattern: the engine's
    background tick thread calls buffer.append() from inside step() while
    already holding engine.lock (see build_tick_callback/factory.py), and
    a separate thread repeatedly calls get_all()/get_frame() the way REST
    history handlers do, holding no lock at all. Neither side must ever
    block on the other."""
    config = {
        "simulation": {"warmupTime": 0.0, "timeStep": 0.01},
        "geometry": {"intersectionType": "fixed_time_signal"},
        "roads": {"approachLength": 100.0, "laneWidth": 3.5, "lanesPerApproach": 2},
    }
    clock = Clock(0.01)
    # Long duration relative to the read loop below, so the engine is
    # still ticking/appending for the whole read phase rather than
    # finishing before it starts.
    engine = SimulationEngine(clock, duration=100.0, config=config)
    collector = MetricCollector(config)
    controller = FixedTimeSignalController(config, engine.network)
    builder = SnapshotBuilder("sim_concurrency", "cfg_concurrency", engine, collector, controller)
    buffer = SnapshotBuffer(max_frames=50)

    engine.register_tick_callback(
        build_tick_callback(controller, clock, engine, collector, buffer, builder)
    )

    errors: "queue.Queue[BaseException]" = queue.Queue()

    def reader() -> None:
        try:
            for i in range(500):
                buffer.get_all()
                buffer.get_frame(i)
        except BaseException as exc:  # noqa: BLE001 - must capture every failure mode
            errors.put(exc)

    engine.start()
    reader_thread = threading.Thread(target=reader)
    reader_thread.start()
    reader_thread.join(timeout=10.0)
    assert not reader_thread.is_alive(), "reader thread deadlocked against the engine"

    engine.stop()
    if engine._thread is not None:
        engine._thread.join(timeout=5.0)
        assert not engine._thread.is_alive(), "engine thread failed to stop (deadlock?)"

    if not errors.empty():
        raise errors.get()

    # The engine was genuinely ticking (and appending) throughout the read
    # loop, not merely idle -- otherwise this test would prove nothing.
    assert len(buffer.get_all()) > 0


def test_snapshot_builder_active_and_exited_vehicles() -> None:
    config = {
        "simulation": {"warmupTime": 5.0, "timeStep": 0.1},
        "geometry": {
            "intersectionType": "fixed_time_signal",
            "intersectionCenter": {"x": 0.0, "y": 0.0},
        },
        "roads": {"approachLength": 100.0, "laneWidth": 3.5, "lanesPerApproach": 2},
    }
    clock = Clock(0.1)
    engine = SimulationEngine(clock, duration=10.0, config=config)
    collector = MetricCollector(config)
    controller = FixedTimeSignalController(config, engine.network)
    builder = SnapshotBuilder("sim_1", "cfg_1", engine, collector, controller)

    lane_conn = Lane("conn_north_0_straight", 0.0, 10.0, 0.0, -10.0)
    lane_round = Lane("roundabout_circ", 0.0, 10.0, 10.0, 0.0)
    lane_in = Lane("north_in_0", 0.0, 100.0, 0.0, 10.0)

    # 1. Crossing vehicle on conn lane
    v_crossing = Vehicle(
        "v_cross",
        4.0,
        2.0,
        10.0,
        route=[lane_in, lane_conn],
        start_position=5.0,
        initial_speed=10.0,
        turn_intent=TurnIntent.STRAIGHT,
    )
    v_crossing.lane = lane_conn

    # 2. In-roundabout vehicle
    v_round = Vehicle(
        "v_round",
        4.0,
        2.0,
        10.0,
        route=[lane_round],
        start_position=5.0,
        initial_speed=8.0,
        turn_intent=TurnIntent.LEFT,
    )

    # 3. Approaching & waiting vehicles
    v_app = Vehicle(
        "v_app",
        4.0,
        2.0,
        10.0,
        route=[lane_in],
        start_position=5.0,
        initial_speed=10.0,
        turn_intent=TurnIntent.RIGHT,
    )
    v_wait = Vehicle(
        "v_wait",
        4.0,
        2.0,
        10.0,
        route=[lane_in],
        start_position=50.0,
        initial_speed=0.0,
        turn_intent=TurnIntent.STRAIGHT,
    )
    v_wait.state = VehicleState.WAITING

    engine.pool.active_vehicles.extend([v_crossing, v_round, v_app, v_wait])

    # 4. Exited vehicle
    v_exit = Vehicle(
        "v_exit",
        4.0,
        2.0,
        10.0,
        route=[lane_in],
        start_position=100.0,
        initial_speed=10.0,
        turn_intent=TurnIntent.STRAIGHT,
    )
    v_exit.state = VehicleState.EXITED
    v_exit.exit_time = 8.5
    engine.pool.exited_vehicles.append(v_exit)

    snapshot = builder.build()
    assert snapshot["schemaVersion"] == "1.0.0"
    assert snapshot["vehicleCounts"]["active"] == 4
    assert snapshot["vehicleCounts"]["exited"] == 1
    assert len(snapshot["vehicles"]) == 5

    # Test KeyError on missing approach in network
    empty_engine = SimulationEngine(clock, duration=10.0)
    builder_empty = SnapshotBuilder(
        "sim_empty", "cfg_empty", empty_engine, collector, controller
    )
    snap_empty = builder_empty.build()
    assert len(snap_empty["intersection"]["approaches"]) == 4


def test_dual_simulation_orchestrator() -> None:
    config = {
        "roads": {"approachLength": 100.0, "laneWidth": 3.5, "lanesPerApproach": 2},
        "traffic": {"arrivalRate": 2.0},
    }
    orchestrator = DualSimulationOrchestrator(config)
    assert orchestrator.get_status() == "initialized"

    # Step engines to invoke tick callbacks
    orchestrator.engine_signal.step()
    orchestrator.engine_roundabout.step()

    orchestrator.start()
    assert orchestrator.get_status() == "running"

    orchestrator.pause()
    assert orchestrator.get_status() == "paused"

    orchestrator.stop()
    assert orchestrator.get_status() == "completed"

    snap = orchestrator.get_dual_snapshot()
    assert "signal" in snap
    assert "roundabout" in snap
