# Project GitHub Issues Breakdown

This directory contains the historical atomic GitHub Issues used to plan the project. They are not a current implementation checklist; several describe proposed files or behavior that changed during development. Use [the operations guide](../operations.md) and tests for current behavior.

## Issue Documents Index

| Phase File | Description | Target Issues |
|------------|-------------|---------------|
| **[phase-0-setup-docs.md](file:///c:/VIRAJ/Internship/Traffic_Simulation_Project_1/docs/issues/phase-0-setup-docs.md)** | Repository setup, styling standards, linters, pre-commits, and document specs verification. | `ISSUE-001` to `ISSUE-008` |
| **[phase-1-backend-core.md](file:///c:/VIRAJ/Internship/Traffic_Simulation_Project_1/docs/issues/phase-1-backend-core.md)** | Clock classes, tick loops, lane/approach models, directed graph topologies, and IDM car physics. | `ISSUE-009` to `ISSUE-017` |
| **[phase-2-intersection-controllers.md](file:///c:/VIRAJ/Internship/Traffic_Simulation_Project_1/docs/issues/phase-2-intersection-controllers.md)** | Conflict zone bounding boxes, base ABC classes, signal timing states, and roundabout yield margins. | `ISSUE-018` to `ISSUE-025` |
| **[phase-3-metrics-snapshots.md](file:///c:/VIRAJ/Internship/Traffic_Simulation_Project_1/docs/issues/phase-3-metrics-snapshots.md)** | Aggregating indicators (wait times, stop counts, queue statistics, fairness indices) and snapshots serialization. | `ISSUE-026` to `ISSUE-034` |
| **[phase-4-api-frontend-foundation.md](file:///c:/VIRAJ/Internship/Traffic_Simulation_Project_1/docs/issues/phase-4-api-frontend-foundation.md)** | FastAPI configuration, WebSocket streams, React TS boots, REST clients, and socket managers. | `ISSUE-035` to `ISSUE-042` |
| **[phase-5-visualization-dashboard.md](file:///c:/VIRAJ/Internship/Traffic_Simulation_Project_1/docs/issues/phase-5-visualization-dashboard.md)** | 2D Canvas viewport controllers, road network vectors overlay, vehicle rotations, and dashboard layout tabs. | `ISSUE-043` to `ISSUE-052` |
| **[phase-6-testing-deployment-polish.md](file:///c:/VIRAJ/Internship/Traffic_Simulation_Project_1/docs/issues/phase-6-testing-deployment-polish.md)** | Pytest suites, vitest mocks, client-side interpolation, serialization profiling, Docker configs, and user guides. | `ISSUE-053` to `ISSUE-061` |

## Setup Automation

Instead of manually copying these issues, you can run the provided Python script:
```bash
python scripts/setup_github.py
```
This script parses these markdown files and logs all labels, milestones, and issues directly to your remote repository via the GitHub REST API!
*(See the [GitHub Management Package](file:///c:/VIRAJ/Internship/Traffic_Simulation_Project_1/docs/project-management/github-management-package.md) for full instructions)*.
