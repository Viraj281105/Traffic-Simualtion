import React, { useState } from "react";
import { API_BASE_URL } from "../config";
import "./ValidationDashboard.css";

// ── Types ──────────────────────────────────────────────────────────────────

interface StatResult {
  mean: number;
  std: number;
  min: number;
  max: number;
  ci95: number;
}

interface SeedRun {
  seed: number;
  signal: { delay: number; throughput: number; queue: number };
  roundabout: { delay: number; throughput: number; queue: number };
}

interface ValidationResult {
  numSeeds: number;
  signal: {
    delay: StatResult;
    throughput: StatResult;
    queue: StatResult;
  };
  roundabout: {
    delay: StatResult;
    throughput: StatResult;
    queue: StatResult;
  };
  comparison: {
    delay: { pValue: number | null; significant: boolean; cohensD: number };
    throughput: {
      pValue: number | null;
      significant: boolean;
      cohensD: number;
    };
    queue: { pValue: number | null; significant: boolean; cohensD: number };
  };
  seedRuns: SeedRun[];
}

const METRIC_KEYS = ["delay", "throughput", "queue"] as const;
type MetricKey = (typeof METRIC_KEYS)[number];

const METRIC_LABELS: Record<MetricKey, string> = {
  delay: "Avg Delay (s)",
  throughput: "Throughput (veh)",
  queue: "Avg Queue (veh)",
};

const SIGNAL_COLOR = "#4d96ff";
const ROUND_COLOR = "#2ecc40";

function getCohensDLabel(d: number): { label: string; color: string } {
  const absD = Math.abs(d);
  if (absD >= 0.8) return { label: "Large Effect", color: "#ffd93d" };
  if (absD >= 0.5) return { label: "Medium Effect", color: "#60a5fa" };
  if (absD >= 0.2) return { label: "Small Effect", color: "#94a3b8" };
  return { label: "Negligible", color: "#64748b" };
}

// ── CI Bar Component ────────────────────────────────────────────────────────

function CIBar({
  label,
  stat,
  color,
  maxMean,
}: {
  label: string;
  stat: StatResult;
  color: string;
  maxMean: number;
}) {
  const pct = maxMean > 0 ? (stat.mean / maxMean) * 100 : 0;
  const ciWidthPct = maxMean > 0 ? (stat.ci95 / maxMean) * 100 : 0;
  const ciLeft = Math.max(0, pct - ciWidthPct / 2);

  return (
    <div className="ci-row">
      <div className="ci-label-group">
        <span className="ci-label">{label}</span>
        <span className="ci-stat-sub">
          range: [{stat.min.toFixed(1)} – {stat.max.toFixed(1)}]
        </span>
      </div>
      <div className="ci-bar-track">
        <div
          className="ci-bar-fill"
          style={{
            width: `${pct.toString()}%`,
            background: color,
            opacity: 0.65,
          }}
        />
        <div
          className="ci-bar-ci"
          style={{
            left: `${ciLeft.toString()}%`,
            width: `${ciWidthPct.toString()}%`,
          }}
          title={`95% CI Error Margin: ±${stat.ci95.toFixed(2)}`}
        />
      </div>
      <div className="ci-values">
        <span className="ci-mean" style={{ color }}>
          {stat.mean.toFixed(2)}
        </span>
        <span className="ci-range">
          ± {stat.ci95.toFixed(2)} (σ={stat.std.toFixed(2)})
        </span>
      </div>
    </div>
  );
}

// ── Main Component ──────────────────────────────────────────────────────────

export const ValidationDashboard: React.FC = () => {
  const [numSeeds, setNumSeeds] = useState(5);
  const [duration, setDuration] = useState(30);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ValidationResult | null>(null);
  const [showMethodology, setShowMethodology] = useState(true);

  const runValidation = () => {
    setIsRunning(true);
    setError(null);
    fetch(`${API_BASE_URL}/api/v1/study/validate/monte-carlo`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ num_seeds: numSeeds, duration }),
    })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status.toString()}`);
        return r.json() as Promise<ValidationResult>;
      })
      .then((data) => {
        setResult(data);
        setIsRunning(false);
      })
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : "Validation failed");
        setIsRunning(false);
      });
  };

  const exportValidationCSV = () => {
    if (!result) return;
    const headers = [
      "Seed",
      "Signal Delay (s)",
      "Roundabout Delay (s)",
      "Signal Throughput",
      "Roundabout Throughput",
      "Signal Queue",
      "Roundabout Queue",
      "Seed Winner",
    ];

    const rows = result.seedRuns.map((r) => [
      r.seed.toString(),
      r.signal.delay.toFixed(2),
      r.roundabout.delay.toFixed(2),
      r.signal.throughput.toFixed(1),
      r.roundabout.throughput.toFixed(1),
      r.signal.queue.toFixed(2),
      r.roundabout.queue.toFixed(2),
      r.roundabout.delay < r.signal.delay ? "Roundabout" : "Signal",
    ]);

    const csvContent =
      "data:text/csv;charset=utf-8," +
      [headers.join(","), ...rows.map((e) => e.join(","))].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute(
      "download",
      `monte_carlo_validation_n${result.numSeeds.toString()}.csv`,
    );
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const allSignificant = result
    ? METRIC_KEYS.every((k) => result.comparison[k].significant)
    : false;

  const anySignificant = result
    ? METRIC_KEYS.some((k) => result.comparison[k].significant)
    : false;

  return (
    <div className="validation-dashboard">
      {/* ── Top Header Row ────────────────────────────── */}
      <div className="validation-header-row">
        <div className="header-title-group">
          <h2>🔬 Statistical Hypothesis & Validation Engine</h2>
          <p className="header-subtitle">
            Rigorous multi-seed stochastic validation comparing Signal vs.
            Roundabout across randomized arrivals. Confirms findings via
            Welch&apos;s two-sample z-test (α = 0.05) and Cohen&apos;s d effect
            sizes.
          </p>
        </div>
        <div className="header-actions">
          {result && (
            <button
              className="export-csv-btn"
              onClick={exportValidationCSV}
              title="Export validation data as CSV"
            >
              📥 Export CSV
            </button>
          )}
        </div>
      </div>

      {/* ── Trigger & Configuration Panel ──────────────── */}
      <div className="validation-trigger-panel">
        <div className="panel-header-badge">
          <h3>🔬 Monte Carlo Statistical Validation</h3>
          <span className="badge-pill">Stochastic Multi-Seed Engine</span>
        </div>

        <div className="validation-controls">
          <div className="validation-field">
            <label>Seeds (N)</label>
            <input
              type="number"
              min={2}
              max={30}
              value={numSeeds}
              onChange={(e) => {
                setNumSeeds(Number(e.target.value));
              }}
            />
          </div>

          <div className="validation-field">
            <label>Duration / Seed (s)</label>
            <input
              type="number"
              min={10}
              max={300}
              step={10}
              value={duration}
              onChange={(e) => {
                setDuration(Number(e.target.value));
              }}
            />
          </div>

          <div className="preset-shortcuts">
            <span className="preset-label">Test Rigor:</span>
            <button
              type="button"
              className="preset-tag"
              onClick={() => {
                setNumSeeds(3);
                setDuration(20);
              }}
            >
              ⚡ Quick (3 seeds, 20s)
            </button>
            <button
              type="button"
              className="preset-tag"
              onClick={() => {
                setNumSeeds(5);
                setDuration(30);
              }}
            >
              🧪 Standard (5 seeds, 30s)
            </button>
            <button
              type="button"
              className="preset-tag"
              onClick={() => {
                setNumSeeds(10);
                setDuration(60);
              }}
            >
              🔬 High Rigor (10 seeds, 60s)
            </button>
          </div>

          <button
            className="validation-run-btn"
            onClick={runValidation}
            disabled={isRunning}
          >
            {isRunning ? "⏳ Running…" : "▶ Run Validation"}
          </button>
        </div>

        {error && <div className="validation-error">⚠ {error}</div>}
        {isRunning && (
          <div className="validation-loading">
            <div className="spin-purple" />
            <span>
              Executing {numSeeds} randomized seeds × {duration}s — computing
              confidence intervals…
            </span>
          </div>
        )}
      </div>

      {/* ── Hypothesis & Methodology Guide ─────────────── */}
      <div className="methodology-card">
        <div className="methodology-header">
          <div className="methodology-title">
            <span>📐 Statistical Hypothesis Framework</span>
            <span className="confidence-pill">95% Confidence (α = 0.05)</span>
          </div>
          <button
            type="button"
            className="toggle-methodology-btn"
            onClick={() => {
              setShowMethodology((v) => !v);
            }}
          >
            {showMethodology ? "Collapse Guide" : "Expand Guide"}
          </button>
        </div>

        {showMethodology && (
          <div className="methodology-body">
            <div className="methodology-col">
              <span className="method-sub">Null Hypothesis (H₀)</span>
              <p>
                μ<sub>signal</sub> = μ<sub>roundabout</sub>. Performance
                differences are solely due to stochastic vehicle spawn jitter.
              </p>
            </div>
            <div className="methodology-col">
              <span className="method-sub">Alternative Hypothesis (H₁)</span>
              <p>
                μ<sub>signal</sub> ≠ μ<sub>roundabout</sub>. Real, reproducible
                architectural divergence verified (p &lt; 0.05).
              </p>
            </div>
            <div className="methodology-col">
              <span className="method-sub">Cohen&apos;s d Effect Size</span>
              <div className="effect-size-scale">
                <span className="scale-item neg">&lt;0.2 Negligible</span>
                <span className="scale-item sm">0.2–0.5 Small</span>
                <span className="scale-item med">0.5–0.8 Medium</span>
                <span className="scale-item lg">&gt;0.8 Large</span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ── Results ───────────────────────────────────── */}
      {result && !isRunning && (
        <>
          {/* Verdict */}
          <div
            className={`verdict-card ${
              anySignificant ? "significant" : "not-significant"
            }`}
          >
            <span className="verdict-icon">
              {allSignificant ? "✅" : anySignificant ? "⚠️" : "❌"}
            </span>
            <div className="verdict-text">
              <strong>
                {allSignificant
                  ? "Statistically Significant Difference Across All Metrics"
                  : anySignificant
                    ? "Partial Statistical Significance Detected"
                    : "No Statistically Significant Difference Detected"}
              </strong>
              <span>
                Based on {result.numSeeds} randomized Monte Carlo seeds with 95%
                confidence intervals (α = 0.05). Significance tags:{" "}
                <span className="significance-tags">
                  {METRIC_KEYS.map((k) => (
                    <span
                      key={k}
                      className={`sig-tag ${
                        result.comparison[k].significant ? "yes" : "no"
                      }`}
                    >
                      {METRIC_LABELS[k]}:{" "}
                      {result.comparison[k].significant
                        ? "Significant"
                        : "Not Significant"}
                    </span>
                  ))}
                </span>
              </span>
            </div>
          </div>

          {/* Per-metric CI stat cards (Widescreen 3-column grid) */}
          <div className="stats-grid">
            {METRIC_KEYS.map((key) => {
              const sigStat = result.signal[key];
              const rndStat = result.roundabout[key];
              const maxMean = Math.max(
                sigStat.mean + sigStat.ci95,
                rndStat.mean + rndStat.ci95,
                0.01,
              );
              const cmp = result.comparison[key];
              const effect = getCohensDLabel(cmp.cohensD);

              return (
                <div className="stat-card" key={key}>
                  <div className="stat-card-header">
                    <h4>{METRIC_LABELS[key]}</h4>
                    <span
                      className="effect-badge"
                      style={{ color: effect.color, borderColor: effect.color }}
                    >
                      {effect.label}
                    </span>
                  </div>

                  <div className="ci-comparison">
                    <CIBar
                      label="Fixed-Time Signal"
                      stat={sigStat}
                      color={SIGNAL_COLOR}
                      maxMean={maxMean}
                    />
                    <CIBar
                      label="Roundabout"
                      stat={rndStat}
                      color={ROUND_COLOR}
                      maxMean={maxMean}
                    />

                    <div className="metric-stats-footer">
                      <div className="stats-footer-left">
                        <span className="cohen-d">
                          Cohen&apos;s d = {cmp.cohensD.toFixed(3)}
                        </span>
                        {cmp.pValue !== null && (
                          <span className="p-val">
                            {" "}
                            · p ={" "}
                            {cmp.pValue < 0.001
                              ? "<0.001"
                              : cmp.pValue.toFixed(3)}
                          </span>
                        )}
                      </div>
                      <div className="stats-footer-right">
                        <strong
                          style={{
                            color: cmp.significant ? "#ffd93d" : "#64748b",
                          }}
                        >
                          {cmp.significant
                            ? "★ Significant"
                            : "Not Significant"}
                        </strong>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Per-seed runs table */}
          {result.seedRuns.length > 0 && (
            <div className="seed-runs-table-wrapper">
              <div className="runs-table-header">
                <h4>Per-Seed Raw Results ({result.numSeeds} seeds)</h4>
                <span className="table-meta-hint">
                  Stochastic seed trials executed in synchronized parallel pairs
                </span>
              </div>
              <div className="table-scroll-container">
                <table>
                  <thead>
                    <tr>
                      <th>Seed</th>
                      <th>Sig Delay (s)</th>
                      <th>Rnd Delay (s)</th>
                      <th>Δ Delay</th>
                      <th>Sig Tput</th>
                      <th>Rnd Tput</th>
                      <th>Sig Queue</th>
                      <th>Rnd Queue</th>
                      <th>Seed Winner</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.seedRuns.map((run) => {
                      const deltaDelay =
                        run.roundabout.delay - run.signal.delay;
                      const winner =
                        run.roundabout.delay < run.signal.delay
                          ? "roundabout"
                          : "signal";

                      return (
                        <tr key={run.seed}>
                          <td>
                            <strong>{run.seed}</strong>
                          </td>
                          <td>{run.signal.delay.toFixed(2)}</td>
                          <td>{run.roundabout.delay.toFixed(2)}</td>
                          <td
                            style={{
                              color:
                                deltaDelay < 0
                                  ? "#4ade80"
                                  : deltaDelay > 0
                                    ? "#f87171"
                                    : "#94a3b8",
                              fontWeight: 600,
                            }}
                          >
                            {deltaDelay < 0 ? "" : "+"}
                            {deltaDelay.toFixed(2)}s
                          </td>
                          <td>{run.signal.throughput.toFixed(1)}</td>
                          <td>{run.roundabout.throughput.toFixed(1)}</td>
                          <td>{run.signal.queue.toFixed(2)}</td>
                          <td>{run.roundabout.queue.toFixed(2)}</td>
                          <td>
                            <span
                              className={
                                winner === "roundabout"
                                  ? "seed-winner-rnd"
                                  : "seed-winner-sig"
                              }
                            >
                              {winner === "roundabout"
                                ? "🔄 Roundabout"
                                : "🚦 Signal"}
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
        </>
      )}
    </div>
  );
};
