import { API_BASE_URL } from "../config";

const BASE = API_BASE_URL;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, init);
  if (!response.ok) {
    throw new Error(
      `HTTP ${response.status.toString()}: ${response.statusText}`,
    );
  }
  return response.json() as Promise<T>;
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    ...(body === undefined
      ? {}
      : {
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }),
  });
}

async function get<T>(path: string): Promise<T> {
  return request<T>(path);
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
  return get("/api/simulation/dual/status");
}

/** Get current simulation lifecycle status. */
export async function getSimulationStatus(): Promise<{
  status: string;
  message?: string;
}> {
  return get("/api/simulation/status");
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
  await post("/api/simulation/config", config);
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
  return post("/api/v1/study/sweeps/run", params);
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
  return post("/api/v1/study/validate/monte-carlo", params);
}

export async function saveReplay(payload: {
  name: string;
  config: Record<string, unknown>;
  metrics: Record<string, unknown>;
}): Promise<{ status: string; replay_id: string }> {
  return post("/api/v1/replays", payload);
}

export async function listReplays<T>(): Promise<T> {
  return get<T>("/api/v1/replays");
}

export async function deleteReplay(id: string): Promise<{ status: string }> {
  return request(`/api/v1/replays/${id}`, { method: "DELETE" });
}
