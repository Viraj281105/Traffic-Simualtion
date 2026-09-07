import { API_BASE_URL } from "../config";

const BASE = API_BASE_URL;

async function post(path: string): Promise<unknown> {
  const res = await fetch(`${BASE}${path}`, { method: "POST" });
  if (!res.ok)
    throw new Error(`HTTP ${res.status.toString()}: ${res.statusText}`);
  return res.json();
}

async function get(path: string): Promise<unknown> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok)
    throw new Error(`HTTP ${res.status.toString()}: ${res.statusText}`);
  return res.json();
}

/** Start / resume the live simulation engine. */
export async function playSimulation(): Promise<void> {
  await post("/api/simulation/play");
}

/** Pause the live simulation engine. */
export async function pauseSimulation(): Promise<void> {
  await post("/api/simulation/pause");
}

/** Stop the live simulation engine. */
export async function stopSimulation(): Promise<void> {
  await post("/api/simulation/stop");
}

/** Start / resume the dual simulation engine. */
export async function playDualSimulation(): Promise<void> {
  await post("/api/simulation/dual/play");
}

/** Pause the dual simulation engine. */
export async function pauseDualSimulation(): Promise<void> {
  await post("/api/simulation/dual/pause");
}

/** Reset the dual simulation engine. */
export async function resetDualSimulation(): Promise<void> {
  await post("/api/simulation/dual/reset");
}

/** Get current dual simulation status. */
export async function getDualSimulationStatus(): Promise<{
  status: string;
  elapsed: number;
  tick: number;
}> {
  return get("/api/simulation/dual/status") as Promise<{
    status: string;
    elapsed: number;
    tick: number;
  }>;
}

/** Get current simulation lifecycle status. */
export async function getSimulationStatus(): Promise<{
  status: string;
  message?: string;
}> {
  return get("/api/simulation/status") as Promise<{
    status: string;
    message?: string;
  }>;
}

/** Send new configuration to backend. */
export async function updateSimulationConfig(config: {
  intersectionType: string;
  intersectionSize: number;
  laneWidth: number;
  lanesNorth: number;
  lanesSouth: number;
  lanesEast: number;
  lanesWest: number;
  arrivalRate?: number;
  duration?: number;
  randomSeed?: number;
  greenDuration?: number;
  yellowDuration?: number;
  allRedDuration?: number;
  criticalGap?: number;
  followUpTime?: number;
}): Promise<void> {
  const res = await fetch(`${BASE}/api/simulation/config`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status.toString()}: ${res.statusText}`);
  }
}

/** Reset/stop lockstep dual simulation. */
export async function stopDualSimulation(): Promise<void> {
  await post("/api/simulation/dual/reset");
}

// ── Study / Analytics API ──────────────────────────────────────────────────

/** Trigger a new volume sweep experiment. */
export async function runVolumeSweep(params: {
  duration?: number;
  random_seed?: number;
  time_step?: number;
}): Promise<unknown> {
  const res = await fetch(`${BASE}/api/v1/study/sweeps/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok)
    throw new Error(`HTTP ${res.status.toString()}: ${res.statusText}`);
  return res.json();
}

/** List saved sweep sessions. */
export async function listSweeps(limit = 20): Promise<unknown> {
  return get(`/api/v1/study/sweeps?limit=${limit.toString()}`);
}

/** Get a specific sweep session by ID. */
export async function getSweep(id: string): Promise<unknown> {
  return get(`/api/v1/study/sweeps/${id}`);
}

/** Run Monte Carlo statistical validation. */
export async function runMonteCarlo(params: {
  num_seeds?: number;
  duration?: number;
}): Promise<unknown> {
  const res = await fetch(`${BASE}/api/v1/study/validate/monte-carlo`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok)
    throw new Error(`HTTP ${res.status.toString()}: ${res.statusText}`);
  return res.json();
}
