/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ConfigurationSidebar } from "../components/ConfigurationSidebar";
import type { SimulationConfigValues } from "../types/config";
import { DEFAULT_CONFIG_VALUES } from "../types/config";

describe("ConfigurationSidebar", () => {
  const mockConfig: SimulationConfigValues = { ...DEFAULT_CONFIG_VALUES };

  it("does not render when isOpen is false", () => {
    const { container } = render(
      <ConfigurationSidebar
        isOpen={false}
        onClose={vi.fn()}
        config={mockConfig}
        onApply={vi.fn()}
      />,
    );
    expect(container.querySelector(".config-sidebar-panel")).toBeNull();
  });

  it("renders when isOpen is true with control sections and sliders", () => {
    render(
      <ConfigurationSidebar
        isOpen={true}
        onClose={vi.fn()}
        config={mockConfig}
        onApply={vi.fn()}
      />,
    );

    expect(screen.getByText(/Scenario Configuration/i)).toBeInTheDocument();
    expect(screen.getByText(/Traffic & Demand/i)).toBeInTheDocument();
    expect(screen.getByText(/Geometry & Widths/i)).toBeInTheDocument();
    expect(screen.getByText(/Fixed-Time Signal Timings/i)).toBeInTheDocument();
    expect(screen.getByText(/Roundabout Gap Acceptance/i)).toBeInTheDocument();
  });

  it("displays validation alert when invalid parameter entered", () => {
    render(
      <ConfigurationSidebar
        isOpen={true}
        onClose={vi.fn()}
        config={{
          ...mockConfig,
          criticalGap: 2.0,
          followUpTime: 3.5, // criticalGap < followUpTime -> error!
        }}
        onApply={vi.fn()}
      />,
    );

    expect(
      screen.getByText(
        /Critical gap must be strictly greater than follow-up headway time/,
      ),
    ).toBeInTheDocument();

    // Apply button should be disabled when there are errors
    const applyBtn = screen.getByRole("button", {
      name: /Fix Validation Errors/i,
    });
    expect(applyBtn).toBeDisabled();
  });

  it("calls onApply with updated configuration when applied", () => {
    const onApply = vi.fn();
    render(
      <ConfigurationSidebar
        isOpen={true}
        onClose={vi.fn()}
        config={mockConfig}
        onApply={onApply}
      />,
    );

    const applyBtn = screen.getByRole("button", {
      name: /Apply Configuration/i,
    });
    expect(applyBtn).not.toBeDisabled();
    fireEvent.click(applyBtn);

    expect(onApply).toHaveBeenCalledTimes(1);
    expect(onApply).toHaveBeenCalledWith(
      expect.objectContaining({
        lanes: mockConfig.lanes,
        arrivalRate: mockConfig.arrivalRate,
      }),
    );
  });

  it("resets form when Reset Defaults button is clicked", () => {
    const customConfig: SimulationConfigValues = {
      ...mockConfig,
      lanes: 4,
      arrivalRate: 0.9,
    };

    render(
      <ConfigurationSidebar
        isOpen={true}
        onClose={vi.fn()}
        config={customConfig}
        onApply={vi.fn()}
      />,
    );

    const resetBtn = screen.getByRole("button", { name: /Reset Defaults/i });
    fireEvent.click(resetBtn);

    // After reset, lanes should be reset to default (2)
    expect(screen.getByText("2 lanes")).toBeInTheDocument();
  });
});
