import React, { useState, useEffect, useCallback } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import { API_BASE_URL } from "../config";
import "./VolumeAnalysisDashboard.css";

// ── Types ──────────────────────────────────────────────────────────────────

interface SweepRun {
  arrivalRate: number;
  hourlyVolumeVehPerHour: number;
  winner: "signal" | "roundabout" | "tie";
  delayDeltaPercent: number;
  signal: { delay: number; throughput: number; queue: number };
  roundabout: { delay: number; throughput: number; queue: number };
}

interface SweepCurves {
  rates: number[];
  volumesVehPerHour: number[];
  signal: { delays: number[]; throughputs: number[]; queues: number[] };
  roundabout: { delays: number[]; throughputs: number[]; queues: number[] };
  crossoverArrivalRate: number | null;
  crossoverHourlyVolume: number | null;
}

interface SweepSession {
  sessionId: string;
  name: string;
  duration: number;
  randomSeed: number;
  curves: SweepCurves;
  runs: SweepRun[];
}

interface SavedSweep {
  id: string;
  name: string;
  created_at: string;
}

type MetricView = "all" | "delay" | "throughput" | "queue";
type XAxisMode = "volume" | "rate";

// ── Chart data builder ──────────────────────────────────────────────────────

function buildChartData(session: SweepSession) {
  return session.runs.map((run) => ({
    volume: run.hourlyVolumeVehPerHour,
    rate: Number(run.arrivalRate.toFixed(2)),
    signalDelay: Number(run.signal.delay.toFixed(2)),
    roundaboutDelay: Number(run.roundabout.delay.toFixed(2)),
    signalThroughput: run.signal.throughput,
    roundaboutThroughput: run.roundabout.throughput,
    signalQueue: Number(run.signal.queue.toFixed(2)),
    roundaboutQueue: Number(run.roundabout.queue.toFixed(2)),
    winner: run.winner,
    delayDeltaPercent: Number(run.delayDeltaPercent.toFixed(1)),
  }));
}

// ── Custom Tooltip ──────────────────────────────────────────────────────────

const CustomTooltip = ({
  active,
  payload,
  label,
  unit = "",
  xMode = "volume",
}: {
  active?: boolean;
  payload?: Array<{
    name: string;
    value: number;
    color: string;
    payload?: unknown;
  }>;
  label?: number | string;
  unit?: string;
  xMode?: XAxisMode;
}) => {
  if (!active || !payload || payload.length === 0) return null;

  const raw = payload[0].payload as
    | {
        winner?: "signal" | "roundabout" | "tie";
        delayDeltaPercent?: number;
      }
    | undefined;

  return (
    <div className="custom-chart-tooltip">
      <div className="tooltip-header">
        <span className="tooltip-x-val">
          {xMode === "volume"
            ? `${String(label)} veh/h`
            : `${String(label)} veh/s`}
        </span>
        {raw?.winner && (
          <span className={`tooltip-winner-badge winner-${raw.winner}`}>
            {raw.winner === "roundabout"
              ? "🔄 Roundabout Advantage"
              : raw.winner === "signal"
                ? "🚦 Signal Advantage"
                : "⚖️ Parity / Tie"}
          </span>
        )}
      </div>
      <div className="tooltip-metrics">
        {payload.map((p) => (
          <div key={p.name} className="tooltip-row">
            <span className="tooltip-dot" style={{ background: p.color }} />
            <span className="tooltip-name">{p.name}:</span>
            <span className="tooltip-val" style={{ color: p.color }}>
              {p.value.toFixed(2)}
              {unit}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};

// ── Main Component ──────────────────────────────────────────────────────────

export const VolumeAnalysisDashboard: React.FC = () => {
  const [savedSweeps, setSavedSweeps] = useState<SavedSweep[]>([]);
  const [activeSession, setActiveSession] = useState<SweepSession | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Sweep config form state
  const [sweepDuration, setSweepDuration] = useState(60);
  const [randomSeed, setRandomSeed] = useState(42);

  // Interactive UI view controls
  const [metricView, setMetricView] = useState<MetricView>("all");
  const [xAxisMode, setXAxisMode] = useState<XAxisMode>("volume");
  const [filterWinner, setFilterWinner] = useState<
    "all" | "roundabout" | "signal"
  >("all");
  const [showEngineeringNotes, setShowEngineeringNotes] = useState(true);

  const [isRunning, setIsRunning] = useState(false);
  const [sweepError, setSweepError] = useState<string | null>(null);
  const [loadingSession, setLoadingSession] = useState(false);

  // Fetch saved sweep list
  const fetchSweeps = useCallback(() => {
    fetch(`${API_BASE_URL}/api/v1/study/sweeps`)
      .then((r) => r.json())
      .then((data: SavedSweep[]) => {
        setSavedSweeps(data);
      })
      .catch(() => {
        setSavedSweeps([]);
      });
  }, []);

  useEffect(() => {
    fetchSweeps();
  }, [fetchSweeps]);

  // Load a specific sweep session
  const loadSweep = (id: string) => {
    setSelectedId(id);
    setLoadingSession(true);
    fetch(`${API_BASE_URL}/api/v1/study/sweeps/${id}`)
      .then((r) => r.json())
      .then((data: SweepSession) => {
        setActiveSession(data);
        setLoadingSession(false);
      })
      .catch(() => {
        setLoadingSession(false);
        setSweepError("Failed to load sweep results.");
      });
  };

  // Trigger new sweep via API
  const runSweep = () => {
    setIsRunning(true);
    setSweepError(null);
    fetch(`${API_BASE_URL}/api/v1/study/sweeps/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        duration: sweepDuration,
        random_seed: randomSeed,
        time_step: 0.1,
      }),
    })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status.toString()}`);
        return r.json() as Promise<SweepSession>;
      })
      .then((data) => {
        setActiveSession(data);
        setSelectedId(data.sessionId);
        setIsRunning(false);
        fetchSweeps();
      })
      .catch((e: unknown) => {
        setSweepError(e instanceof Error ? e.message : "Sweep failed");
        setIsRunning(false);
      });
  };

  // Export CSV helper
  const exportCSV = () => {
    if (!activeSession) return;
    const headers = [
      "Arrival Rate (veh/s)",
      "Hourly Volume (veh/h)",
      "Signal Delay (s)",
      "Roundabout Delay (s)",
      "Delay Delta (%)",
      "Signal Throughput (veh)",
      "Roundabout Throughput (veh)",
      "Signal Queue (veh)",
      "Roundabout Queue (veh)",
      "Winning Strategy",
    ];

    const rows = activeSession.runs.map((r) => [
      r.arrivalRate.toFixed(2),
      r.hourlyVolumeVehPerHour.toString(),
      r.signal.delay.toFixed(2),
      r.roundabout.delay.toFixed(2),
      r.delayDeltaPercent.toFixed(1),
      r.signal.throughput.toString(),
      r.roundabout.throughput.toString(),
      r.signal.queue.toFixed(1),
      r.roundabout.queue.toFixed(1),
      r.winner,
    ]);

    const csvContent =
      "data:text/csv;charset=utf-8," +
      [headers.join(","), ...rows.map((e) => e.join(","))].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute(
      "download",
      `traffic_volume_sweep_${activeSession.sessionId.slice(0, 8)}.csv`,
    );
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const chartData = activeSession ? buildChartData(activeSession) : [];
  const crossover = activeSession?.curves.crossoverHourlyVolume ?? null;
  const xDataKey = xAxisMode === "volume" ? "volume" : "rate";

  // Compute quick KPI metrics
  const roundaboutWins = activeSession
    ? activeSession.runs.filter((r) => r.winner === "roundabout").length
    : 0;
  const signalWins = activeSession
    ? activeSession.runs.filter((r) => r.winner === "signal").length
    : 0;
  const totalRuns = activeSession ? activeSession.runs.length : 0;
  const roundaboutWinPct =
    totalRuns > 0 ? Math.round((roundaboutWins / totalRuns) * 100) : 0;

  // Filtered runs for table
  const filteredRuns = activeSession
    ? activeSession.runs.filter((r) => {
        if (filterWinner === "all") return true;
        return r.winner === filterWinner;
      })
    : [];

  return (
    <div className="volume-dashboard">
      {/* ── Top Header & KPI Bar ──────────────────────── */}
      <div className="volume-header-row">
        <div className="header-title-group">
          <h2>📈 Traffic Volume & Capacity Curve Analysis</h2>
          <p className="header-subtitle">
            Systematic sensitivity study evaluating Signal vs. Roundabout
            control across increasing demand levels (360 to 11,520+ veh/h).
          </p>
        </div>
        <div className="header-actions">
          {activeSession && (
            <button
              className="export-csv-btn"
              onClick={exportCSV}
              title="Download study dataset as CSV"
            >
              📥 Export CSV
            </button>
          )}
        </div>
      </div>

      {/* ── Main Control Bar (Trigger + Saved Sweeps) ──── */}
      <div className="sweep-top-controls-grid">
        {/* Sweep Trigger Panel */}
        <div className="sweep-trigger-panel">
          <div className="panel-header-badge">
            <h3>📊 Run Volume Sweep Experiment</h3>
            <span className="badge-pill">8 Demand Rates (0.1–0.8 veh/s)</span>
          </div>

          <div className="sweep-controls">
            <div className="sweep-field">
              <label>Duration / Rate (s)</label>
              <input
                type="number"
                min={10}
                max={600}
                step={10}
                value={sweepDuration}
                onChange={(e) => {
                  setSweepDuration(Number(e.target.value));
                }}
              />
            </div>

            <div className="sweep-field">
              <label>Random Seed</label>
              <div className="seed-input-wrapper">
                <input
                  type="number"
                  min={1}
                  value={randomSeed}
                  onChange={(e) => {
                    setRandomSeed(Number(e.target.value));
                  }}
                />
                <button
                  type="button"
                  className="dice-btn"
                  onClick={() => {
                    setRandomSeed(Math.floor(Math.random() * 999999) + 1);
                  }}
                  title="Randomize seed"
                >
                  🎲
                </button>
              </div>
            </div>

            <div className="sweep-field" style={{ opacity: 0.7 }}>
              <label>Rates Evaluated</label>
              <input type="number" value={8} disabled readOnly />
            </div>

            <div className="preset-shortcuts">
              <span className="preset-label">Presets:</span>
              <button
                type="button"
                className="preset-tag"
                onClick={() => {
                  setSweepDuration(30);
                }}
              >
                ⚡ Quick (30s)
              </button>
              <button
                type="button"
                className="preset-tag"
                onClick={() => {
                  setSweepDuration(60);
                }}
              >
                ⚖️ Standard (60s)
              </button>
              <button
                type="button"
                className="preset-tag"
                onClick={() => {
                  setSweepDuration(120);
                }}
              >
                🔬 Rigorous (120s)
              </button>
            </div>

            <button
              className="sweep-run-btn"
              onClick={runSweep}
              disabled={isRunning}
            >
              {isRunning ? "⏳ Running..." : "▶ Run Sweep"}
            </button>
          </div>

          {sweepError && <div className="sweep-error">⚠ {sweepError}</div>}
          {isRunning && (
            <div className="sweep-loading">
              <div className="spin" />
              <span>
                Simulating 8 volume tiers across dual intersection models —
                computing capacity envelopes…
              </span>
            </div>
          )}
        </div>

        {/* Saved Sweeps Panel */}
        <div className="saved-sweeps-panel">
          <div className="panel-header-badge">
            <h3>📁 Saved Sweeps</h3>
            <span className="count-pill">
              {savedSweeps.length.toString()} saved
            </span>
          </div>
          {savedSweeps.length > 0 ? (
            <div className="sweep-list">
              {savedSweeps.map((s) => (
                <div
                  key={s.id}
                  className={`sweep-list-item ${selectedId === s.id ? "active" : ""}`}
                  onClick={() => {
                    loadSweep(s.id);
                  }}
                >
                  <div className="sweep-item-left">
                    <span className="sweep-name">{s.name}</span>
                    <span className="sweep-meta">
                      {new Date(s.created_at).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}{" "}
                      · {new Date(s.created_at).toLocaleDateString()}
                    </span>
                  </div>
                  {selectedId === s.id && (
                    <span className="active-tag">Active</span>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-saved-hint">
              <span>
                No sweep history yet. Click <strong>Run Sweep</strong> to
                generate curves!
              </span>
            </div>
          )}
        </div>
      </div>

      {/* ── Loading indicator ──────────────────────────── */}
      {loadingSession && (
        <div className="sweep-loading">
          <div className="spin" />
          <span>Retrieving sweep curves and telemetry…</span>
        </div>
      )}

      {/* ── Active Results View ───────────────────────── */}
      {activeSession && !loadingSession && (
        <>
          {/* Quick KPI Cards */}
          <div className="volume-kpi-grid">
            <div className="kpi-card">
              <div className="kpi-icon">🎯</div>
              <div className="kpi-content">
                <span className="kpi-label">Critical Crossover Point</span>
                <span className="kpi-value">
                  {crossover
                    ? `${crossover.toLocaleString()} veh/h`
                    : "None Detected"}
                </span>
                <span className="kpi-hint">
                  {crossover
                    ? "Roundabout saturates; Signal becomes superior"
                    : "Roundabout maintained lowest delay across all 8 tiers"}
                </span>
              </div>
            </div>

            <div className="kpi-card">
              <div className="kpi-icon">🏆</div>
              <div className="kpi-content">
                <span className="kpi-label">Dominant Strategy</span>
                <span
                  className="kpi-value"
                  style={{
                    color: roundaboutWins >= signalWins ? "#2ecc40" : "#4d96ff",
                  }}
                >
                  {roundaboutWins > signalWins
                    ? `Roundabout (${roundaboutWinPct.toString()}%)`
                    : signalWins > roundaboutWins
                      ? "Signal Control"
                      : "Balanced Parity"}
                </span>
                <span className="kpi-hint">
                  Roundabout wins {roundaboutWins.toString()} of{" "}
                  {totalRuns.toString()} demand brackets tested
                </span>
              </div>
            </div>

            <div className="kpi-card">
              <div className="kpi-icon">⏱️</div>
              <div className="kpi-content">
                <span className="kpi-label">Max Delay Reduction</span>
                <span className="kpi-value" style={{ color: "#2ecc40" }}>
                  {activeSession.runs.length > 0
                    ? `${Math.abs(Math.min(...activeSession.runs.map((r) => r.delayDeltaPercent))).toFixed(1)}%`
                    : "N/A"}
                </span>
                <span className="kpi-hint">
                  Achieved under free-flow off-peak arrival rates
                </span>
              </div>
            </div>

            <div className="kpi-card">
              <div className="kpi-icon">🚦</div>
              <div className="kpi-content">
                <span className="kpi-label">Peak Saturation Volume</span>
                <span className="kpi-value">
                  {activeSession.curves.volumesVehPerHour.length > 0
                    ? `${Math.max(...activeSession.curves.volumesVehPerHour).toLocaleString()} veh/h`
                    : "11,520 veh/h"}
                </span>
                <span className="kpi-hint">
                  Upper stress-test boundary evaluated
                </span>
              </div>
            </div>
          </div>

          {/* Crossover badge */}
          {crossover ? (
            <div className="crossover-badge">
              <span className="crossover-icon">⭐</span>
              <div className="crossover-text">
                <strong>
                  Critical Saturation Crossover: {crossover.toLocaleString()}{" "}
                  veh/h
                </strong>
                <br />
                <span>
                  <strong>Below {crossover.toLocaleString()} veh/h:</strong>{" "}
                  Modern Roundabout drastically outperforms Fixed-Time Signal
                  (up to 50% lower vehicular delay).
                  <br />
                  <strong>
                    Above {crossover.toLocaleString()} veh/h:
                  </strong>{" "}
                  Roundabout entry headways become starved by circulating
                  queues; Fixed-Time Signal provides superior queue stability
                  and cycle fairness.
                </span>
              </div>
            </div>
          ) : (
            <div
              className="crossover-badge"
              style={{
                borderColor: "rgba(46, 204, 64, 0.3)",
                background: "rgba(46, 204, 64, 0.05)",
              }}
            >
              <span className="crossover-icon">🔄</span>
              <div className="crossover-text">
                <strong style={{ color: "#2ecc40" }}>
                  Roundabout Dominates All Volume Brackets
                </strong>
                <br />
                <span>
                  No saturation crossover detected in the tested range.
                  Roundabout maintained lower delay across all evaluated arrival
                  rates.
                </span>
              </div>
            </div>
          )}

          {/* ── Interactive View Switcher Bar ─────────── */}
          <div className="chart-view-toolbar">
            <div className="toolbar-group">
              <span className="toolbar-label">Metric View:</span>
              <button
                type="button"
                className={`toolbar-btn ${metricView === "all" ? "active" : ""}`}
                onClick={() => {
                  setMetricView("all");
                }}
              >
                📊 All 3 Curves
              </button>
              <button
                type="button"
                className={`toolbar-btn ${metricView === "delay" ? "active" : ""}`}
                onClick={() => {
                  setMetricView("delay");
                }}
              >
                ⏱️ Delay Only
              </button>
              <button
                type="button"
                className={`toolbar-btn ${metricView === "throughput" ? "active" : ""}`}
                onClick={() => {
                  setMetricView("throughput");
                }}
              >
                🚗 Throughput Only
              </button>
              <button
                type="button"
                className={`toolbar-btn ${metricView === "queue" ? "active" : ""}`}
                onClick={() => {
                  setMetricView("queue");
                }}
              >
                📏 Queue Length Only
              </button>
            </div>

            <div className="toolbar-group">
              <span className="toolbar-label">X-Axis Scale:</span>
              <button
                type="button"
                className={`toolbar-btn ${xAxisMode === "volume" ? "active" : ""}`}
                onClick={() => {
                  setXAxisMode("volume");
                }}
              >
                Hourly Vol (veh/h)
              </button>
              <button
                type="button"
                className={`toolbar-btn ${xAxisMode === "rate" ? "active" : ""}`}
                onClick={() => {
                  setXAxisMode("rate");
                }}
              >
                Rate (veh/s)
              </button>
            </div>

            <button
              type="button"
              className="insights-toggle-btn"
              onClick={() => {
                setShowEngineeringNotes((v) => !v);
              }}
            >
              {showEngineeringNotes ? "💡 Hide Insights" : "💡 Show Insights"}
            </button>
          </div>

          {/* ── Engineering Insights Accordion ───────── */}
          {showEngineeringNotes && (
            <div className="engineering-insights-box">
              <div className="insights-header">
                <h4>
                  🧠 Traffic Engineering Insights: Why Roundabouts Saturation
                  Occurs
                </h4>
              </div>
              <div className="insights-grid">
                <div className="insight-item">
                  <span className="insight-badge roundabout-badge">
                    Low-Medium Volumes (&lt; Crossover)
                  </span>
                  <p>
                    Roundabouts eliminate static yellow/red cycle losses.
                    Drivers execute continuous gap-acceptance without stopping
                    if the circulating ring is clear. Throughput remains near
                    capacity and queue buildup is negligible.
                  </p>
                </div>
                <div className="insight-item">
                  <span className="insight-badge signal-badge">
                    High Over-Capacity (&gt; Crossover)
                  </span>
                  <p>
                    As circulating volume exceeds critical density, entry
                    vehicles encounter zero acceptable gaps. This causes
                    exponential queue spillback and circular deadlock. Signals
                    enforce deterministic green splits, guaranteeing lane
                    progression.
                  </p>
                </div>
                <div className="insight-item">
                  <span className="insight-badge recommendation-badge">
                    Civic Planning Takeaway
                  </span>
                  <p>
                    {crossover
                      ? `For arterial corridors exceeding ${crossover.toLocaleString()} veh/h peak demand, a multi-phase Traffic Signal or Turbo-Roundabout with bypass lanes is mathematically required.`
                      : "For these demand profiles, modern roundabouts provide clear carbon, delay, and safety advantages over fixed-time signals."}
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* ── Charts Row (Full Width Grid) ─────────── */}
          <div className={`charts-grid view-${metricView}`}>
            {/* Delay Chart */}
            {(metricView === "all" || metricView === "delay") && (
              <div className="chart-card">
                <div className="chart-card-header">
                  <h4>Average Delay vs. Traffic Volume</h4>
                  <span className="chart-metric-unit">Seconds / Vehicle</span>
                </div>
                {chartData.length > 0 ? (
                  <ResponsiveContainer
                    width="100%"
                    height={metricView === "all" ? 220 : 340}
                  >
                    <LineChart
                      data={chartData}
                      margin={{ top: 8, right: 16, bottom: 8, left: 0 }}
                    >
                      <CartesianGrid
                        strokeDasharray="3 3"
                        stroke="rgba(255,255,255,0.07)"
                      />
                      <XAxis
                        dataKey={xDataKey}
                        tick={{ fontSize: 11, fill: "#8892b0" }}
                        tickFormatter={(v: number) => v.toString()}
                        label={{
                          value: xAxisMode === "volume" ? "veh/h" : "veh/s",
                          position: "insideBottom",
                          offset: -4,
                          fill: "#8892b0",
                          fontSize: 11,
                        }}
                      />
                      <YAxis tick={{ fontSize: 11, fill: "#8892b0" }} />
                      <Tooltip
                        content={<CustomTooltip unit="s" xMode={xAxisMode} />}
                      />
                      <Legend wrapperStyle={{ fontSize: 12, paddingTop: 4 }} />
                      {crossover && xAxisMode === "volume" && (
                        <ReferenceLine
                          x={crossover}
                          stroke="#ffd93d"
                          strokeDasharray="4 3"
                          label={{
                            value: `Crossover (${crossover.toLocaleString()})`,
                            position: "top",
                            fill: "#ffd93d",
                            fontSize: 11,
                          }}
                        />
                      )}
                      <Line
                        type="monotone"
                        dataKey="signalDelay"
                        name="Fixed-Time Signal"
                        stroke="#4d96ff"
                        strokeWidth={2.5}
                        dot={{ r: 4, fill: "#4d96ff" }}
                        activeDot={{ r: 6 }}
                      />
                      <Line
                        type="monotone"
                        dataKey="roundaboutDelay"
                        name="Modern Roundabout"
                        stroke="#2ecc40"
                        strokeWidth={2.5}
                        dot={{ r: 4, fill: "#2ecc40" }}
                        activeDot={{ r: 6 }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="chart-empty">No telemetry data recorded</div>
                )}
              </div>
            )}

            {/* Throughput Chart */}
            {(metricView === "all" || metricView === "throughput") && (
              <div className="chart-card">
                <div className="chart-card-header">
                  <h4>Throughput vs. Traffic Volume</h4>
                  <span className="chart-metric-unit">Completed Vehicles</span>
                </div>
                {chartData.length > 0 ? (
                  <ResponsiveContainer
                    width="100%"
                    height={metricView === "all" ? 220 : 340}
                  >
                    <LineChart
                      data={chartData}
                      margin={{ top: 8, right: 16, bottom: 8, left: 0 }}
                    >
                      <CartesianGrid
                        strokeDasharray="3 3"
                        stroke="rgba(255,255,255,0.07)"
                      />
                      <XAxis
                        dataKey={xDataKey}
                        tick={{ fontSize: 11, fill: "#8892b0" }}
                        tickFormatter={(v: number) => v.toString()}
                        label={{
                          value: xAxisMode === "volume" ? "veh/h" : "veh/s",
                          position: "insideBottom",
                          offset: -4,
                          fill: "#8892b0",
                          fontSize: 11,
                        }}
                      />
                      <YAxis tick={{ fontSize: 11, fill: "#8892b0" }} />
                      <Tooltip
                        content={
                          <CustomTooltip unit=" veh" xMode={xAxisMode} />
                        }
                      />
                      <Legend wrapperStyle={{ fontSize: 12, paddingTop: 4 }} />
                      {crossover && xAxisMode === "volume" && (
                        <ReferenceLine
                          x={crossover}
                          stroke="#ffd93d"
                          strokeDasharray="4 3"
                        />
                      )}
                      <Line
                        type="monotone"
                        dataKey="signalThroughput"
                        name="Fixed-Time Signal"
                        stroke="#4d96ff"
                        strokeWidth={2.5}
                        dot={{ r: 4, fill: "#4d96ff" }}
                        activeDot={{ r: 6 }}
                      />
                      <Line
                        type="monotone"
                        dataKey="roundaboutThroughput"
                        name="Modern Roundabout"
                        stroke="#2ecc40"
                        strokeWidth={2.5}
                        dot={{ r: 4, fill: "#2ecc40" }}
                        activeDot={{ r: 6 }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="chart-empty">No telemetry data recorded</div>
                )}
              </div>
            )}

            {/* Queue Chart */}
            {(metricView === "all" || metricView === "queue") && (
              <div className="chart-card">
                <div className="chart-card-header">
                  <h4>Average Queue Length vs. Traffic Volume</h4>
                  <span className="chart-metric-unit">
                    Average Vehicles in Line
                  </span>
                </div>
                {chartData.length > 0 ? (
                  <ResponsiveContainer
                    width="100%"
                    height={metricView === "all" ? 220 : 340}
                  >
                    <LineChart
                      data={chartData}
                      margin={{ top: 8, right: 16, bottom: 8, left: 0 }}
                    >
                      <CartesianGrid
                        strokeDasharray="3 3"
                        stroke="rgba(255,255,255,0.07)"
                      />
                      <XAxis
                        dataKey={xDataKey}
                        tick={{ fontSize: 11, fill: "#8892b0" }}
                        tickFormatter={(v: number) => v.toString()}
                        label={{
                          value: xAxisMode === "volume" ? "veh/h" : "veh/s",
                          position: "insideBottom",
                          offset: -4,
                          fill: "#8892b0",
                          fontSize: 11,
                        }}
                      />
                      <YAxis tick={{ fontSize: 11, fill: "#8892b0" }} />
                      <Tooltip
                        content={
                          <CustomTooltip unit=" veh" xMode={xAxisMode} />
                        }
                      />
                      <Legend wrapperStyle={{ fontSize: 12, paddingTop: 4 }} />
                      {crossover && xAxisMode === "volume" && (
                        <ReferenceLine
                          x={crossover}
                          stroke="#ffd93d"
                          strokeDasharray="4 3"
                        />
                      )}
                      <Line
                        type="monotone"
                        dataKey="signalQueue"
                        name="Fixed-Time Signal"
                        stroke="#4d96ff"
                        strokeWidth={2.5}
                        dot={{ r: 4, fill: "#4d96ff" }}
                        activeDot={{ r: 6 }}
                      />
                      <Line
                        type="monotone"
                        dataKey="roundaboutQueue"
                        name="Modern Roundabout"
                        stroke="#2ecc40"
                        strokeWidth={2.5}
                        dot={{ r: 4, fill: "#2ecc40" }}
                        activeDot={{ r: 6 }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="chart-empty">No telemetry data recorded</div>
                )}
              </div>
            )}
          </div>

          {/* ── Summary Table ─────────────────────────── */}
          <div className="sweep-summary-table-wrapper">
            <div className="table-header-controls">
              <h4>Volume Sweep Results: {activeSession.name}</h4>
              <div className="table-filter-group">
                <span className="filter-label">Filter Winner:</span>
                <button
                  type="button"
                  className={`table-filter-btn ${filterWinner === "all" ? "active" : ""}`}
                  onClick={() => {
                    setFilterWinner("all");
                  }}
                >
                  All ({activeSession.runs.length.toString()})
                </button>
                <button
                  type="button"
                  className={`table-filter-btn ${filterWinner === "roundabout" ? "active" : ""}`}
                  onClick={() => {
                    setFilterWinner("roundabout");
                  }}
                >
                  🔄 Roundabout ({roundaboutWins.toString()})
                </button>
                <button
                  type="button"
                  className={`table-filter-btn ${filterWinner === "signal" ? "active" : ""}`}
                  onClick={() => {
                    setFilterWinner("signal");
                  }}
                >
                  🚦 Signal ({signalWins.toString()})
                </button>
              </div>
            </div>

            <div className="table-scroll-container">
              <table>
                <thead>
                  <tr>
                    <th>Rate (veh/s)</th>
                    <th>Vol (veh/h)</th>
                    <th>Sig Delay (s)</th>
                    <th>Rnd Delay (s)</th>
                    <th>Sig Tput</th>
                    <th>Rnd Tput</th>
                    <th>Sig Queue</th>
                    <th>Rnd Queue</th>
                    <th>Winner</th>
                    <th>Δ Delay</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredRuns.map((run) => (
                    <tr key={run.arrivalRate}>
                      <td>
                        <strong>{run.arrivalRate.toFixed(2)}</strong>
                      </td>
                      <td>{run.hourlyVolumeVehPerHour.toLocaleString()}</td>
                      <td>{run.signal.delay.toFixed(2)}</td>
                      <td>{run.roundabout.delay.toFixed(2)}</td>
                      <td>{run.signal.throughput.toString()}</td>
                      <td>{run.roundabout.throughput.toString()}</td>
                      <td>{run.signal.queue.toFixed(1)}</td>
                      <td>{run.roundabout.queue.toFixed(1)}</td>
                      <td>
                        <span
                          className={
                            run.winner === "roundabout"
                              ? "winner-roundabout"
                              : run.winner === "signal"
                                ? "winner-signal"
                                : "winner-tie"
                          }
                        >
                          {run.winner === "roundabout"
                            ? "🔄 Roundabout"
                            : run.winner === "signal"
                              ? "🚦 Signal"
                              : "— Tie"}
                        </span>
                      </td>
                      <td
                        style={{
                          fontWeight: 600,
                          color:
                            run.delayDeltaPercent > 0
                              ? "#2ecc40"
                              : run.delayDeltaPercent < 0
                                ? "#ff6b6b"
                                : "#888",
                        }}
                      >
                        {run.delayDeltaPercent > 0 ? "+" : ""}
                        {run.delayDeltaPercent.toFixed(1)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
};
