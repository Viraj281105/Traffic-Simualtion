import "@testing-library/jest-dom/vitest";
import React from "react";
import { vi } from "vitest";

vi.mock("recharts", () => {
  return {
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) =>
      React.createElement(
        "div",
        { className: "recharts-responsive-container" },
        children,
      ),
    LineChart: ({ children }: { children: React.ReactNode }) =>
      React.createElement(
        "div",
        { className: "recharts-line-chart" },
        children,
      ),
    Line: () => React.createElement("div", { className: "recharts-line" }),
    XAxis: () => React.createElement("div", { className: "recharts-xaxis" }),
    YAxis: () => React.createElement("div", { className: "recharts-yaxis" }),
    CartesianGrid: () =>
      React.createElement("div", { className: "recharts-grid" }),
    Tooltip: () =>
      React.createElement("div", { className: "recharts-tooltip" }),
    Legend: () => React.createElement("div", { className: "recharts-legend" }),
    ReferenceLine: () =>
      React.createElement("div", { className: "recharts-reference-line" }),
  };
});
