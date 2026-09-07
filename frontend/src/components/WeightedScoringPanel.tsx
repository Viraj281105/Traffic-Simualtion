import React, { useMemo } from "react";
import type { RunningMetrics } from "../types/simulation";
import type { ScoringWeights } from "../types/scoring";
import { DEFAULT_WEIGHTS, computeWeightedScore } from "../types/scoring";
import "./WeightedScoringPanel.css";

interface WeightedScoringPanelProps {
  metricsSignal: RunningMetrics | undefined;
  metricsRoundabout: RunningMetrics | undefined;
  weights: ScoringWeights;
  onWeightsChange: (newWeights: ScoringWeights) => void;
}

export const WeightedScoringPanel: React.FC<WeightedScoringPanelProps> = ({
  metricsSignal,
  metricsRoundabout,
  weights,
  onWeightsChange,
}) => {
  const scoreSignal = useMemo(
    () => computeWeightedScore(metricsSignal, weights),
    [metricsSignal, weights],
  );
  const scoreRoundabout = useMemo(
    () => computeWeightedScore(metricsRoundabout, weights),
    [metricsRoundabout, weights],
  );

  const winner = useMemo(() => {
    if (scoreSignal === scoreRoundabout) return { name: "Tie", advantage: 0 };
    if (scoreRoundabout > scoreSignal) {
      const adv =
        scoreSignal > 0
          ? ((scoreRoundabout - scoreSignal) / scoreSignal) * 100
          : 0;
      return {
        name: "Modern Roundabout",
        advantage: Math.round(adv * 10) / 10,
      };
    }
    const adv =
      scoreRoundabout > 0
        ? ((scoreSignal - scoreRoundabout) / scoreRoundabout) * 100
        : 0;
    return { name: "Fixed-Time Signal", advantage: Math.round(adv * 10) / 10 };
  }, [scoreSignal, scoreRoundabout]);

  const handleSlider = (key: keyof ScoringWeights, val: number) => {
    onWeightsChange({
      ...weights,
      [key]: val,
    });
  };

  const applyPreset = (preset: ScoringWeights) => {
    onWeightsChange(preset);
  };

  const sumScores = scoreSignal + scoreRoundabout;
  const pctSig = sumScores > 0 ? (scoreSignal / sumScores) * 100 : 50;
  const pctRound = sumScores > 0 ? (scoreRoundabout / sumScores) * 100 : 50;

  return (
    <div className="weighted-scoring-card">
      <div className="scoring-header">
        <div className="scoring-title-group">
          <div className="scoring-title">
            <span>⚖️ Custom Weighted Scoring Model</span>
          </div>
          <div className="scoring-subtitle">
            Fine-tune criteria priorities to determine the overall operational
            winner
          </div>
        </div>

        <div className="scoring-presets">
          <button
            type="button"
            className="preset-btn"
            onClick={() => {
              applyPreset(DEFAULT_WEIGHTS);
            }}
          >
            ⚖️ Balanced
          </button>
          <button
            type="button"
            className="preset-btn"
            onClick={() => {
              applyPreset({
                weightWaitTime: 15,
                weightThroughput: 50,
                weightQueue: 15,
                weightFairness: 10,
                weightStops: 10,
              });
            }}
          >
            🚦 High Throughput
          </button>
          <button
            type="button"
            className="preset-btn"
            onClick={() => {
              applyPreset({
                weightWaitTime: 50,
                weightThroughput: 15,
                weightQueue: 15,
                weightFairness: 10,
                weightStops: 10,
              });
            }}
          >
            ⏱️ Min Delay
          </button>
          <button
            type="button"
            className="preset-btn"
            onClick={() => {
              applyPreset({
                weightWaitTime: 20,
                weightThroughput: 20,
                weightQueue: 20,
                weightFairness: 20,
                weightStops: 20,
              });
            }}
          >
            🛑 Smooth Flow
          </button>
        </div>
      </div>

      {/* Winner Banner */}
      <div className="winner-banner">
        <div className="winner-info">
          <span className="winner-trophy">🏆</span>
          <div>
            <div className="winner-label">Overall Scoring Winner</div>
            <div>
              <span className="winner-name">{winner.name}</span>
              {winner.advantage > 0 && (
                <span className="winner-advantage">
                  (+{winner.advantage.toString()}% lead)
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="scores-comparison">
          <div className="score-tag">
            <span className="score-tag-name">🚦 Signal Score</span>
            <span className="score-tag-val">
              {scoreSignal.toFixed(1)} / 100
            </span>
          </div>
          <div className="score-tag">
            <span className="score-tag-name">🔄 Roundabout Score</span>
            <span className="score-tag-val" style={{ color: "#3fb950" }}>
              {scoreRoundabout.toFixed(1)} / 100
            </span>
          </div>
        </div>
      </div>

      {/* Visual score comparative progress track */}
      <div className="scores-progress-wrapper">
        <div className="scores-progress-labels">
          <span>Signal ({pctSig.toFixed(0)}%)</span>
          <span>Roundabout ({pctRound.toFixed(0)}%)</span>
        </div>
        <div className="scores-progress-track">
          <div
            className="progress-fill-signal"
            style={{ width: `${pctSig.toString()}%` }}
          />
          <div
            className="progress-fill-roundabout"
            style={{ width: `${pctRound.toString()}%` }}
          />
        </div>
      </div>

      {/* Weight sliders grid */}
      <div className="weights-grid">
        <div className="weight-control">
          <div className="weight-header">
            <span>Average Wait Time</span>
            <span className="weight-percent">
              {weights.weightWaitTime.toString()}%
            </span>
          </div>
          <input
            type="range"
            min="0"
            max="60"
            step="5"
            className="weight-slider"
            value={weights.weightWaitTime}
            onChange={(e) => {
              handleSlider("weightWaitTime", parseInt(e.target.value, 10));
            }}
          />
        </div>

        <div className="weight-control">
          <div className="weight-header">
            <span>Throughput Volume</span>
            <span className="weight-percent">
              {weights.weightThroughput.toString()}%
            </span>
          </div>
          <input
            type="range"
            min="0"
            max="60"
            step="5"
            className="weight-slider"
            value={weights.weightThroughput}
            onChange={(e) => {
              handleSlider("weightThroughput", parseInt(e.target.value, 10));
            }}
          />
        </div>

        <div className="weight-control">
          <div className="weight-header">
            <span>Queue Clearance</span>
            <span className="weight-percent">
              {weights.weightQueue.toString()}%
            </span>
          </div>
          <input
            type="range"
            min="0"
            max="50"
            step="5"
            className="weight-slider"
            value={weights.weightQueue}
            onChange={(e) => {
              handleSlider("weightQueue", parseInt(e.target.value, 10));
            }}
          />
        </div>

        <div className="weight-control">
          <div className="weight-header">
            <span>Directional Fairness</span>
            <span className="weight-percent">
              {weights.weightFairness.toString()}%
            </span>
          </div>
          <input
            type="range"
            min="0"
            max="50"
            step="5"
            className="weight-slider"
            value={weights.weightFairness}
            onChange={(e) => {
              handleSlider("weightFairness", parseInt(e.target.value, 10));
            }}
          />
        </div>

        <div className="weight-control">
          <div className="weight-header">
            <span>Stop Reductions</span>
            <span className="weight-percent">
              {weights.weightStops.toString()}%
            </span>
          </div>
          <input
            type="range"
            min="0"
            max="40"
            step="5"
            className="weight-slider"
            value={weights.weightStops}
            onChange={(e) => {
              handleSlider("weightStops", parseInt(e.target.value, 10));
            }}
          />
        </div>
      </div>
    </div>
  );
};
