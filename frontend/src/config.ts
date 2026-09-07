/**
 * Application network configuration.
 *
 * Automatically detects whether to use relative paths (when behind Nginx or Vite proxy),
 * explicit environment variables (VITE_API_URL / VITE_WS_URL), or falls back to
 * localhost:8000 for standalone environments.
 */

const isBrowser = typeof window !== "undefined";

/**
 * REST API base URL (empty string for relative path in browser, or custom URL).
 */
export const API_BASE_URL: string =
  (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") ??
  (isBrowser ? "" : "http://localhost:8000");

/**
 * WebSocket base URL (e.g. ws://localhost:5173 or ws://ec2-ip).
 */
export const WS_BASE_URL: string =
  (import.meta.env.VITE_WS_URL as string | undefined)?.replace(/\/$/, "") ??
  (isBrowser
    ? `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}`
    : "ws://localhost:8000");
