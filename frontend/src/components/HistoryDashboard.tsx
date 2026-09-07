import React, { useEffect, useState } from "react";
import "./HistoryDashboard.css";
import { API_BASE_URL } from "../config";

import { RunningMetrics } from "../types/simulation";

export interface SavedReplay {
  id: string;
  name: string;
  config: {
    simulation?: { duration?: number; randomSeed?: number };
    geometry?: { intersectionType?: string; laneWidth?: number };
    roads?: {
      lanesPerApproach?: {
        north?: number;
        south?: number;
        east?: number;
        west?: number;
      };
    };
    traffic?: { arrivalRate?: number };
  };
  metrics: {
    signal?: RunningMetrics;
    roundabout?: RunningMetrics;
  } & Partial<RunningMetrics>;
  created_at: string;
}

interface HistoryDashboardProps {
  onReplay: (replay: SavedReplay) => void;
}

export const HistoryDashboard: React.FC<HistoryDashboardProps> = ({
  onReplay,
}) => {
  const [replays, setReplays] = useState<SavedReplay[]>([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_BASE_URL}/api/v1/replays`)
      .then((res) => res.json())
      .then((data: SavedReplay[]) => {
        setReplays(data);
        setLoading(false);
      })
      .catch((err: unknown) => {
        console.error("Failed to load replays:", err);
        setLoading(false);
      });
  }, []);

  const confirmDelete = (id: string) => {
    fetch(`${API_BASE_URL}/api/v1/replays/${id}`, {
      method: "DELETE",
    })
      .then((res) => res.json())
      .then((data: { status: string }) => {
        if (data.status === "ok") {
          setReplays((prev) => prev.filter((r) => r.id !== id));
          setDeletingId(null);
        }
      })
      .catch((err: unknown) => {
        console.error("Failed to delete replay:", err);
        setDeletingId(null);
      });
  };

  if (loading) {
    return (
      <div className="history-dashboard">
        <p>Loading history...</p>
      </div>
    );
  }

  if (replays.length === 0) {
    return (
      <div className="history-dashboard empty">
        <p>No saved simulations found.</p>
        <p className="hint">
          Run a simulation and click "Save to History" to see it here.
        </p>
      </div>
    );
  }

  return (
    <div className="history-dashboard">
      <div className="dashboard-header">
        <h3>📚 Saved Simulations</h3>
        <p>Replay past runs deterministically with their exact random seeds.</p>
      </div>
      <table className="history-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Name</th>
            <th>Type</th>
            <th>Seed</th>
            <th>Avg Wait Time (s)</th>
            <th>Throughput</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {replays.map((r) => {
            const date = new Date(r.created_at).toLocaleString();
            const type =
              r.config.geometry?.intersectionType === "roundabout"
                ? "🔄 Roundabout"
                : "🚦 Signal";
            const isDual =
              r.metrics.signal !== undefined &&
              r.metrics.roundabout !== undefined;
            const displayType = isDual ? "📊 Comparative" : type;

            let awt = "—";
            let throughput = "—";
            if (isDual && r.metrics.signal && r.metrics.roundabout) {
              awt = `S: ${r.metrics.signal.averageWaitTime.toFixed(1)} / R: ${r.metrics.roundabout.averageWaitTime.toFixed(1)}`;
              throughput = `S: ${String(r.metrics.signal.throughput)} / R: ${String(r.metrics.roundabout.throughput)}`;
            } else if (r.metrics.averageWaitTime !== undefined) {
              awt = r.metrics.averageWaitTime.toFixed(1);
              throughput = String(r.metrics.throughput ?? 0);
            }

            return (
              <tr key={r.id}>
                <td>{date}</td>
                <td>
                  <strong>{r.name}</strong>
                </td>
                <td>{displayType}</td>
                <td style={{ fontFamily: "monospace" }}>
                  {String(r.config.simulation?.randomSeed)}
                </td>
                <td>{awt}</td>
                <td>{throughput}</td>
                <td>
                  <div style={{ display: "flex", gap: "8px" }}>
                    <button
                      className="pb-btn pb-primary"
                      onClick={() => {
                        onReplay(r);
                      }}
                    >
                      ▶ Replay
                    </button>
                    <button
                      className="pb-btn pb-danger"
                      onClick={() => {
                        setDeletingId(r.id);
                      }}
                    >
                      🗑 Delete
                    </button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {deletingId && (
        <div className="modal-overlay">
          <div className="modal-content">
            <h4>Confirm Deletion</h4>
            <p>
              Are you sure you want to delete this simulation? This action
              cannot be undone.
            </p>
            <div className="modal-actions">
              <button
                className="pb-btn"
                onClick={() => {
                  setDeletingId(null);
                }}
              >
                Cancel
              </button>
              <button
                className="pb-btn pb-danger"
                onClick={() => {
                  confirmDelete(deletingId);
                }}
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
