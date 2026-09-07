import React, { useState, useEffect, useCallback, useMemo } from "react";
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

type StudioTab = "curves" | "matrix" | "insights";
type MetricView = "all" | "delay" | "throughput" | "queue";
type XAxisMode = "volume" | "rate";

// ── HCM Level of Service (LOS) Helper ──────────────────────────────────────

interface LOSInfo {
  grade: "A" | "B" | "C" | "D" | "E" | "F";
  label: string;
  color: string;
  bg: string;
}

function getHCMLevelOfService(delaySeconds: number): LOSInfo {
  if (delaySeconds <= 10) {
    return { grade: "A", label: "Free Flow", color: "#10b981", bg: "rgba(16, 185, 129, 0.15)" };
  }
  if (delaySeconds <= 20) {
    return { grade: "B", label: "Stable Flow", color: "#34d399", bg: "rgba(52, 211, 153, 0.15)" };
  }
  if (delaySeconds <= 35) {
    return { grade: "C", label: "Moderate Delay", color: "#fbbf24", bg: "rgba(251, 191, 36, 0.15)" };
  }
  if (delaySeconds <= 55) {
    return { grade: "D", label: "Approaching Capacity", color: "#f97316", bg: "rgba(249, 115, 22, 0.15)" };
  }
  if (delaySeconds <= 80) {
    return { grade: "E", label: "At Capacity", color: "#ef4444", bg: "rgba(239, 68, 68, 0.15)" };
  }
  return { grade: "F", label: "Gridlock", color: "#f43f5e", bg: "rgba(244, 63, 94, 0.2)" };
}

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

  // Tab & View Controls
  const [activeTab, setActiveTab] = useState<StudioTab>("curves");
  const [showConfigDrawer, setShowConfigDrawer] = useState(false);

  // Sweep config form state
  const [sweepDuration, setSweepDuration] = useState(60);
  const [randomSeed, setRandomSeed] = useState(42);

  // Scrubber volume override state
  const [scrubberVolumeOverride, setScrubberVolumeOverride] = useState<number | null>(null);

  // Interactive UI view controls
  const [metricView, setMetricView] = useState<MetricView>("all");
  const [xAxisMode, setXAxisMode] = useState<XAxisMode>("volume");
  const [filterWinner, setFilterWinner] = useState<"all" | "roundabout" | "signal">("all");

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
        setScrubberVolumeOverride(null);
        setLoadingSession(false);
        setShowConfigDrawer(false);
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
        setScrubberVolumeOverride(null);
        setIsRunning(false);
        setShowConfigDrawer(false);
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

  // Scrubber min/max & closest run computation
  const minVol = activeSession?.runs[0]?.hourlyVolumeVehPerHour ?? 360;
  const maxVol = activeSession?.runs[activeSession.runs.length - 1]?.hourlyVolumeVehPerHour ?? 11520;

  const currentScrubberVolume = useMemo(() => {
    if (scrubberVolumeOverride !== null) return scrubberVolumeOverride;
    if (activeSession?.curves.crossoverHourlyVolume) {
      return activeSession.curves.crossoverHourlyVolume;
    }
    if (activeSession && activeSession.runs.length > 0) {
      const midIdx = Math.floor(activeSession.runs.length / 2);
      return activeSession.runs[midIdx].hourlyVolumeVehPerHour;
    }
    return 1440;
  }, [activeSession, scrubberVolumeOverride]);

  const currentScrubberRun = useMemo(() => {
    if (!activeSession || activeSession.runs.length === 0) return null;
    let closest = activeSession.runs[0];
    let minDiff = Math.abs(closest.hourlyVolumeVehPerHour - currentScrubberVolume);
    for (const run of activeSession.runs) {
      const diff = Math.abs(run.hourlyVolumeVehPerHour - currentScrubberVolume);
      if (diff < minDiff) {
        minDiff = diff;
        closest = run;
      }
    }
    return closest;
  }, [activeSession, currentScrubberVolume]);

  const maxDelayInRuns = useMemo(() => {
    if (!activeSession || activeSession.runs.length === 0) return 60;
    return Math.max(
      ...activeSession.runs.map((r) => Math.max(r.signal.delay, r.roundabout.delay)),
      10,
    );
  }, [activeSession]);

  return (
    <div className="volume-dashboard">
      {/* ── Top Executive Header ───────────────────────── */}
      <div className="volume-header-row">
        <div className="header-title-group">
          <div className="header-badge-row">
            <span className="header-mini-chip">Capacity Analysis Studio</span>
            <span className="header-version-chip">HCM 6th Ed.</span>
          </div>
          <h2>📈 Traffic Volume & Capacity Curve Analysis</h2>
          <p className="header-subtitle">
            Systematic sensitivity study comparing Fixed-Time Signals vs. Modern Roundabouts across demand tiers.
          </p>
        </div>

        <div className="header-actions">
          <button
            type="button"
            className={`config-toggle-btn ${showConfigDrawer ? "active" : ""}`}
            onClick={() => {
              setShowConfigDrawer((prev) => !prev);
            }}
            title="Configure duration, random seed, or load past sweep history"
          >
            ⚙️ Experiment Controls & History ({savedSweeps.length.toString()})
          </button>
          {activeSession && (
            <button
              type="button"
              className="export-csv-btn"
              onClick={exportCSV}
              title="Download study dataset as CSV"
            >
              📥 Export CSV
            </button>
          )}
        </div>
      </div>

      {/* ── Sweep Settings & History Panel (Inline or Modal Drawer) ── */}
      <div className={`sweep-top-controls-grid ${showConfigDrawer || !activeSession ? "open" : "collapsed"}`}>
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
                ⚡ 30s
              </button>
              <button
                type="button"
                className="preset-tag"
                onClick={() => {
                  setSweepDuration(60);
                }}
              >
                ⚖️ 60s
              </button>
              <button
                type="button"
                className="preset-tag"
                onClick={() => {
                  setSweepDuration(120);
                }}
              >
                🔬 120s
              </button>
            </div>

            <button
              type="button"
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
                Simulating 8 volume tiers across dual intersection models — computing capacity envelopes…
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
                No sweep history yet. Click <strong>Run Sweep</strong> to generate curves!
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
          {/* Executive KPI Cards */}
          <div className="volume-kpi-grid">
            <div className="kpi-card">
              <div className="kpi-top">
                <span className="kpi-icon-badge">🎯</span>
                <span className="kpi-category">Crossover Threshold</span>
              </div>
              <span className="kpi-label">Critical Saturation Point</span>
              <span className="kpi-value highlight-amber">
                {crossover
                  ? `${crossover.toLocaleString()} veh/h`
                  : "None Detected"}
              </span>
              <span className="kpi-hint">
                {crossover
                  ? "Signal becomes superior above this volume"
                  : "Roundabout maintained lower delay across all tiers"}
              </span>
            </div>

            <div className="kpi-card">
              <div className="kpi-top">
                <span className="kpi-icon-badge">🏆</span>
                <span className="kpi-category">Dominant Architecture</span>
              </div>
              <span className="kpi-label">Winning Strategy</span>
              <span
                className="kpi-value"
                style={{
                  color: roundaboutWins >= signalWins ? "#10b981" : "#38bdf8",
                }}
              >
                {roundaboutWins > signalWins
                  ? `Roundabout (${roundaboutWinPct.toString()}%)`
                  : signalWins > roundaboutWins
                    ? "Signal Control"
                    : "Balanced Parity"}
              </span>
              <span className="kpi-hint">
                Roundabout wins {roundaboutWins.toString()} of {totalRuns.toString()} demand brackets
              </span>
            </div>

            <div className="kpi-card">
              <div className="kpi-top">
                <span className="kpi-icon-badge">⏱️</span>
                <span className="kpi-category">Efficiency Peak</span>
              </div>
              <span className="kpi-label">Max Delay Reduction</span>
              <span className="kpi-value" style={{ color: "#10b981" }}>
                {activeSession.runs.length > 0
                  ? `${Math.abs(Math.min(...activeSession.runs.map((r) => r.delayDeltaPercent))).toFixed(1)}%`
                  : "N/A"}
              </span>
              <span className="kpi-hint">
                Observed under low to moderate demand
              </span>
            </div>

            <div className="kpi-card">
              <div className="kpi-top">
                <span className="kpi-icon-badge">🚦</span>
                <span className="kpi-category">Stress Boundary</span>
              </div>
              <span className="kpi-label">Peak Evaluated Volume</span>
              <span className="kpi-value highlight-blue">
                {activeSession.curves.volumesVehPerHour.length > 0
                  ? `${Math.max(...activeSession.curves.volumesVehPerHour).toLocaleString()} veh/h`
                  : "11,520 veh/h"}
              </span>
              <span className="kpi-hint">
                Highest capacity stress tier analyzed
              </span>
            </div>
          </div>

          {/* Compact High-Impact Crossover Banner */}
          {crossover ? (
            <div className="crossover-badge">
              <div className="crossover-compact-bar">
                <div className="crossover-compact-left">
                  <span className="crossover-sparkle">⭐</span>
                  <span className="crossover-text">
                    <strong>Critical Saturation Crossover: {crossover.toLocaleString()} veh/h</strong>
                  </span>
                  <span className="crossover-pill">Phase Transition</span>
                </div>
                <div className="crossover-compact-right">
                  <span className="crossover-tag tag-green">
                    &lt; {crossover.toLocaleString()} veh/h: Roundabout Advantage
                  </span>
                  <span className="crossover-tag tag-blue">
                    &gt; {crossover.toLocaleString()} veh/h: Signal Progress Stability
                  </span>
                </div>
              </div>
            </div>
          ) : (
            <div className="crossover-badge dominated-badge">
              <div className="crossover-compact-bar">
                <div className="crossover-compact-left">
                  <span className="crossover-sparkle">🔄</span>
                  <span className="crossover-text">
                    <strong style={{ color: "#10b981" }}>
                      Roundabout Dominates All Evaluated Volume Brackets
                    </strong>
                  </span>
                </div>
                <span className="crossover-tag tag-green">
                  Lower Delay Maintained Across All Rates
                </span>
              </div>
            </div>
          )}

          {/* ── Studio Navigation Tabs ─────────────────── */}
          <div className="studio-tabs-bar">
            <button
              type="button"
              className={`studio-tab-btn ${activeTab === "curves" ? "active" : ""}`}
              onClick={() => {
                setActiveTab("curves");
              }}
            >
              📈 Interactive Curves & Crossover Studio
            </button>
            <button
              type="button"
              className={`studio-tab-btn ${activeTab === "matrix" ? "active" : ""}`}
              onClick={() => {
                setActiveTab("matrix");
              }}
            >
              🔬 Head-to-Head Volume Matrix
            </button>
            <button
              type="button"
              className={`studio-tab-btn ${activeTab === "insights" ? "active" : ""}`}
              onClick={() => {
                setActiveTab("insights");
              }}
            >
              💡 Traffic Engineering & HCM LOS Guide
            </button>
          </div>

          {/* ── Interactive Volume Scrubber HUD ───────── */}
          {activeTab !== "insights" && currentScrubberRun && (
            <div className="volume-scrubber-card">
              <div className="scrubber-header">
                <div className="scrubber-title-group">
                  <span className="scrubber-title">🎛️ Interactive Demand Explorer</span>
                  <span className="scrubber-subtitle">
                    Scrub volume to inspect dynamic delay, HCM Level of Service, and winning advantage.
                  </span>
                </div>
                <div className="scrubber-winner-pill">
                  <span className="pill-prefix">Verdict:</span>
                  <span className={`pill-winner-name winner-${currentScrubberRun.winner}`}>
                    {currentScrubberRun.winner === "roundabout"
                      ? "🔄 Roundabout"
                      : currentScrubberRun.winner === "signal"
                        ? "🚦 Signal"
                        : "⚖️ Parity / Tie"}
                  </span>
                </div>
              </div>

              {/* Slider Track */}
              <div className="scrubber-slider-row">
                <span className="slider-bound-label">{minVol.toLocaleString()} veh/h</span>
                <div className="slider-input-wrapper">
                  <input
                    type="range"
                    min={minVol}
                    max={maxVol}
                    step={100}
                    value={currentScrubberVolume}
                    onChange={(e) => {
                      setScrubberVolumeOverride(Number(e.target.value));
                    }}
                    className="volume-slider-input"
                  />
                  {crossover && (
                    <div
                      className="slider-crossover-marker"
                      style={{
                        left: `${Math.max(0, Math.min(100, ((crossover - minVol) / (maxVol - minVol)) * 100)).toString()}%`,
                      }}
                      title={`Crossover: ${crossover.toLocaleString()} veh/h`}
                    >
                      <span className="marker-pin">📍</span>
                    </div>
                  )}
                </div>
                <span className="slider-bound-label">{maxVol.toLocaleString()} veh/h</span>
              </div>

              {/* Live HUD Cards */}
              <div className="scrubber-hud-grid">
                {/* Active Volume */}
                <div className="hud-metric-box">
                  <span className="hud-box-label">Current Demand</span>
                  <div className="hud-box-value-row">
                    <span className="hud-box-value highlight-cyan">
                      {currentScrubberRun.hourlyVolumeVehPerHour.toLocaleString()}
                    </span>
                    <span className="hud-box-unit">veh/h</span>
                  </div>
                  <span className="hud-box-sub">Rate: {currentScrubberRun.arrivalRate.toFixed(2)} veh/s</span>
                </div>

                {/* Signal Performance */}
                {(() => {
                  const sigLOS = getHCMLevelOfService(currentScrubberRun.signal.delay);
                  return (
                    <div className="hud-metric-box signal-theme">
                      <div className="hud-box-header-row">
                        <span className="hud-box-label">🚦 Fixed-Time Signal</span>
                        <span className="los-chip" style={{ color: sigLOS.color, background: sigLOS.bg }}>
                          LOS {sigLOS.grade}
                        </span>
                      </div>
                      <div className="hud-box-value-row">
                        <span className="hud-box-value">{currentScrubberRun.signal.delay.toFixed(1)}s</span>
                        <span className="hud-box-unit">delay</span>
                      </div>
                      <span className="hud-box-sub">
                        Tput: {currentScrubberRun.signal.throughput} veh · Q: {currentScrubberRun.signal.queue.toFixed(1)}
                      </span>
                    </div>
                  );
                })()}

                {/* Roundabout Performance */}
                {(() => {
                  const rndLOS = getHCMLevelOfService(currentScrubberRun.roundabout.delay);
                  return (
                    <div className="hud-metric-box roundabout-theme">
                      <div className="hud-box-header-row">
                        <span className="hud-box-label">🔄 Modern Roundabout</span>
                        <span className="los-chip" style={{ color: rndLOS.color, background: rndLOS.bg }}>
                          LOS {rndLOS.grade}
                        </span>
                      </div>
                      <div className="hud-box-value-row">
                        <span className="hud-box-value">{currentScrubberRun.roundabout.delay.toFixed(1)}s</span>
                        <span className="hud-box-unit">delay</span>
                      </div>
                      <span className="hud-box-sub">
                        Tput: {currentScrubberRun.roundabout.throughput} veh · Q: {currentScrubberRun.roundabout.queue.toFixed(1)}
                      </span>
                    </div>
                  );
                })()}

                {/* Delta / Verdict */}
                <div className="hud-metric-box delta-theme">
                  <span className="hud-box-label">Delay Margin</span>
                  <div className="hud-box-value-row">
                    <span
                      className="hud-box-value"
                      style={{
                        color:
                          currentScrubberRun.delayDeltaPercent > 0
                            ? "#10b981"
                            : currentScrubberRun.delayDeltaPercent < 0
                              ? "#f43f5e"
                              : "#94a3b8",
                      }}
                    >
                      {currentScrubberRun.delayDeltaPercent > 0 ? "+" : ""}
                      {currentScrubberRun.delayDeltaPercent.toFixed(1)}%
                    </span>
                  </div>
                  <span className="hud-box-sub">
                    {currentScrubberRun.winner === "roundabout"
                      ? "Roundabout saves driver delay"
                      : "Signal provides lane stability"}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* ── TAB 1: Curves & Crossover Studio ───────── */}
          {activeTab === "curves" && (
            <>
              {/* Interactive View Switcher Bar */}
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
              </div>

              {/* Charts Grid */}
              <div className={`charts-grid view-${metricView}`}>
                {/* Delay Chart */}
                {(metricView === "all" || metricView === "delay") && (
                  <div className="chart-card">
                    <div className="chart-card-header">
                      <div>
                        <h4>Average Delay vs. Traffic Volume</h4>
                        <span className="chart-subtitle">Vehicular control delay across volume tiers</span>
                      </div>
                      <span className="chart-metric-unit">s / vehicle</span>
                    </div>
                    {chartData.length > 0 ? (
                      <ResponsiveContainer
                        width="100%"
                        height={metricView === "all" ? 270 : 380}
                      >
                        <LineChart
                          data={chartData}
                          margin={{ top: 12, right: 24, bottom: 8, left: 4 }}
                        >
                          <CartesianGrid
                            strokeDasharray="3 3"
                            stroke="rgba(255,255,255,0.06)"
                          />
                          <XAxis
                            dataKey={xDataKey}
                            tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                            tickFormatter={(v: number) => v.toString()}
                            label={{
                              value: xAxisMode === "volume" ? "veh/h" : "veh/s",
                              position: "insideBottom",
                              offset: -4,
                              fill: "hsl(var(--muted-foreground))",
                              fontSize: 11,
                            }}
                          />
                          <YAxis tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} />
                          <Tooltip
                            content={<CustomTooltip unit="s" xMode={xAxisMode} />}
                          />
                          <Legend wrapperStyle={{ fontSize: 12, paddingTop: 4 }} />
                          {crossover && xAxisMode === "volume" && (
                            <ReferenceLine
                              x={crossover}
                              stroke="#f59e0b"
                              strokeDasharray="4 3"
                              strokeWidth={2}
                              label={{
                                value: `Crossover (${crossover.toLocaleString()})`,
                                position: "top",
                                fill: "#f59e0b",
                                fontSize: 11,
                              }}
                            />
                          )}
                          <Line
                            type="monotone"
                            dataKey="signalDelay"
                            name="Fixed-Time Signal"
                            stroke="#38bdf8"
                            strokeWidth={2.8}
                            dot={{ r: 4, fill: "#38bdf8" }}
                            activeDot={{ r: 7, stroke: "#7dd3fc", strokeWidth: 2 }}
                          />
                          <Line
                            type="monotone"
                            dataKey="roundaboutDelay"
                            name="Modern Roundabout"
                            stroke="#10b981"
                            strokeWidth={2.8}
                            dot={{ r: 4, fill: "#10b981" }}
                            activeDot={{ r: 7, stroke: "#34d399", strokeWidth: 2 }}
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
                      <div>
                        <h4>Throughput vs. Traffic Volume</h4>
                        <span className="chart-subtitle">Vehicles processed during simulation window</span>
                      </div>
                      <span className="chart-metric-unit">Completed Vehicles</span>
                    </div>
                    {chartData.length > 0 ? (
                      <ResponsiveContainer
                        width="100%"
                        height={metricView === "all" ? 270 : 380}
                      >
                        <LineChart
                          data={chartData}
                          margin={{ top: 12, right: 24, bottom: 8, left: 4 }}
                        >
                          <CartesianGrid
                            strokeDasharray="3 3"
                            stroke="rgba(255,255,255,0.06)"
                          />
                          <XAxis
                            dataKey={xDataKey}
                            tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                            tickFormatter={(v: number) => v.toString()}
                            label={{
                              value: xAxisMode === "volume" ? "veh/h" : "veh/s",
                              position: "insideBottom",
                              offset: -4,
                              fill: "hsl(var(--muted-foreground))",
                              fontSize: 11,
                            }}
                          />
                          <YAxis tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} />
                          <Tooltip
                            content={
                              <CustomTooltip unit=" veh" xMode={xAxisMode} />
                            }
                          />
                          <Legend wrapperStyle={{ fontSize: 12, paddingTop: 4 }} />
                          {crossover && xAxisMode === "volume" && (
                            <ReferenceLine
                              x={crossover}
                              stroke="#f59e0b"
                              strokeDasharray="4 3"
                              strokeWidth={2}
                            />
                          )}
                          <Line
                            type="monotone"
                            dataKey="signalThroughput"
                            name="Fixed-Time Signal"
                            stroke="#38bdf8"
                            strokeWidth={2.8}
                            dot={{ r: 4, fill: "#38bdf8" }}
                            activeDot={{ r: 7, stroke: "#7dd3fc", strokeWidth: 2 }}
                          />
                          <Line
                            type="monotone"
                            dataKey="roundaboutThroughput"
                            name="Modern Roundabout"
                            stroke="#10b981"
                            strokeWidth={2.8}
                            dot={{ r: 4, fill: "#10b981" }}
                            activeDot={{ r: 7, stroke: "#34d399", strokeWidth: 2 }}
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
                      <div>
                        <h4>Average Queue Length vs. Traffic Volume</h4>
                        <span className="chart-subtitle">Mean standing queue per approach lane</span>
                      </div>
                      <span className="chart-metric-unit">Average Vehicles</span>
                    </div>
                    {chartData.length > 0 ? (
                      <ResponsiveContainer
                        width="100%"
                        height={metricView === "all" ? 270 : 380}
                      >
                        <LineChart
                          data={chartData}
                          margin={{ top: 12, right: 24, bottom: 8, left: 4 }}
                        >
                          <CartesianGrid
                            strokeDasharray="3 3"
                            stroke="rgba(255,255,255,0.06)"
                          />
                          <XAxis
                            dataKey={xDataKey}
                            tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                            tickFormatter={(v: number) => v.toString()}
                            label={{
                              value: xAxisMode === "volume" ? "veh/h" : "veh/s",
                              position: "insideBottom",
                              offset: -4,
                              fill: "hsl(var(--muted-foreground))",
                              fontSize: 11,
                            }}
                          />
                          <YAxis tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} />
                          <Tooltip
                            content={
                              <CustomTooltip unit=" veh" xMode={xAxisMode} />
                            }
                          />
                          <Legend wrapperStyle={{ fontSize: 12, paddingTop: 4 }} />
                          {crossover && xAxisMode === "volume" && (
                            <ReferenceLine
                              x={crossover}
                              stroke="#f59e0b"
                              strokeDasharray="4 3"
                              strokeWidth={2}
                            />
                          )}
                          <Line
                            type="monotone"
                            dataKey="signalQueue"
                            name="Fixed-Time Signal"
                            stroke="#38bdf8"
                            strokeWidth={2.8}
                            dot={{ r: 4, fill: "#38bdf8" }}
                            activeDot={{ r: 7, stroke: "#7dd3fc", strokeWidth: 2 }}
                          />
                          <Line
                            type="monotone"
                            dataKey="roundaboutQueue"
                            name="Modern Roundabout"
                            stroke="#10b981"
                            strokeWidth={2.8}
                            dot={{ r: 4, fill: "#10b981" }}
                            activeDot={{ r: 7, stroke: "#34d399", strokeWidth: 2 }}
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    ) : (
                      <div className="chart-empty">No telemetry data recorded</div>
                    )}
                  </div>
                )}
              </div>
            </>
          )}

          {/* ── TAB 2: Head-to-Head Volume Matrix ──────── */}
          {activeTab === "matrix" && (
            <div className="sweep-summary-table-wrapper">
              <div className="table-header-controls">
                <div>
                  <h4>Volume Sweep Results: {activeSession.name}</h4>
                  <p className="table-subtitle">Comparative telemetry data with side-by-side delay bars & HCM Level of Service</p>
                </div>
                <div className="table-filter-group">
                  <span className="filter-label">Filter:</span>
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
                <table className="modern-telemetry-table">
                  <thead>
                    <tr>
                      <th>Demand Tier</th>
                      <th>Delay Comparison Bar</th>
                      <th>Signal Delay & LOS</th>
                      <th>Roundabout Delay & LOS</th>
                      <th>Throughput</th>
                      <th>Queues</th>
                      <th>Winner</th>
                      <th>Δ Delay</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredRuns.map((run) => {
                      const sigLOS = getHCMLevelOfService(run.signal.delay);
                      const rndLOS = getHCMLevelOfService(run.roundabout.delay);
                      const sigPct = Math.min(100, Math.round((run.signal.delay / maxDelayInRuns) * 100));
                      const rndPct = Math.min(100, Math.round((run.roundabout.delay / maxDelayInRuns) * 100));

                      return (
                        <tr key={run.arrivalRate}>
                          <td>
                            <div className="table-tier-col">
                              <strong>{run.hourlyVolumeVehPerHour.toLocaleString()} veh/h</strong>
                              <span className="table-tier-rate">{run.arrivalRate.toFixed(2)} veh/s</span>
                            </div>
                          </td>

                          {/* Visual Micro Delay Bar */}
                          <td className="delay-bar-cell">
                            <div className="dual-delay-bars">
                              <div className="bar-row">
                                <span className="bar-label">Sig</span>
                                <div className="bar-track">
                                  <div className="bar-fill sig-fill" style={{ width: `${sigPct.toString()}%` }} />
                                </div>
                              </div>
                              <div className="bar-row">
                                <span className="bar-label">Rnd</span>
                                <div className="bar-track">
                                  <div className="bar-fill rnd-fill" style={{ width: `${rndPct.toString()}%` }} />
                                </div>
                              </div>
                            </div>
                          </td>

                          {/* Signal Delay */}
                          <td>
                            <div className="delay-los-cell">
                              <span className="delay-val">{run.signal.delay.toFixed(2)}s</span>
                              <span className="los-chip mini" style={{ color: sigLOS.color, background: sigLOS.bg }}>
                                LOS {sigLOS.grade}
                              </span>
                            </div>
                          </td>

                          {/* Roundabout Delay */}
                          <td>
                            <div className="delay-los-cell">
                              <span className="delay-val">{run.roundabout.delay.toFixed(2)}s</span>
                              <span className="los-chip mini" style={{ color: rndLOS.color, background: rndLOS.bg }}>
                                LOS {rndLOS.grade}
                              </span>
                            </div>
                          </td>

                          {/* Throughput */}
                          <td>
                            <div className="table-multi-col">
                              <span>🚦 {run.signal.throughput}</span>
                              <span>🔄 {run.roundabout.throughput}</span>
                            </div>
                          </td>

                          {/* Queues */}
                          <td>
                            <div className="table-multi-col">
                              <span>🚦 {run.signal.queue.toFixed(1)}</span>
                              <span>🔄 {run.roundabout.queue.toFixed(1)}</span>
                            </div>
                          </td>

                          {/* Winner Badge */}
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

                          {/* Delta */}
                          <td>
                            <span
                              className="delta-pill"
                              style={{
                                color:
                                  run.delayDeltaPercent > 0
                                    ? "#10b981"
                                    : run.delayDeltaPercent < 0
                                      ? "#f43f5e"
                                      : "#94a3b8",
                                background:
                                  run.delayDeltaPercent > 0
                                    ? "rgba(16, 185, 129, 0.1)"
                                    : run.delayDeltaPercent < 0
                                      ? "rgba(244, 63, 94, 0.1)"
                                      : "rgba(148, 163, 184, 0.1)",
                              }}
                            >
                              {run.delayDeltaPercent > 0 ? "+" : ""}
                              {run.delayDeltaPercent.toFixed(1)}%
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ── TAB 3: Traffic Engineering Insights & Capacity Guide ─ */}
          {activeTab === "insights" && (
            <div className="engineering-insights-container">
              <div className="insights-header">
                <div>
                  <h4>🧠 Traffic Engineering Insights & Capacity Envelopes</h4>
                  <p className="insights-subtitle">
                    Theoretical principles explaining why roundabouts saturate and when traffic signals must be deployed according to Highway Capacity Manual (HCM) standards.
                  </p>
                </div>
              </div>

              <div className="insights-card-grid">
                <div className="insight-card-modern">
                  <div className="insight-card-top">
                    <span className="insight-card-icon">⚡</span>
                    <span className="insight-badge roundabout-badge">Low-Medium Volumes (&lt; Crossover)</span>
                  </div>
                  <h5>Continuous Gap-Acceptance Superiority</h5>
                  <p>
                    Modern Roundabouts completely eliminate lost time from yellow/all-red intervals. In low-to-moderate demand (below the critical crossover), circulating density is low, allowing drivers to execute yield and gap-acceptance without coming to a full halt. Vehicle throughput remains near capacity while queue buildup is negligible.
                  </p>
                  <div className="insight-stat-row">
                    <span className="stat-highlight">Up to 50%</span>
                    <span className="stat-desc">reduction in average vehicular delay vs. fixed signals</span>
                  </div>
                </div>

                <div className="insight-card-modern">
                  <div className="insight-card-top">
                    <span className="insight-card-icon">🛑</span>
                    <span className="insight-badge signal-badge">High Over-Capacity (&gt; Crossover)</span>
                  </div>
                  <h5>Circulating Ring Starvation & Lockup</h5>
                  <p>
                    When circulating demand exceeds critical density, entry vehicles encounter zero acceptable gaps. Queues spill backward along entrance approaches, leading to gridlock across adjacent legs. Fixed-Time Signals enforce deterministic cycle splits, forcefully rationing green time and guaranteeing clearance for cross-traffic.
                  </p>
                  <div className="insight-stat-row">
                    <span className="stat-highlight">Deterministic</span>
                    <span className="stat-desc">lane progression prevents circular cascade failure</span>
                  </div>
                </div>

                <div className="insight-card-modern">
                  <div className="insight-card-top">
                    <span className="insight-card-icon">🏛️</span>
                    <span className="insight-badge recommendation-badge">Civic Planning Takeaway</span>
                  </div>
                  <h5>Municipal Corridor Design Guidelines</h5>
                  <p>
                    {crossover
                      ? `For corridors exceeding ${crossover.toLocaleString()} veh/h peak design hourly volume (DHV), a multi-phase adaptive traffic signal or turbo-roundabout with slip lanes is mathematically required.`
                      : "For the evaluated volume ranges, modern roundabouts provide clear carbon emission reductions, lower fuel consumption, and higher safety margins over fixed-time signals."}
                  </p>
                  <div className="insight-stat-row">
                    <span className="stat-highlight">{crossover ? `${crossover.toLocaleString()} veh/h` : "Full Range"}</span>
                    <span className="stat-desc">planning design threshold for intersection selection</span>
                  </div>
                </div>
              </div>

              {/* HCM Level of Service Reference Table */}
              <div className="hcm-los-reference-box">
                <h5>📖 Highway Capacity Manual (HCM 6th Edition) Level of Service (LOS) Benchmarks</h5>
                <div className="los-grid-chips">
                  <div className="los-card-chip">
                    <span className="los-badge" style={{ color: "#10b981", background: "rgba(16, 185, 129, 0.15)" }}>LOS A</span>
                    <span className="los-time">≤ 10s delay</span>
                    <span className="los-condition">Free flow; progression is extremely high.</span>
                  </div>
                  <div className="los-card-chip">
                    <span className="los-badge" style={{ color: "#34d399", background: "rgba(52, 211, 153, 0.15)" }}>LOS B</span>
                    <span className="los-time">10 – 20s delay</span>
                    <span className="los-condition">Good progression; short cycle queues.</span>
                  </div>
                  <div className="los-card-chip">
                    <span className="los-badge" style={{ color: "#fbbf24", background: "rgba(251, 191, 36, 0.15)" }}>LOS C</span>
                    <span className="los-time">20 – 35s delay</span>
                    <span className="los-condition">Fair progression; noticeable vehicle queues.</span>
                  </div>
                  <div className="los-card-chip">
                    <span className="los-badge" style={{ color: "#f97316", background: "rgba(249, 115, 22, 0.15)" }}>LOS D</span>
                    <span className="los-time">35 – 55s delay</span>
                    <span className="los-condition">Noticeable congestion; high delay margin.</span>
                  </div>
                  <div className="los-card-chip">
                    <span className="los-badge" style={{ color: "#ef4444", background: "rgba(239, 68, 68, 0.15)" }}>LOS E</span>
                    <span className="los-time">55 – 80s delay</span>
                    <span className="los-condition">At or near physical capacity; long queues.</span>
                  </div>
                  <div className="los-card-chip">
                    <span className="los-badge" style={{ color: "#f43f5e", background: "rgba(244, 63, 94, 0.2)" }}>LOS F</span>
                    <span className="los-time">&gt; 80s delay</span>
                    <span className="los-condition">Breakdown & oversaturation; excessive queuing.</span>
                  </div>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
};
