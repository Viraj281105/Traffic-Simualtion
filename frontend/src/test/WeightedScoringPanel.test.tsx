/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { WeightedScoringPanel } from "../components/WeightedScoringPanel";
import { DEFAULT_WEIGHTS } from "../types/scoring";
import { RunningMetrics } from "../types/simulation";

describe("WeightedScoringPanel", () => {
  const mockSignalMetrics: RunningMetrics = {
    averageWaitTime: 24.5,
    throughput: 120,
    throughputRate: 1.2,
    currentQueueLengths: { north: 3, south: 2, east: 1, west: 0 },
    maxQueueLength: 6,
    averageQueueLength: 3.2,
    totalStops: 40,
    averageStopsPerVehicle: 1.8,
    speedVarianceIndex: 0.15,
    travelTimeReliability: 0.85,
    idleOpportunityLoss: 0.12,
    directionalFairnessIndex: 0.72,
    activeVehicleCount: 15,
    totalVehiclesSpawned: 150,
    averageTravelSpeed: 9.5,
    queueStabilityIndex: 0.8,
    congestionRecoveryTime: 12.0,
    spaceFootprintConsumed: 450.0,
    intersectionUtilization: 0.65,
    criticalSaturationVolume: 1200,
  };

  const mockRoundaboutMetrics: RunningMetrics = {
    averageWaitTime: 12.3,
    throughput: 145,
    throughputRate: 1.8,
    currentQueueLengths: { north: 1, south: 1, east: 0, west: 0 },
    maxQueueLength: 3,
    averageQueueLength: 1.1,
    totalStops: 10,
    averageStopsPerVehicle: 0.4,
    speedVarianceIndex: 0.08,
    travelTimeReliability: 0.94,
    idleOpportunityLoss: 0.04,
    directionalFairnessIndex: 0.91,
    activeVehicleCount: 8,
    totalVehiclesSpawned: 155,
    averageTravelSpeed: 11.2,
    queueStabilityIndex: 0.95,
    congestionRecoveryTime: 4.0,
    spaceFootprintConsumed: 500.0,
    intersectionUtilization: 0.55,
    criticalSaturationVolume: 1400,
  };

  it("renders scoring panel with winner banner and default weights", () => {
    render(
      <WeightedScoringPanel
        metricsSignal={mockSignalMetrics}
        metricsRoundabout={mockRoundaboutMetrics}
        weights={DEFAULT_WEIGHTS}
        onWeightsChange={vi.fn()}
      />,
    );

    expect(
      screen.getByText(/Custom Weighted Scoring Model/i),
    ).toBeInTheDocument();
    expect(screen.getByText("Overall Scoring Winner")).toBeInTheDocument();
    expect(screen.getByText("Modern Roundabout")).toBeInTheDocument();
    expect(screen.getByText("Average Wait Time")).toBeInTheDocument();
    expect(screen.getByText("Throughput Volume")).toBeInTheDocument();
    expect(screen.getByText("Queue Clearance")).toBeInTheDocument();
    expect(screen.getByText("Directional Fairness")).toBeInTheDocument();
  });

  it("changes weight presets when preset buttons are clicked", () => {
    const onWeightsChange = vi.fn();
    render(
      <WeightedScoringPanel
        metricsSignal={mockSignalMetrics}
        metricsRoundabout={mockRoundaboutMetrics}
        weights={DEFAULT_WEIGHTS}
        onWeightsChange={onWeightsChange}
      />,
    );

    const highThroughputBtn = screen.getByRole("button", {
      name: /High Throughput/i,
    });
    fireEvent.click(highThroughputBtn);

    expect(onWeightsChange).toHaveBeenCalledWith(
      expect.objectContaining({
        weightThroughput: 50,
      }),
    );
  });

  it("allows individual slider adjustments and invokes onWeightsChange", () => {
    const onWeightsChange = vi.fn();
    render(
      <WeightedScoringPanel
        metricsSignal={mockSignalMetrics}
        metricsRoundabout={mockRoundaboutMetrics}
        weights={DEFAULT_WEIGHTS}
        onWeightsChange={onWeightsChange}
      />,
    );

    const sliders = screen.getAllByRole("slider");
    expect(sliders.length).toBeGreaterThanOrEqual(4);

    // Change first slider (Wait Time)
    fireEvent.change(sliders[0], { target: { value: "45" } });
    expect(onWeightsChange).toHaveBeenCalledWith(
      expect.objectContaining({
        weightWaitTime: 45,
      }),
    );
  });
});
