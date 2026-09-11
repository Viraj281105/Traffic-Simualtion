import json
import threading
from typing import Any, Dict, List, Optional


class SnapshotBuffer:
    """Manages a rolling history cache of simulation state snapshots.

    ``append()`` is called by the simulation engine's background tick
    thread (see ``controllers/factory.py``'s tick callback, invoked from
    within ``SimulationEngine.step()``); ``get_all()``/``get_frame()`` are
    called by REST history handlers on other threads with no other
    synchronization of their own. The buffer's own ``_lock`` protects its
    internal list from concurrent mutation/iteration across those threads.

    Lock ordering vs. ``SimulationEngine.lock``: ``append()`` always runs
    while the calling thread already holds the engine's lock (``step()``
    holds it for the whole tick, including tick callbacks), so this lock is
    only ever acquired *while already inside* the engine's lock, never the
    other way around — the REST read paths that use this lock never touch
    ``SimulationEngine.lock`` at all. That one-directional nesting order is
    consistent everywhere it happens, so no lock-order inversion/deadlock
    is possible between the two locks.
    """

    def __init__(self, max_frames: int = 1000) -> None:
        self.max_frames: int = max_frames
        self.buffer: List[Dict[str, Any]] = []
        self._lock: threading.RLock = threading.RLock()

    def append(self, snapshot: Dict[str, Any]) -> None:
        """Appends a new snapshot frame. Truncates older frames if capacity is reached."""
        with self._lock:
            self.buffer.append(snapshot)
            if len(self.buffer) > self.max_frames:
                self.buffer.pop(0)

    def get_frame(self, tick: int) -> Optional[Dict[str, Any]]:
        """Retrieves a specific snapshot frame corresponding to the tick count."""
        with self._lock:
            for frame in self.buffer:
                if frame.get("tick") == tick:
                    return frame
            return None

    def clear(self) -> None:
        """Clears the buffer cache."""
        with self._lock:
            self.buffer.clear()

    def get_all(self) -> List[Dict[str, Any]]:
        """Returns all cached frames.

        Returns a shallow copy taken under the lock, not the live internal
        list, so a caller iterating the result can never race a concurrent
        ``append()``/eviction on another thread, and cannot mutate this
        buffer's internal state by mutating the returned list.
        """
        with self._lock:
            return list(self.buffer)

    def export_to_file(self, filepath: str) -> None:
        """Saves the entire run history as a single JSON file."""
        # Snapshot the buffer under the lock, then release it before doing
        # file I/O — the lock must not be held during unrelated, potentially
        # slow work like writing to disk.
        with self._lock:
            snapshot_copy = list(self.buffer)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(snapshot_copy, f, indent=2)
