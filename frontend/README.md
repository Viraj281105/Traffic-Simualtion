# Traffic Simulation Frontend

The frontend is a TypeScript, React 19, and Vite application with a landing page and a simulation dashboard. The dashboard provides Canvas intersection views, comparative signal/roundabout playback, metrics, saved run history, volume analysis, validation, and replay controls. Current API payloads and routes are in [../docs/operations.md](../docs/operations.md).

**Owner:** Developer B
**Tech Stack:** React 19, TypeScript, Vite 8, HTML5 Canvas, Tailwind CSS, and Recharts

---

## Key Features

- **Dual Rendering Modes**:
  - **Intersection Map (`IntersectionMap.tsx`)**: High-fidelity top-down rendering of a 4-way intersection. Allows customization of lane counts per approach direction, lane widths, intersection size, and toggles for crosswalks, stop lines, and debug labels.
  - **Intersection Canvas (`IntersectionCanvas.tsx`)**: An alternative visualization module optimized to display a single-vehicle signalized intersection scenario, showing precise sensor markers, traffic light state transitions, and a telemetry info overlay.
- **Real-Time Telemetry & Controls**:
  - Starts, stops, and resets the simulation via standard HTTP POST controls.
  - Renders live simulation state parameters (Simulation Time, Tick counter, Vehicle State, Speed, Acceleration, Lead Distance, etc.).
- **Interactive Configuration Panel**: Adjust road geometry dynamically (number of lanes per direction, lane width, and intersection box size) and instantly see updates reflected on the canvas.

---

## Directory Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── IntersectionCanvas.tsx   # Canvas view for single-vehicle scenarios
│   │   └── IntersectionMap.tsx      # Configurable multi-lane intersection canvas
│   ├── hooks/
│   │   └── useSimulationPolling.ts  # Simulation state management & API polling hook
│   ├── types/
│   │   └── simulation.ts            # TypeScript definitions reflecting JSON Schemas
│   ├── App.tsx                      # Main layout, control panel, and view coordinators
│   ├── App.css                      # Styling for dashboard layout, forms, and badges
│   ├── index.css                    # Base page resets and typography
│   ├── main.tsx                     # React root mount point
│   └── vite-env.d.ts                # Vite environment definitions
├── eslint.config.js                 # ESLint check specifications
├── index.html                       # Base HTML shell
├── package.json                     # Node dependencies and execution scripts
├── tsconfig.json                    # TypeScript engine preferences
├── vite.config.ts                   # Vite bundler configurations
└── .env.example                     # Reference config environment variables
```

---

## Component Specifications

### 1. `IntersectionMap.tsx`

This component implements a custom-drawn HTML5 canvas. It centers the coordinate origin $(0,0)$ at the middle of the intersection and supports:

- **Approach Roads**: North, South, East, and West arms.
- **Variable Lane Configurations**:
  - `lanesNorth`, `lanesSouth`, `lanesEast`, `lanesWest`: Configure count of lanes on each respective side.
  - `laneWidth`: Width of each lane in meters (converted to pixels via `ppm` - pixels per meter).
- **Visual Overlays**:
  - Solid outer edges and yellow center dividers.
  - Dashed lane boundaries (`setLineDash([5, 15])`).
  - Optional zebra-striped crosswalks (`showCrosswalks`).
  - Solid white stop lines at entry boundaries (`showStopLines`).

### 2. `IntersectionCanvas.tsx`

Specifically tailored for single-vehicle tracking runs. Features:

- **Interactive Lights**: Visual representation of traffic lights corresponding to the current phase.
- **Info Overlay**: Draws live text directly on the canvas top-left corner displaying:
  - Velocity ($v$) in m/s
  - Acceleration ($a$) in $m/s^2$
  - Headway spacing ($s$) in meters
  - Active controller states

---

## Simulation Client Logic (`useSimulationPolling.ts`)

The React application interfaces with the Python backend via the `useSimulationPolling` hook:

- **Polling Loop**: Executes standard HTTP `GET` requests against the `/api/simulation/single-vehicle` endpoint at a constant frequency matching the simulation tickrate (10Hz / 100ms interval).
- **State Management**:
  - Automatically suspends polling if the returned simulation state is `"completed"`.
  - Captures and flags network connectivity errors and updates the UI accordingly.
- **REST Endpoints Mapping**:
  - `POST /api/simulation/start`: Transition the backend simulation to active loop and start local polling timer.
  - `POST /api/simulation/stop`: Transition the backend simulation to paused state and clear local polling timer.
  - `POST /api/simulation/reset`: Call the reset command on the backend and clear local vehicle/telemetry state.

---

## Setup & Running Guide

### Prerequisites

- Node.js 18 or newer
- npm or yarn package manager

### Development Server

1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install npm dependencies:
   ```bash
   npm install
   ```
3. Boot the Vite local dev server:
   ```bash
   npm run dev
   ```
  By default, the Vite dev server runs at `http://localhost:5173`; use `/` for the landing page and `/app.html` for the dashboard.

### Production Build

Compile and bundle source assets into highly optimized, minified static files ready for static serving:

```bash
npm run build
```

Build assets will be populated inside the `dist/` directory.

### Code Quality Checkpoints

Run code quality linters and formatting validators:

```bash
npm run lint           # Runs ESLint checks
npm run format         # Checks code formatting with Prettier
npm run format:fix     # Automatically formats code using Prettier
npm run type-check     # Runs TypeScript type check validation
```
