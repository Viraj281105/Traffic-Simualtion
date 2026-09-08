# Architecture Decision Records (ADRs)

This directory contains historical **Architecture Decision Records (ADRs)**. They record intended rationale and trade-offs at the time of the decision; they are not a substitute for the current implementation guide. When an ADR differs from the code, use [the operations guide](../operations.md) and the source tree as the current authority.

## ADR Library Index

| ID | Title | Status | Date |
|----|-------|--------|------|
| **[ADR-001](adr-001-repository-structure.md)** | Repository Structure | Accepted | 2026-07-23 |
| **[ADR-002](adr-002-backend-frontend-separation.md)** | Backend / Frontend Separation | Accepted | 2026-07-23 |
| **[ADR-003](adr-003-shared-contract-layer.md)** | Shared Contract Layer | Accepted | 2026-07-23 |
| **[ADR-004](adr-004-snapshot-based-communication.md)** | Snapshot-Based Communication | Accepted | 2026-07-23 |
| **[ADR-005](adr-005-metric-contract-design.md)** | Metric Contract Design | Accepted | 2026-07-23 |
| **[ADR-006](adr-006-scenario-configuration-format.md)** | Scenario Configuration Format | Accepted | 2026-07-23 |
| **[ADR-007](adr-007-rest-websocket-communication-strategy.md)** | REST + WebSocket Communication Strategy | Accepted | 2026-07-23 |
| **[ADR-008](file:///c:/VIRAJ/Internship/Traffic_Simulation_Project_1/docs/decisions/adr-008-repository-branching-strategy.md)** | Repository Branching Strategy | Accepted | 2026-07-23 |
| **[ADR-009](file:///c:/VIRAJ/Internship/Traffic_Simulation_Project_1/docs/decisions/adr-009-engineering-standards.md)** | Engineering Standards | Accepted | 2026-07-23 |
| **[ADR-010](file:///c:/VIRAJ/Internship/Traffic_Simulation_Project_1/docs/decisions/adr-010-documentation-organization.md)** | Documentation Organization | Accepted | 2026-07-23 |
| **[ADR-011](file:///c:/VIRAJ/Internship/Traffic_Simulation_Project_1/docs/decisions/adr-011-versioning-strategy.md)** | Versioning Strategy | Accepted | 2026-07-23 |
| **[ADR-012](file:///c:/VIRAJ/Internship/Traffic_Simulation_Project_1/docs/decisions/adr-012-future-controller-extensibility.md)** | Future Controller Extensibility | Accepted | 2026-07-23 |

## ADR Structure

Each record follows the standard format:
1.  **Title**: The index ID and descriptive name.
2.  **Status**: Current lifecycle state of the decision (`Accepted`, `Proposed`, `Superseded`).
3.  **Context**: The environment parameters or constraints prompting the choice.
4.  **Problem Statement**: The central architectural question.
5.  **Decision**: The chosen technical path and details.
6.  **Alternatives Considered**: Other architectural paths evaluated and why they were rejected.
7.  **Trade-offs**: Direct positive (pros) and negative (cons) consequences.
8.  **Consequences**: Workflow and tooling adjustments resulting from the decision.
9.  **Future Considerations**: Future paths of optimization or changes.
10. **Related ADRs**: Cross-linked dependency records.
