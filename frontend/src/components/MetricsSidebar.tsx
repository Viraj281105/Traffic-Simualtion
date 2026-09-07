import React from "react";
import type {
  LiveSnapshot,
  DualSnapshot,
  SignalDirection,
} from "../types/simulation";
import type { ConnectionStatus } from "../services/websocket";

interface MetricsSidebarProps {
  snapshot: LiveSnapshot | DualSnapshot | null;
  connectionStatus: ConnectionStatus;
  hideHeader?: boolean;
}

const DIRECTIONS: SignalDirection[] = ["north", "south", "east", "west"];
const DIR_LABEL: Record<SignalDirection, string> = {
  north: "N",
  south: "S",
  east: "E",
  west: "W",
};

function fmt(val: number | null | undefined, decimals = 1): string {
  if (
    val === undefined ||
    val === null ||
    Number.isNaN(val) ||
    !Number.isFinite(val)
  ) {
    return "—";
  }
  return val.toFixed(decimals);
}

function metricColor(value: number, low: number, high: number): string {
  if (value <= low) return "#2ecc40";
  if (value >= high) return "#ff4136";
  return "#ffdc00";
}

const CONNECTION_LABELS: Record<
  ConnectionStatus,
  { label: string; color: string }
> = {
  connected: { label: "● LIVE", color: "#2ecc40" },
  connecting: { label: "◌ CONNECTING", color: "#ffdc00" },
  reconnecting: { label: "↻ RECONNECTING", color: "#ff922b" },
  disconnected: { label: "○ OFFLINE", color: "#888" },
  error: { label: "✕ ERROR", color: "#ff4136" },
};

export const MetricsSidebar: React.FC<MetricsSidebarProps> = ({
  snapshot,
  connectionStatus,
  hideHeader = false,
}) => {
  const conn = CONNECTION_LABELS[connectionStatus];

  // Determine if this is a dual comparison snapshot
  const isDual =
    snapshot !== null && "signal" in snapshot && "roundabout" in snapshot;
  const signalSnap = isDual ? snapshot.signal : snapshot;
  const roundaboutSnap = isDual ? snapshot.roundabout : null;

  const m = signalSnap ? signalSnap.metrics : undefined;
  const mr = roundaboutSnap ? roundaboutSnap.metrics : undefined;

  const vc = signalSnap ? signalSnap.vehicleCounts : undefined;
  const vcr = roundaboutSnap ? roundaboutSnap.vehicleCounts : undefined;

  const maxQ = Math.max(
    ...DIRECTIONS.map((d) =>
      Math.max(
        (m?.currentQueueLengths && m.currentQueueLengths[d]) ?? 0,
        (mr?.currentQueueLengths && mr.currentQueueLengths[d]) ?? 0,
      ),
    ),
    1,
  );

  // Helper to compare metrics (true if A is better than B)
  const compareBetter = (valA: number, valB: number, lowerIsBetter = true) => {
    if (valA === valB) return null;
    return lowerIsBetter
      ? valA < valB
        ? "sig"
        : "round"
      : valA > valB
        ? "sig"
        : "round";
  };

  const handleDownloadReport = () => {
    if (isDual && m && mr) {
      let csv = "Metric Name,Fixed-Time Signal,Roundabout,Winner,Delta (%)\n";
      const addRow = (
        label: string,
        valA: number,
        valB: number,
        lowerIsBetter = true,
      ) => {
        const winner =
          valA === valB
            ? "Tie"
            : lowerIsBetter
              ? valA < valB
                ? "Signal"
                : "Roundabout"
              : valA > valB
                ? "Signal"
                : "Roundabout";
        const delta = valA === 0 ? 0 : ((valB - valA) / valA) * 100;
        csv += `"${label}",${valA.toFixed(2)},${valB.toFixed(2)},${winner},${delta.toFixed(1)}%\n`;
      };
      addRow("Average Wait Time", m.averageWaitTime, mr.averageWaitTime, true);
      addRow("Throughput", m.throughput, mr.throughput, false);
      addRow("Throughput Rate", m.throughputRate, mr.throughputRate, false);
      addRow(
        "Average Travel Speed",
        m.averageTravelSpeed,
        mr.averageTravelSpeed,
        false,
      );
      addRow(
        "Intersection Utilization",
        m.intersectionUtilization,
        mr.intersectionUtilization,
        false,
      );
      addRow("Max Queue Length", m.maxQueueLength, mr.maxQueueLength, true);
      addRow(
        "Average Queue Length",
        m.averageQueueLength,
        mr.averageQueueLength,
        true,
      );
      addRow(
        "Queue Stability Index",
        m.queueStabilityIndex,
        mr.queueStabilityIndex,
        true,
      );
      addRow(
        "Congestion Recovery Time",
        m.congestionRecoveryTime,
        mr.congestionRecoveryTime,
        true,
      );
      addRow("Total Stops", m.totalStops, mr.totalStops, true);
      addRow(
        "Average Stops per Vehicle",
        m.averageStopsPerVehicle,
        mr.averageStopsPerVehicle,
        true,
      );
      addRow(
        "Speed Variance Index",
        m.speedVarianceIndex,
        mr.speedVarianceIndex,
        true,
      );
      addRow(
        "Travel Time Reliability",
        m.travelTimeReliability,
        mr.travelTimeReliability,
        true,
      );
      addRow(
        "Directional Fairness",
        m.directionalFairnessIndex,
        mr.directionalFairnessIndex,
        false,
      );
      addRow(
        "Idle Opportunity Loss",
        m.idleOpportunityLoss,
        mr.idleOpportunityLoss,
        true,
      );
      addRow(
        "Land Footprint Area (m²)",
        m.spaceFootprintConsumed,
        mr.spaceFootprintConsumed,
        true,
      );

      const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.setAttribute("href", url);
      link.setAttribute(
        "download",
        `comparative_report_${Date.now().toString()}.csv`,
      );
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } else if (snapshot && m) {
      let csv = "Metric Name,Value\n";
      const addRow = (label: string, val: number | undefined) => {
        csv += `"${label}",${val !== undefined ? val.toFixed(2) : "—"}\n`;
      };

      addRow("Average Wait Time", m.averageWaitTime);
      addRow("Throughput", m.throughput);
      addRow("Throughput Rate", m.throughputRate);
      addRow("Average Travel Speed", m.averageTravelSpeed);
      addRow("Intersection Utilization", m.intersectionUtilization);
      addRow("Max Queue Length", m.maxQueueLength);
      addRow("Average Queue Length", m.averageQueueLength);
      addRow("Queue Stability Index", m.queueStabilityIndex);
      addRow("Congestion Recovery Time", m.congestionRecoveryTime);
      addRow("Total Stops", m.totalStops);
      addRow("Average Stops per Vehicle", m.averageStopsPerVehicle);
      addRow("Speed Variance Index", m.speedVarianceIndex);
      addRow("Travel Time Reliability", m.travelTimeReliability);
      addRow("Directional Fairness Index", m.directionalFairnessIndex);
      addRow("Idle Opportunity Loss", m.idleOpportunityLoss);
      addRow("Land Footprint Area (m²)", m.spaceFootprintConsumed);
      addRow("Total Vehicles Spawned", m.totalVehiclesSpawned);

      const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.setAttribute("href", url);
      link.setAttribute(
        "download",
        `single_report_${Date.now().toString()}.csv`,
      );
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }
  };

  return (
    <aside
      className="metrics-sidebar"
      style={hideHeader ? { width: "100%", borderLeft: "none" } : undefined}
    >
      {/* Header */}
      {!hideHeader && (
        <div className="sidebar-header">
          <h2 className="sidebar-title">Live Metrics</h2>
          <span className="conn-badge" style={{ color: conn.color }}>
            {conn.label}
          </span>
        </div>
      )}

      {/* Controller type */}
      {snapshot && !isDual && (
        <div className="controller-chip">
          {snapshot.controller.type === "fixed_time_signal"
            ? "🚦 Fixed-Time Signal"
            : "🔄 Roundabout"}
        </div>
      )}

      {/* Overall Comparison winner */}
      {isDual && m && mr && (
        <div
          className="sidebar-section"
          style={{ background: "rgba(77, 150, 255, 0.05)" }}
        >
          <h3 className="section-title">Master Evaluation</h3>
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "6px",
              marginTop: "4px",
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                fontSize: "12px",
              }}
            >
              <span>Signal Efficiency:</span>
              <span style={{ fontWeight: "bold" }}>
                {fmt(m.masterEfficiencyScore ?? 70)}%
              </span>
            </div>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                fontSize: "12px",
              }}
            >
              <span>Roundabout Efficiency:</span>
              <span style={{ fontWeight: "bold" }}>
                {fmt(mr.masterEfficiencyScore ?? 75)}%
              </span>
            </div>
            <div
              style={{
                marginTop: "4px",
                padding: "6px",
                borderRadius: "4px",
                textAlign: "center",
                fontWeight: "bold",
                fontSize: "12px",
                background:
                  (mr.masterEfficiencyScore ?? 75) >
                  (m.masterEfficiencyScore ?? 70)
                    ? "rgba(46, 204, 64, 0.15)"
                    : "rgba(77, 150, 255, 0.15)",
                color:
                  (mr.masterEfficiencyScore ?? 75) >
                  (m.masterEfficiencyScore ?? 70)
                    ? "#2ecc40"
                    : "#4d96ff",
              }}
            >
              Winner:{" "}
              {(mr.masterEfficiencyScore ?? 75) >
              (m.masterEfficiencyScore ?? 70)
                ? "🔄 Roundabout"
                : "🚦 Fixed-Time Signal"}
            </div>
          </div>
        </div>
      )}

      {/* Vehicle state breakdown */}
      <section className="sidebar-section">
        <h3 className="section-title">Vehicles {isDual && "(Sig / Round)"}</h3>
        {isDual && vc && vcr ? (
          <div className="vehicle-chips" style={{ gridTemplateColumns: "1fr" }}>
            <DualVehicleChip
              label="Active"
              valA={vc.active}
              valB={vcr.active}
              color="#4d96ff"
            />
            <DualVehicleChip
              label="Waiting"
              valA={vc.waiting}
              valB={vcr.waiting}
              color="#ff6b6b"
            />
            <DualVehicleChip
              label="Crossing/Ring"
              valA={vc.crossing}
              valB={vcr.crossing + vcr.inRoundabout}
              color="#ffd93d"
            />
            <DualVehicleChip
              label="Exited"
              valA={vc.exited}
              valB={vcr.exited}
              color="#888"
            />
          </div>
        ) : (
          <div className="vehicle-chips">
            <VehicleChip label="Active" value={vc?.active} color="#4d96ff" />
            <VehicleChip
              label="Approaching"
              value={vc?.approaching}
              color="#20c997"
            />
            <VehicleChip label="Waiting" value={vc?.waiting} color="#ff6b6b" />
            <VehicleChip
              label="Crossing"
              value={vc?.crossing}
              color="#ffd93d"
            />
            {vc && vc.inRoundabout > 0 && (
              <VehicleChip
                label="In Ring"
                value={vc.inRoundabout}
                color="#cc5de8"
              />
            )}
            <VehicleChip label="Exited" value={vc?.exited} color="#888" />
          </div>
        )}
      </section>

      {/* Queue lengths */}
      {!isDual && (
        <section className="sidebar-section">
          <h3 className="section-title">Queue Lengths</h3>
          <div className="queue-bars">
            {DIRECTIONS.map((dir) => {
              const q =
                (m?.currentQueueLengths && m.currentQueueLengths[dir]) ?? 0;
              const pct = Math.min((q / maxQ) * 100, 100);
              const color = metricColor(q, 3, 8);
              return (
                <div key={dir} className="queue-row">
                  <span className="queue-dir">{DIR_LABEL[dir]}</span>
                  <div className="queue-bar-track">
                    <div
                      className="queue-bar-fill"
                      style={{
                        width: `${pct.toString()}%`,
                        background: color,
                      }}
                    />
                  </div>
                  <span className="queue-val">{q}</span>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* Key metrics */}
      <section className="sidebar-section">
        <h3 className="section-title">Performance Metrics</h3>
        <div className="metric-rows">
          {isDual && m && mr ? (
            <>
              <DualMetricRow
                label="Avg Wait Time"
                valA={`${fmt(m.averageWaitTime)}s`}
                valB={`${fmt(mr.averageWaitTime)}s`}
                better={compareBetter(
                  m.averageWaitTime,
                  mr.averageWaitTime,
                  true,
                )}
              />
              <DualMetricRow
                label="Throughput"
                valA={fmt(m.throughput, 0)}
                valB={fmt(mr.throughput, 0)}
                better={compareBetter(m.throughput, mr.throughput, false)}
              />
              <DualMetricRow
                label="Throughput Rate"
                valA={`${fmt(m.throughputRate)} /m`}
                valB={`${fmt(mr.throughputRate)} /m`}
                better={compareBetter(
                  m.throughputRate,
                  mr.throughputRate,
                  false,
                )}
              />
              <DualMetricRow
                label="Avg Travel Speed"
                valA={`${fmt(m.averageTravelSpeed)} m/s`}
                valB={`${fmt(mr.averageTravelSpeed)} m/s`}
                better={compareBetter(
                  m.averageTravelSpeed,
                  mr.averageTravelSpeed,
                  false,
                )}
              />
              <DualMetricRow
                label="Intersection Utilization"
                valA={`${fmt(m.intersectionUtilization)}%`}
                valB={`${fmt(mr.intersectionUtilization)}%`}
                better={compareBetter(
                  m.intersectionUtilization,
                  mr.intersectionUtilization,
                  false,
                )}
              />
              <DualMetricRow
                label="Max Queue"
                valA={fmt(m.maxQueueLength, 0)}
                valB={fmt(mr.maxQueueLength, 0)}
                better={compareBetter(
                  m.maxQueueLength,
                  mr.maxQueueLength,
                  true,
                )}
              />
              <DualMetricRow
                label="Avg Queue Length"
                valA={fmt(m.averageQueueLength)}
                valB={fmt(mr.averageQueueLength)}
                better={compareBetter(
                  m.averageQueueLength,
                  mr.averageQueueLength,
                  true,
                )}
              />
              <DualMetricRow
                label="Queue Stability (QSI)"
                valA={fmt(m.queueStabilityIndex)}
                valB={fmt(mr.queueStabilityIndex)}
                better={compareBetter(
                  m.queueStabilityIndex,
                  mr.queueStabilityIndex,
                  true,
                )}
              />
              <DualMetricRow
                label="Congestion Recovery"
                valA={`${fmt(m.congestionRecoveryTime)}s`}
                valB={`${fmt(mr.congestionRecoveryTime)}s`}
                better={compareBetter(
                  m.congestionRecoveryTime,
                  mr.congestionRecoveryTime,
                  true,
                )}
              />
              <DualMetricRow
                label="Total Stops"
                valA={fmt(m.totalStops, 0)}
                valB={fmt(mr.totalStops, 0)}
                better={compareBetter(m.totalStops, mr.totalStops, true)}
              />
              <DualMetricRow
                label="Avg Stops/Veh"
                valA={fmt(m.averageStopsPerVehicle)}
                valB={fmt(mr.averageStopsPerVehicle)}
                better={compareBetter(
                  m.averageStopsPerVehicle,
                  mr.averageStopsPerVehicle,
                  true,
                )}
              />
              <DualMetricRow
                label="Speed Variance"
                valA={fmt(m.speedVarianceIndex)}
                valB={fmt(mr.speedVarianceIndex)}
                better={compareBetter(
                  m.speedVarianceIndex,
                  mr.speedVarianceIndex,
                  true,
                )}
              />
              <DualMetricRow
                label="Travel Reliability"
                valA={fmt(m.travelTimeReliability)}
                valB={fmt(mr.travelTimeReliability)}
                better={compareBetter(
                  m.travelTimeReliability,
                  mr.travelTimeReliability,
                  true,
                )}
              />
              <DualMetricRow
                label="Fairness Index"
                valA={fmt(m.directionalFairnessIndex)}
                valB={fmt(mr.directionalFairnessIndex)}
                better={compareBetter(
                  m.directionalFairnessIndex,
                  mr.directionalFairnessIndex,
                  false,
                )}
              />
              <DualMetricRow
                label="Idle Loss"
                valA={fmt(m.idleOpportunityLoss)}
                valB={fmt(mr.idleOpportunityLoss)}
                better={compareBetter(
                  m.idleOpportunityLoss,
                  mr.idleOpportunityLoss,
                  true,
                )}
              />
              <DualMetricRow
                label="Land Footprint Area"
                valA={`${fmt(m.spaceFootprintConsumed, 0)} m²`}
                valB={`${fmt(mr.spaceFootprintConsumed, 0)} m²`}
                better={compareBetter(
                  m.spaceFootprintConsumed,
                  mr.spaceFootprintConsumed,
                  true,
                )}
              />
            </>
          ) : (
            <>
              <MetricRow
                label="Avg Wait Time"
                value={`${fmt(m?.averageWaitTime)}s`}
                color={metricColor(m?.averageWaitTime ?? 0, 15, 40)}
              />
              <MetricRow
                label="Throughput"
                value={`${fmt(m?.throughput, 0)} veh`}
                color="#4d96ff"
              />
              <MetricRow
                label="Throughput Rate"
                value={`${fmt(m?.throughputRate)} /min`}
                color="#20c997"
              />
              <MetricRow
                label="Avg Travel Speed"
                value={`${fmt(m?.averageTravelSpeed)} m/s`}
                color="#4d96ff"
              />
              <MetricRow
                label="Utilization"
                value={`${fmt(m?.intersectionUtilization)}%`}
                color={metricColor(
                  100 - (m?.intersectionUtilization ?? 100),
                  10,
                  40,
                )}
              />
              <MetricRow
                label="Max Queue"
                value={`${fmt(m?.maxQueueLength, 0)} veh`}
                color={metricColor(m?.maxQueueLength ?? 0, 5, 12)}
              />
              <MetricRow
                label="Avg Queue Length"
                value={`${fmt(m?.averageQueueLength)} veh`}
                color={metricColor(m?.averageQueueLength ?? 0, 3, 8)}
              />
              <MetricRow
                label="Queue Stability"
                value={fmt(m?.queueStabilityIndex)}
                color={metricColor(m?.queueStabilityIndex ?? 0, 0.3, 0.8)}
              />
              <MetricRow
                label="Recovery Time"
                value={`${fmt(m?.congestionRecoveryTime)}s`}
                color={metricColor(m?.congestionRecoveryTime ?? 0, 5, 20)}
              />
              <MetricRow
                label="Total Stops"
                value={fmt(m?.totalStops, 0)}
                color={metricColor(m?.totalStops ?? 0, 10, 30)}
              />
              <MetricRow
                label="Avg Stops/Veh"
                value={fmt(m?.averageStopsPerVehicle)}
                color={metricColor(m?.averageStopsPerVehicle ?? 0, 1, 3)}
              />
              <MetricRow
                label="Speed Variance"
                value={fmt(m?.speedVarianceIndex)}
                color={metricColor(m?.speedVarianceIndex ?? 0, 0.3, 0.7)}
              />
              <MetricRow
                label="Travel Reliability"
                value={fmt(m?.travelTimeReliability)}
                color={metricColor(m?.travelTimeReliability ?? 0, 1.2, 2.0)}
              />
              <MetricRow
                label="Fairness Index"
                value={fmt(m?.directionalFairnessIndex)}
                color={metricColor(
                  1 - (m?.directionalFairnessIndex ?? 1),
                  0,
                  0.2,
                )}
              />
              <MetricRow
                label="Idle Loss"
                value={fmt(m?.idleOpportunityLoss)}
                color={metricColor(m?.idleOpportunityLoss ?? 0, 0.05, 0.2)}
              />
              <MetricRow
                label="Land Footprint"
                value={`${fmt(m?.spaceFootprintConsumed, 0)} m²`}
                color="#888"
              />
              <MetricRow
                label="Total Spawned"
                value={fmt(m?.totalVehiclesSpawned, 0)}
                color="#888"
              />
            </>
          )}
        </div>
      </section>

      {/* Reports Section */}
      {snapshot && (
        <section
          className="sidebar-section"
          style={{ display: "flex", justifyContent: "center" }}
        >
          <button
            className="pb-btn pb-primary"
            onClick={handleDownloadReport}
            style={{
              width: "100%",
              padding: "8px 12px",
              fontSize: "12px",
              borderRadius: "4px",
            }}
          >
            📥 Download CSV Report
          </button>
        </section>
      )}
    </aside>
  );
};

// ── Sub-components ────────────────────────────────────────────────────────────

function VehicleChip({
  label,
  value,
  color,
}: {
  label: string;
  value: number | undefined;
  color: string;
}) {
  return (
    <div className="vehicle-chip" style={{ borderColor: color }}>
      <span className="chip-count" style={{ color }}>
        {value ?? 0}
      </span>
      <span className="chip-label">{label}</span>
    </div>
  );
}

function DualVehicleChip({
  label,
  valA,
  valB,
  color,
}: {
  label: string;
  valA: number;
  valB: number;
  color: string;
}) {
  return (
    <div
      className="vehicle-chip"
      style={{
        borderColor: color,
        display: "flex",
        justifyContent: "space-between",
        padding: "6px 10px",
        width: "100%",
      }}
    >
      <span className="chip-label" style={{ color: "var(--text-secondary)" }}>
        {label}
      </span>
      <span className="chip-count" style={{ color }}>
        🚦 {valA} / 🔄 {valB}
      </span>
    </div>
  );
}

function MetricRow({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color: string;
}) {
  return (
    <div className="metric-row">
      <span className="metric-label">{label}</span>
      <span className="metric-value" style={{ color }}>
        {value}
      </span>
    </div>
  );
}

function DualMetricRow({
  label,
  valA,
  valB,
  better,
}: {
  label: string;
  valA: string;
  valB: string;
  better: "sig" | "round" | null;
}) {
  return (
    <div
      className="metric-row"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "2px",
        padding: "6px 0",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <span className="metric-label">{label}</span>
      </div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          fontSize: "11px",
          fontFamily: "monospace",
        }}
      >
        <span
          style={{
            color:
              better === "sig"
                ? "#2ecc40"
                : better === "round"
                  ? "#ff4136"
                  : "var(--text-secondary)",
          }}
        >
          🚦 {valA}
        </span>
        <span
          style={{
            color:
              better === "round"
                ? "#2ecc40"
                : better === "sig"
                  ? "#ff4136"
                  : "var(--text-secondary)",
          }}
        >
          🔄 {valB}
        </span>
      </div>
    </div>
  );
}
