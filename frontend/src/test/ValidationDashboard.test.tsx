/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ValidationDashboard } from "../components/ValidationDashboard";

// ── Mock config ────────────────────────────────────────────────────────────

vi.mock("../config", () => ({ API_BASE_URL: "http://localhost:8000" }));

// ── Helpers ────────────────────────────────────────────────────────────────

const makeStat = (mean: number) => ({
  mean,
  std: 1.2,
  min: mean - 2,
  max: mean + 2,
  ci95: 0.8,
});

const MOCK_VALIDATION = {
  numSeeds: 5,
  seeds: [1001, 1002, 1003, 1004, 1005],
  duration: 30,
  signal: {
    delay: makeStat(12),
    throughput: makeStat(80),
    queue: makeStat(4),
  },
  roundabout: {
    delay: makeStat(8),
    throughput: makeStat(90),
    queue: makeStat(2),
  },
  comparison: {
    delay: { pValue: 0.012, cohensD: 1.4, significant: true },
    throughput: { pValue: 0.045, cohensD: 0.9, significant: true },
    queue: { pValue: 0.08, cohensD: 0.6, significant: false },
  },
  seedRuns: [
    {
      seed: 1001,
      signal: { delay: 11, throughput: 79, queue: 3.8 },
      roundabout: { delay: 7, throughput: 91, queue: 1.9 },
    },
    {
      seed: 1002,
      signal: { delay: 13, throughput: 81, queue: 4.2 },
      roundabout: { delay: 9, throughput: 89, queue: 2.1 },
    },
  ],
  individualRuns: [],
};

// ── Tests ──────────────────────────────────────────────────────────────────

describe("ValidationDashboard", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  it("renders trigger panel with heading and button", () => {
    render(<ValidationDashboard />);
    expect(
      screen.getByText(/Monte Carlo Statistical Validation/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Run Validation/i }),
    ).toBeInTheDocument();
  });

  it("shows loading state after clicking Run Validation", async () => {
    vi.mocked(fetch).mockImplementationOnce(() => new Promise(() => undefined));

    render(<ValidationDashboard />);
    fireEvent.click(screen.getByRole("button", { name: /Run Validation/i }));

    await waitFor(() =>
      expect(screen.getByText(/Executing/i)).toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: /Running/i })).toBeDisabled();
  });

  it("renders verdict and metric stats after successful validation", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify(MOCK_VALIDATION), { status: 200 }),
    );

    const { container } = render(<ValidationDashboard />);
    fireEvent.click(screen.getByRole("button", { name: /Run Validation/i }));

    // Wait for verdict card to appear
    await waitFor(
      () => {
        const verdictCard = container.querySelector(".verdict-card");
        expect(verdictCard).not.toBeNull();
      },
      { timeout: 5000 },
    );

    // Metric labels should appear in stat card headings (multiple matches OK)
    await waitFor(() => {
      const h4s = container.querySelectorAll(".stat-card h4");
      expect(h4s.length).toBeGreaterThanOrEqual(3);
    });
  });

  it("renders per-seed raw results table", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify(MOCK_VALIDATION), { status: 200 }),
    );

    render(<ValidationDashboard />);
    fireEvent.click(screen.getByRole("button", { name: /Run Validation/i }));

    await waitFor(() =>
      expect(screen.getByText(/Per-Seed Raw Results/i)).toBeInTheDocument(),
    );
    // Seed values in the table
    expect(screen.getByText("1001")).toBeInTheDocument();
    expect(screen.getByText("1002")).toBeInTheDocument();
  });

  it("displays an error message on failed API call", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response("fail", { status: 503, statusText: "Service Unavailable" }),
    );

    render(<ValidationDashboard />);
    fireEvent.click(screen.getByRole("button", { name: /Run Validation/i }));

    await waitFor(() =>
      expect(screen.getByText(/HTTP 503/i)).toBeInTheDocument(),
    );
  });

  it("shows significance tags per metric", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify(MOCK_VALIDATION), { status: 200 }),
    );

    render(<ValidationDashboard />);
    fireEvent.click(screen.getByRole("button", { name: /Run Validation/i }));

    await waitFor(() => {
      // Two 'Significant' tags for delay+throughput, one 'Not Significant' for queue
      const sigTags = screen.getAllByText(/Significant/i);
      expect(sigTags.length).toBeGreaterThanOrEqual(3);
    });
  });

  it("shows Cohen's d values in metric cards", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify(MOCK_VALIDATION), { status: 200 }),
    );

    render(<ValidationDashboard />);
    fireEvent.click(screen.getByRole("button", { name: /Run Validation/i }));

    await waitFor(() => {
      expect(screen.getByText(/Cohen.*1\.4/)).toBeInTheDocument();
    });
  });
});
