# Project Management Specifications

This directory contains historical project-management resources, roadmaps, labels, and GitHub automation notes. It is not a statement of current implementation status; use the root README and [operations guide](../operations.md) for the running system.

## Directory Index

| Document | Purpose |
|----------|---------|
| **[roadmap.md](roadmap.md)** | Historical development roadmap and exit gates. |
| **[labels.md](labels.md)** | GitHub labeling configuration used by automation scripts. |
| **[kanban.md](kanban.md)** | Historical Kanban columns and saved-view design. |
| **[github-management-package.md](github-management-package.md)** | GitHub issue, milestone, label, and dependency package. |

## Quick Start: Project Workspace Setup

To configure your GitHub repository workspace with all labels, milestones, and issues defined here:

1.  Provide your Personal Access Token in a `.env` file at the root of the repository:
    ```
    GITHUB_TOKEN=your_pat_token_here
    ```
2.  Run the setup script:
    ```bash
    python scripts/setup_github.py
    ```
3.  The script will auto-detect your git remote URL and automatically populate your repository.
4.  Navigate to GitHub and create a new Project Board matching the guidelines in [kanban.md](file:///c:/VIRAJ/Internship/Traffic_Simulation_Project_1/docs/project-management/kanban.md).
