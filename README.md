# Traffic Intersection Control Comparison

> A comparative traffic simulation framework for evaluating **Fixed-Time Signal Control** vs. **Modern Roundabout Control** using multiple performance metrics.

## Overview

This project simulates and compares two intersection control strategies to determine which performs better under various traffic conditions. The simulation uses the **Intelligent Driver Model (IDM)** for vehicle physics and computes **10 performance metrics** across 5 categories.

### Control Strategies

| Strategy                      | Description                                                                         |
| ----------------------------- | ----------------------------------------------------------------------------------- |
| **Fixed-Time Traffic Signal** | Traditional signal-controlled intersection with fixed green/yellow/red phase cycles |
| **Modern Roundabout**         | Yield-at-entry circular intersection with gap acceptance behavior                   |

## Architecture

The project is organized as a monorepo with strict separation between Backend (Simulation Engine) and Frontend (Visualization Dashboard). Both communicate through shared data contracts.

```
├── [backend/](backend/README.md)       → Simulation engine, metrics, API (Python + FastAPI)
├── [frontend/](frontend/README.md)      → Dashboard, visualization, charts (React + TypeScript + Vite)
├── [shared/](shared/README.md)        → Data contracts, schemas, types (JSON Schema)
├── docs/          → Architecture specifications and project documentation
├── [scripts/](scripts/README.md)       → Development automation
└── examples/      → Sample configurations and outputs
```

See the [Architecture Documents](docs/architecture/) for detailed specifications.

## Architecture Documents

| #   | Document                                                                          | Description                              |
| --- | --------------------------------------------------------------------------------- | ---------------------------------------- |
| 01  | [Repository Architecture](docs/architecture/01-repository-architecture.md)        | Folder structure, ownership boundaries   |
| 02  | [Backend Architecture](docs/architecture/02-backend-architecture.md)              | Simulation engine module design          |
| 03  | [Frontend Architecture](docs/architecture/03-frontend-architecture.md)            | React dashboard design                   |
| 04  | [Shared Contract Layer](docs/architecture/04-shared-contract-layer.md)            | Contract ownership and versioning        |
| 05  | [Snapshot Contract](docs/architecture/05-snapshot-contract.md)                    | Real-time simulation state schema        |
| 06  | [Scenario Configuration](docs/architecture/06-scenario-configuration-contract.md) | Simulation configuration schema          |
| 07  | [Metric Contract](docs/architecture/07-metric-contract.md)                        | 10 metrics with mathematical definitions |
| 08  | [Communication Contract](docs/architecture/08-communication-contract.md)          | REST + WebSocket API design              |
| 09  | [Engineering Standards](docs/architecture/09-engineering-standards.md)            | Naming, Git workflow, code quality       |
| 10  | [Repository Bootstrap](docs/architecture/10-repository-bootstrap.md)              | Labels, milestones, initial issues       |

## Project Planning & Decisions

In addition to system specifications, the repository maintains planning, workflow, and decision history:

| Component                  | Directory                                            | Description                                                                    |
| -------------------------- | ---------------------------------------------------- | ------------------------------------------------------------------------------ |
| **Architecture Decisions** | [docs/decisions/](docs/decisions/)                   | The Architecture Decision Record (ADR) library tracking historic context.      |
| **Kanban & Roadmap**       | [docs/project-management/](docs/project-management/) | Milestones roadmap, label systems, and board configurations.                   |
| **GitHub Issues**          | [docs/issues/](docs/issues/)                         | 61 deconstructed atomic engineering tasks partitioned by implementation phase. |
| **Future Scope & Roadmap** | [docs/future-scope/](docs/future-scope/)             | Finalized roadmap & Google Maps-grade Digital Twin UI/UX innovation blueprints.|

## Performance Metrics

| Category                      | Metrics                                                                               | Description                                                   |
| ----------------------------- | ------------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| **Operational Efficiency**    | Average Wait Time, Throughput, Queue Length Statistics                                | Core delay and volume clearing statistics                     |
| **Traffic Flow Quality**      | Stop Count, Speed Variance Index, Travel Time Reliability, Average Travel Speed (ATS) | Vehicle comfort and flow stabilization markers                |
| **System Performance**        | Idle Opportunity Loss, Critical Saturation Volume, Intersection Utilization %         | Capacity and active service metrics                           |
| **Fairness & Stability**      | Directional Fairness Index (DFI), Queue Stability Index (QSI)                         | Variance across approaches and queues                         |
| **Physical Constraints**      | Space / Footprint Consumed                                                            | Land usage footprint comparison                               |
| **Overall Winner Evaluation** | **Master Efficiency Score**                                                           | Combined weighted normalization of all metrics (0.0 to 100.0) |

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- Docker & Docker Compose (optional, for containerized run)

### Running via Docker (Recommended)

Run the entire containerized system (FastAPI Simulation Engine + React Dashboard + Nginx Reverse Proxy + Persistent SQLite Data Volume):

```bash
docker compose up --build -d
```

- **Frontend Dashboard**: [http://localhost](http://localhost) (or [http://localhost:3000](http://localhost:3000))
- **Backend API & Swagger Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health Check**: [http://localhost/health](http://localhost/health)

To stop the containers:
```bash
docker compose down
```

### Running Natively for Local Development

You can run both services natively on your host machine:

- **Windows One-Click Launcher**: Double-click [`run.bat`](run.bat) or run `powershell -ExecutionPolicy Bypass -File .\start.ps1`
- **Manual Backend Setup**:
  ```bash
  cd backend
  python -m venv .venv
  .venv\Scripts\activate          # Windows
  # source .venv/bin/activate     # macOS/Linux
  pip install -r requirements.txt
  uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
  ```
- **Manual Frontend Setup**:
  ```bash
  cd frontend
  npm install
  npm run dev
  ```
  Visit [http://localhost:5173](http://localhost:5173).

### AWS Free Tier Cloud Deployment

For deploying the containerized application to an **AWS EC2 Free Tier (`t2.micro` / `t3.micro`)** instance with 2 GB Linux Swap, Nginx reverse proxying, and persistent storage, see:

📖 **[AWS Free Tier Deployment Guide](docs/deployment/AWS_FREE_TIER_DEPLOYMENT.md)**

## Team

| Developer      | Scope                                              |
| -------------- | -------------------------------------------------- |
| Viraj Jadhao   | Backend — Simulation Engine, Physics, Metrics, API |
| Khushi Kashyap | Frontend — Dashboard, Canvas, Charts, Playback     |

## Contributing

See [Engineering Standards](docs/architecture/09-engineering-standards.md) for naming conventions, commit message format, branch strategy, and code quality requirements.

## License

MIT License
