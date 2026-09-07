import type { RunningMetrics } from "./simulation";

export interface ScoringWeights {
  weightWaitTime: number;
  weightThroughput: number;
  weightQueue: number;
  weightFairness: number;
  weightStops: number;
}

export const DEFAULT_WEIGHTS: ScoringWeights = {
  weightWaitTime: 30,
  weightThroughput: 30,
  weightQueue: 15,
  weightFairness: 15,
  weightStops: 10,
};

export function computeWeightedScore(
  metrics: RunningMetrics | undefined,
  weights: ScoringWeights,
): number {
  if (!metrics) return 0;

  const totalWeights =
    weights.weightWaitTime +
    weights.weightThroughput +
    weights.weightQueue +
    weights.weightFairness +
    weights.weightStops;

  const wTotal = totalWeights > 0 ? totalWeights : 100;

  // Normalized components (0.0 to 1.0)
  const waitNorm = Math.max(0, 1 - metrics.averageWaitTime / 60.0);
  const tpNorm = Math.min(1, metrics.throughputRate / 2.0);
  const queueNorm = Math.max(0, 1 - metrics.averageQueueLength / 15.0);
  const fairnessNorm = Math.max(
    0,
    Math.min(1, metrics.directionalFairnessIndex),
  );
  const stopsNorm = Math.max(0, 1 - metrics.averageStopsPerVehicle / 5.0);

  const weightedSum =
    waitNorm * weights.weightWaitTime +
    tpNorm * weights.weightThroughput +
    queueNorm * weights.weightQueue +
    fairnessNorm * weights.weightFairness +
    stopsNorm * weights.weightStops;

  return Math.round((weightedSum / wTotal) * 1000) / 10;
}
