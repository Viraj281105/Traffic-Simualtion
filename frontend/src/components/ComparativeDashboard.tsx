import React, { useState } from "react";
import type { DualSnapshot, VehicleCounts } from "../types/simulation";
import type { ConnectionStatus } from "../services/websocket";
import { WeightedScoringPanel } from "./WeightedScoringPanel";
import type { ScoringWeights } from "../types/scoring";
import { DEFAULT_WEIGHTS, computeWeightedScore } from "../types/scoring";
import "./ComparativeDashboard.css";

interface ComparativeDashboardProps {
  snapshot: DualSnapshot | null;
  connectionStatus: ConnectionStatus;
}

function fmt(val: number | undefined, decimals = 1): string {
  if (val === undefined) return "—";
  return val.toFixed(decimals);
}

export const ComparativeDashboard: React.FC<ComparativeDashboardProps> = ({
  snapshot,
}) => {
  const [weights, setWeights] = useState<ScoringWeights>(DEFAULT_WEIGHTS);

  if (!snapshot) {
    return (
      <div className="comparative-dashboard empty">
        <p>Waiting for simulation data...</p>
      </div>
    );
  }

  const mSignal = snapshot.signal.metrics;
  const mRound = snapshot.roundabout.metrics;

  const handleDownloadReport = () => {
    const scoreSig = computeWeightedScore(mSignal, weights);
    const scoreRnd = computeWeightedScore(mRound, weights);
    const overallWinner =
      scoreRnd > scoreSig
        ? "Roundabout"
        : scoreSig > scoreRnd
          ? "Signal"
          : "Tie";

    let csv = "=== CUSTOM WEIGHTED SCORING REPORT ===\n";
    csv += `Wait Time Weight,${weights.weightWaitTime.toString()}%\n`;
    csv += `Throughput Weight,${weights.weightThroughput.toString()}%\n`;
    csv += `Queue Weight,${weights.weightQueue.toString()}%\n`;
    csv += `Fairness Weight,${weights.weightFairness.toString()}%\n`;
    csv += `Stops Weight,${weights.weightStops.toString()}%\n`;
    csv += `Signal Score,${scoreSig.toFixed(1)}/100\n`;
    csv += `Roundabout Score,${scoreRnd.toFixed(1)}/100\n`;
    csv += `Overall Winner,${overallWinner}\n\n`;

    csv += "=== DETAILED METRICS BREAKDOWN ===\n";
    csv += "Metric Name,Fixed-Time Signal,Roundabout,Winner,Delta (%)\n";
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
    addRow(
      "Average Wait Time",
      mSignal.averageWaitTime,
      mRound.averageWaitTime,
      true,
    );
    addRow("Throughput", mSignal.throughput, mRound.throughput, false);
    addRow(
      "Average Speed",
      mSignal.averageTravelSpeed,
      mRound.averageTravelSpeed,
      false,
    );
    addRow(
      "Average Queue Length",
      mSignal.averageQueueLength,
      mRound.averageQueueLength,
      true,
    );
    addRow(
      "Max Queue Length",
      mSignal.maxQueueLength,
      mRound.maxQueueLength,
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
  };

  return (
    <div className="comparative-dashboard">
      <WeightedScoringPanel
        metricsSignal={mSignal}
        metricsRoundabout={mRound}
        weights={weights}
        onWeightsChange={setWeights}
      />
      <div
        className="dashboard-header"
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "16px",
        }}
      >
        <div className="dashboard-insights">
          <h3
            style={{
              margin: 0,
              fontSize: "14px",
              color: "var(--text-primary)",
            }}
          >
            Performance Insights
          </h3>
          <p
            style={{
              margin: "4px 0 0 0",
              fontSize: "12px",
              color: "var(--text-secondary)",
            }}
          >
            Observe how the Roundabout typically reduces Average Wait Time and
            Queues during low-to-medium traffic, while the Fixed-Time Signal may
            offer better fairness or throughput under heavy, directional loads.
          </p>
        </div>
        <button
          className="pb-btn pb-primary"
          onClick={handleDownloadReport}
          style={{
            padding: "8px 12px",
            fontSize: "12px",
            borderRadius: "4px",
            whiteSpace: "nowrap",
          }}
        >
          📥 Export CSV
        </button>
      </div>

      <table className="comparison-table">
        <thead>
          <tr>
            <th>Performance Metric</th>
            <th>🚦 Signal</th>
            <th>🔄 Roundabout</th>
            <th>Improvement %</th>
          </tr>
        </thead>
        <tbody>
          <ComparisonRow
            label="Avg Wait Time (s)"
            valA={mSignal.averageWaitTime}
            valB={mRound.averageWaitTime}
            lowerIsBetter={true}
            formatter={(v) => fmt(v)}
            insight="Roundabouts minimize wait times in light-to-moderate traffic."
          />
          <ComparisonRow
            label="Throughput (veh)"
            valA={mSignal.throughput}
            valB={mRound.throughput}
            lowerIsBetter={false}
            formatter={(v) => fmt(v, 0)}
            insight="Total vehicles successfully processed."
          />
          <ComparisonRow
            label="Avg Speed (m/s)"
            valA={mSignal.averageTravelSpeed}
            valB={mRound.averageTravelSpeed}
            lowerIsBetter={false}
            formatter={(v) => fmt(v)}
            insight="Higher average speed indicates better flow."
          />
          <ComparisonRow
            label="Average Queue"
            valA={mSignal.averageQueueLength}
            valB={mRound.averageQueueLength}
            lowerIsBetter={true}
            formatter={(v) => fmt(v)}
            insight="Signals usually have longer queues due to red phases."
          />
          <ComparisonRow
            label="Max Queue"
            valA={mSignal.maxQueueLength}
            valB={mRound.maxQueueLength}
            lowerIsBetter={true}
            formatter={(v) => fmt(v, 0)}
            insight="Peak congestion impact on approaches."
          />
        </tbody>
      </table>
    </div>
  );
};

export function CompactVehicleStatePanel({
  counts,
}: {
  counts: VehicleCounts | null | undefined;
}) {
  if (!counts) return null;
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "8px",
        background: "var(--bg-secondary)",
        padding: "12px",
        borderRadius: "8px",
        minWidth: "70px",
        boxShadow: "var(--shadow-sm)",
      }}
    >
      <VerticalStateBox label="Active" value={counts.active} color="#3b82f6" />
      <VerticalStateBox
        label="Appr."
        value={counts.approaching}
        color="#8b5cf6"
      />
      <VerticalStateBox label="Wait" value={counts.waiting} color="#ef4444" />
      <VerticalStateBox label="Cross" value={counts.crossing} color="#f59e0b" />
      <VerticalStateBox label="Exit" value={counts.exited} color="#10b981" />
    </div>
  );
}

function VerticalStateBox({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: string;
}) {
  return (
    <div
      style={{
        background: "var(--bg-tertiary)",
        borderRadius: "4px",
        padding: "6px 4px",
        textAlign: "center",
        borderLeft: `3px solid ${color}`,
      }}
    >
      <div
        style={{
          fontSize: "14px",
          fontWeight: "bold",
          color: "var(--text-primary)",
        }}
      >
        {value}
      </div>
      <div
        style={{
          fontSize: "10px",
          color: "var(--text-secondary)",
          textTransform: "uppercase",
          letterSpacing: "0.2px",
          marginTop: "2px",
        }}
      >
        {label}
      </div>
    </div>
  );
}

function ComparisonRow({
  label,
  valA,
  valB,
  lowerIsBetter,
  formatter,
  insight,
}: {
  label: string;
  valA: number;
  valB: number;
  lowerIsBetter: boolean;
  formatter: (v: number) => string;
  insight: string;
}) {
  const diff = valB - valA;
  const pct = valA === 0 ? 0 : Math.abs((diff / valA) * 100);

  let winner = "";
  if (valA !== valB) {
    if (lowerIsBetter) winner = valA < valB ? "sig" : "round";
    else winner = valA > valB ? "sig" : "round";
  }

  const isBetterDiff = lowerIsBetter ? diff < 0 : diff > 0;
  const diffColorClass = diff === 0 ? "neutral" : isBetterDiff ? "good" : "bad";

  return (
    <tr>
      <td className="metric-name">
        <div>{label}</div>
        <div
          style={{
            fontSize: "11px",
            color: "var(--text-secondary)",
            fontWeight: "normal",
            marginTop: "2px",
          }}
        >
          {insight}
        </div>
      </td>
      <td className={winner === "sig" ? "winner-cell" : ""}>
        {formatter(valA)}
      </td>
      <td className={winner === "round" ? "winner-cell" : ""}>
        {formatter(valB)}
      </td>
      <td className="diff-cell">
        <span className={`diff-badge ${diffColorClass}`}>
          {pct > 0 && winner === "round"
            ? "+"
            : pct > 0 && winner === "sig"
              ? "-"
              : ""}
          {fmt(pct)}%
        </span>
      </td>
    </tr>
  );
}
