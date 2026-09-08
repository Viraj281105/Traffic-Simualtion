# Deliverable 10 — Repository Bootstrap

> **Document Version:** 0.1.0
> **Last Updated:** 2026-07-23
> **Status:** Historical bootstrap specification
> **Owner:** Both Developers

---

## 1. README Structure

The root `README.md` should follow this structure:

```markdown
# Traffic Intersection Control Comparison

> A comparative traffic simulation framework for evaluating Fixed-Time Signal
> Control vs. Modern Roundabout Control using multiple performance metrics.

## Overview
Brief project description, goals, and what the two control strategies are.

## Architecture
High-level architecture diagram (embed pipeline overview image).
Link to docs/architecture/ for detailed specifications.

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- npm 9+

### Backend Setup
$ cd backend
$ python -m venv .venv
$ source .venv/bin/activate  (or .venv\Scripts\activate on Windows)
$ pip install -r requirements.txt
$ .venv/Scripts/python.exe -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

### Frontend Setup
$ cd frontend
$ npm install
$ npm run dev

## Project Structure
Brief folder tree showing top-level structure.

## Documentation
Links to all architecture documents in docs/architecture/.

## Metrics
Brief list of the 10 metrics being compared.

## Contributing
Link to engineering standards document.

## License
MIT License (or chosen license).
```

---

## 2. `.gitignore` Enhancements

The existing `.gitignore` covers Python. Add these sections for the frontend and shared layers:

### Node.js / React (add to existing .gitignore)

```gitignore
# Node.js
node_modules/
npm-debug.log*
yarn-debug.log*
yarn-error.log*
.pnpm-debug.log*

# Build outputs
frontend/dist/
frontend/build/
*.tsbuildinfo

# Environment files
.env.local
.env.development.local
.env.test.local
.env.production.local

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# OS files
.DS_Store
Thumbs.db
desktop.ini

# Simulation output (generated data)
output/
results/
*.sim.json
```

---

## 3. LICENSE Recommendation

**Recommended:** MIT License

**Rationale:**
- Simple and permissive
- Standard for academic/internship projects
- Allows future use in research publications
- No copyleft restrictions

---

## 4. GitHub Labels

### Category: Type

| Label | Color | Description |
|-------|-------|-------------|
| `type: feature` | `#0E8A16` (green) | New feature or enhancement |
| `type: bug` | `#D73A4A` (red) | Something isn't working |
| `type: documentation` | `#0075CA` (blue) | Documentation improvements |
| `type: refactor` | `#E4E669` (yellow) | Code restructuring (no behavior change) |
| `type: test` | `#BFD4F2` (light blue) | Test additions or fixes |
| `type: chore` | `#D4C5F9` (purple) | Build, CI, dependency updates |

### Category: Scope

| Label | Color | Description |
|-------|-------|-------------|
| `scope: backend` | `#1D3557` (dark blue) | Backend (simulation engine, API) |
| `scope: frontend` | `#E76F51` (orange) | Frontend (dashboard, visualization) |
| `scope: shared` | `#2D6A4F` (green) | Shared contracts and schemas |
| `scope: docs` | `#6C757D` (gray) | Documentation |
| `scope: ci-cd` | `#495057` (dark gray) | CI/CD and automation |

### Category: Priority

| Label | Color | Description |
|-------|-------|-------------|
| `priority: critical` | `#B60205` (dark red) | Must be fixed immediately |
| `priority: high` | `#D93F0B` (red-orange) | Important, address soon |
| `priority: medium` | `#FBCA04` (yellow) | Normal priority |
| `priority: low` | `#0E8A16` (green) | Nice to have |

### Category: Phase

| Label | Color | Description |
|-------|-------|-------------|
| `phase: 0` | `#C2E0C6` (light green) | Architecture and setup |
| `phase: 1` | `#BFD4F2` (light blue) | Core implementation |
| `phase: 2` | `#D4C5F9` (light purple) | Integration and comparison |
| `phase: 3` | `#FEF2C0` (light yellow) | Polish and final report |

### Category: Status

| Label | Color | Description |
|-------|-------|-------------|
| `status: blocked` | `#D73A4A` (red) | Blocked by another issue or decision |
| `status: in-review` | `#0075CA` (blue) | In code review |
| `status: needs-discussion` | `#FBCA04` (yellow) | Requires team discussion |

---

## 5. Milestones

| Milestone | Target Date | Description |
|-----------|-------------|-------------|
| `v0.1.0 — Architecture Complete` | End of Week 1 | Phase 0: All architecture docs, contracts, and repo skeleton |
| `v0.2.0 — Backend Core` | End of Week 2 | Simulation engine, IDM physics, basic snapshot emission |
| `v0.3.0 — Frontend Core` | End of Week 2 | Canvas rendering, WebSocket connection, basic dashboard |
| `v0.4.0 — Controllers` | End of Week 3 | Fixed-time signal and roundabout controllers implemented |
| `v0.5.0 — Metrics` | End of Week 3 | All 10 metrics computed and displayed |
| `v0.6.0 — Integration` | End of Week 4 | End-to-end simulation with comparison views |
| `v1.0.0 — Final Release` | End of Week 5 | Complete, tested, documented application |

---

## 6. Project Board

### Board: Development Pipeline

| Column | Purpose |
|--------|---------|
| **Backlog** | All open issues not yet prioritized |
| **To Do** | Prioritized for current sprint |
| **In Progress** | Actively being worked on |
| **In Review** | PR created, awaiting review |
| **Done** | Merged to develop or main |

---

## 7. Initial Issues (Phase 0)

### Architecture Issues

| # | Title | Labels | Assignee |
|---|-------|--------|----------|
| 1 | `[Shared] Define snapshot JSON Schema v1.0` | `scope: shared`, `phase: 0` | Both |
| 2 | `[Shared] Define configuration JSON Schema v1.0` | `scope: shared`, `phase: 0` | Both |
| 3 | `[Shared] Define metrics output JSON Schema v1.0` | `scope: shared`, `phase: 0` | Both |
| 4 | `[Shared] Define WebSocket message schemas` | `scope: shared`, `phase: 0` | Both |
| 5 | `[Shared] Create enum definitions (controller type, status, vehicle state)` | `scope: shared`, `phase: 0` | Both |
| 6 | `[Shared] Create example configuration files` | `scope: shared`, `phase: 0` | Both |

### Backend Setup Issues

| # | Title | Labels | Assignee |
|---|-------|--------|----------|
| 7 | `[BE] Initialize Python project with pyproject.toml` | `scope: backend`, `phase: 0` | Dev A |
| 8 | `[BE] Set up FastAPI application skeleton` | `scope: backend`, `phase: 0` | Dev A |
| 9 | `[BE] Configure pytest and initial test structure` | `scope: backend`, `phase: 0` | Dev A |
| 10 | `[BE] Set up ruff and mypy configuration` | `scope: backend`, `phase: 0` | Dev A |

### Frontend Setup Issues

| # | Title | Labels | Assignee |
|---|-------|--------|----------|
| 11 | `[FE] Initialize React + Vite + TypeScript project` | `scope: frontend`, `phase: 0` | Dev B |
| 12 | `[FE] Configure ESLint and Prettier` | `scope: frontend`, `phase: 0` | Dev B |
| 13 | `[FE] Set up CSS design system (variables, reset, typography)` | `scope: frontend`, `phase: 0` | Dev B |
| 14 | `[FE] Create TypeScript type definitions from shared schemas` | `scope: frontend`, `phase: 0` | Dev B |

### Documentation Issues

| # | Title | Labels | Assignee |
|---|-------|--------|----------|
| 15 | `[Docs] Write comprehensive root README` | `scope: docs`, `phase: 0` | Both |
| 16 | `[Docs] Set up GitHub issue templates` | `scope: docs`, `phase: 0` | Either |
| 17 | `[Docs] Create PR template` | `scope: docs`, `phase: 0` | Either |

---

## 8. GitHub Discussions Categories

| Category | Description |
|----------|-------------|
| **Announcements** | Project updates, milestone completions |
| **Architecture Decisions** | ADRs and design discussions |
| **Questions** | General questions about the project |
| **Ideas** | Feature ideas and improvement suggestions |
| **Show and Tell** | Demo progress, screenshots, recordings |

---

## 9. Repository Topics

Add these topics to the GitHub repository for discoverability:

```
traffic-simulation
intersection-control
roundabout
traffic-signal
idm-model
car-following
python
react
typescript
fastapi
websocket
performance-metrics
comparative-analysis
```

---

## 10. Branch Protection Recommendations

### `main` Branch

| Rule | Setting |
|------|---------|
| Require pull request reviews | ✅ At least 1 approval |
| Require status checks to pass | ✅ CI must pass |
| Require branches to be up to date | ✅ |
| Include administrators | ✅ |
| Allow force pushes | ❌ |
| Allow deletions | ❌ |

### `develop` Branch

| Rule | Setting |
|------|---------|
| Require pull request reviews | ✅ At least 1 approval |
| Require status checks to pass | ✅ CI must pass |
| Allow force pushes | ❌ |

---

## 11. Cross-References

| Topic | Document |
|-------|----------|
| Repository structure | [01-repository-architecture.md](./01-repository-architecture.md) |
| Engineering standards | [09-engineering-standards.md](./09-engineering-standards.md) |
| Shared contract management | [04-shared-contract-layer.md](./04-shared-contract-layer.md) |
