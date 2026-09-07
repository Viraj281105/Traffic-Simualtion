/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { VolumeAnalysisDashboard } from "../components/VolumeAnalysisDashboard";

// ── Mock config ────────────────────────────────────────────────────────────

vi.mock("../config", () => ({ API_BASE_URL: "http://localhost:8000" }));

// ── Helpers ────────────────────────────────────────────────────────────────

const makeSweepRun = (rate: number, sigDelay: number, rndDelay: number) => ({
  arrivalRate: rate,
  hourlyVolumeVehPerHour: Math.round(rate * 3600 * 4),
  winner: rndDelay < sigDelay ? "roundabout" : "signal",
  delayDeltaPercent: ((rndDelay - sigDelay) / Math.max(sigDelay, 0.01)) * 100,
  signal: { delay: sigDelay, throughput: 100, queue: 2 },
  roundabout: { delay: rndDelay, throughput: 95, queue: 1.5 },
});

const MOCK_SESSION = {
  sessionId: "abc123",
  name: "Test Sweep",
  duration: 30,
  randomSeed: 42,
  curves: {
    rates: [0.1, 0.3, 0.5],
    volumesVehPerHour: [360, 1080, 1800],
    signal: {
      delays: [5, 8, 14],
      throughputs: [100, 95, 80],
      queues: [1, 3, 7],
    },
    roundabout: {
      delays: [3, 9, 15],
      throughputs: [105, 90, 75],
      queues: [0.5, 2.5, 8],
    },
    crossoverArrivalRate: 0.3,
    crossoverHourlyVolume: 1080,
  },
  runs: [
    makeSweepRun(0.1, 5, 3),
    makeSweepRun(0.3, 8, 9),
    makeSweepRun(0.5, 14, 15),
  ],
};

const MOCK_SWEEPS_LIST = [
  { id: "abc123", name: "Test Sweep", created_at: "2026-09-01T12:00:00Z" },
];

// ── Tests ──────────────────────────────────────────────────────────────────

describe("VolumeAnalysisDashboard", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  it("renders the trigger panel with Run Sweep button", () => {
    // Return empty sweep list
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify([]), { status: 200 }),
    );

    render(<VolumeAnalysisDashboard />);
    expect(
      screen.getByText(/Run Volume Sweep Experiment/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Run Sweep/i }),
    ).toBeInTheDocument();
  });

  it("shows saved sweeps after loading", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify(MOCK_SWEEPS_LIST), { status: 200 }),
    );

    render(<VolumeAnalysisDashboard />);

    await waitFor(() =>
      expect(screen.getByText("Test Sweep")).toBeInTheDocument(),
    );
    expect(screen.getByText(/Saved Sweeps/i)).toBeInTheDocument();
  });

  it("displays crossover badge when a sweep session is active", async () => {
    // First fetch: sweep list; second fetch (loadSweep): session data
    vi.mocked(fetch)
      .mockResolvedValueOnce(
        new Response(JSON.stringify(MOCK_SWEEPS_LIST), { status: 200 }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(MOCK_SESSION), { status: 200 }),
      );

    render(<VolumeAnalysisDashboard />);

    // Click saved sweep item after it appears
    await waitFor(() =>
      expect(screen.getByText("Test Sweep")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByText("Test Sweep"));

    await waitFor(() =>
      expect(
        screen.getByText(/Critical Saturation Crossover/i),
      ).toBeInTheDocument(),
    );
    expect(screen.getAllByText(/1,080/).length).toBeGreaterThanOrEqual(1);
  });

  it("shows error message on failed sweep run", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(new Response(JSON.stringify([]), { status: 200 }))
      .mockResolvedValueOnce(
        new Response("error", {
          status: 500,
          statusText: "Internal Server Error",
        }),
      );

    render(<VolumeAnalysisDashboard />);

    fireEvent.click(screen.getByRole("button", { name: /Run Sweep/i }));

    await waitFor(() =>
      expect(screen.getByText(/HTTP 500/i)).toBeInTheDocument(),
    );
  });

  it("disables Run Sweep button while running", async () => {
    // List loads fine, sweep call hangs
    vi.mocked(fetch)
      .mockResolvedValueOnce(new Response(JSON.stringify([]), { status: 200 }))
      .mockImplementationOnce(() => new Promise(() => undefined)); // never resolves

    render(<VolumeAnalysisDashboard />);

    const btn = screen.getByRole("button", { name: /Run Sweep/i });
    fireEvent.click(btn);

    await waitFor(() => expect(btn).toBeDisabled());
  });

  it("renders summary table rows for each run", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(
        new Response(JSON.stringify(MOCK_SWEEPS_LIST), { status: 200 }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(MOCK_SESSION), { status: 200 }),
      );

    render(<VolumeAnalysisDashboard />);

    await waitFor(() =>
      expect(screen.getByText("Test Sweep")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByText("Test Sweep"));

    // The 3 run rows (one per arrival rate)
    await waitFor(() => {
      const rows = screen.getAllByText(/Roundabout|Signal|Tie/);
      expect(rows.length).toBeGreaterThanOrEqual(3);
    });
  });
});
