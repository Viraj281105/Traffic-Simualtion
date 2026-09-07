import os
import sqlite3
from typing import Generator

DB_PATH = os.environ.get("DB_PATH", "simulation.db")


def init_db() -> None:
    """Initializes the SQLite database tables if they do not exist, and applies safe migrations."""
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    cursor = conn.cursor()

    # Enable WAL mode, busy timeout, and Foreign Key support
    cursor.execute("PRAGMA journal_mode = WAL;")
    cursor.execute("PRAGMA busy_timeout = 5000;")
    cursor.execute("PRAGMA foreign_keys = ON;")

    # 1. Configurations table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS configurations (
            id TEXT PRIMARY KEY,
            config_json TEXT NOT NULL
        );
        """
    )

    # 2. Simulation Runs table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS simulation_runs (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            elapsed REAL NOT NULL,
            intersection_type TEXT NOT NULL DEFAULT 'unknown',
            random_seed INTEGER NOT NULL DEFAULT 0,
            arrival_rate REAL DEFAULT 0.5,
            duration REAL DEFAULT 60.0,
            batch_id TEXT,
            config_json TEXT NOT NULL DEFAULT '{}',
            summary_metrics_json TEXT NOT NULL DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    # Safe migration: ensure existing tables receive any missing columns
    cursor.execute("PRAGMA table_info(simulation_runs);")
    existing_cols = {row[1] for row in cursor.fetchall()}
    columns_to_add = [
        ("intersection_type", "TEXT NOT NULL DEFAULT 'unknown'"),
        ("random_seed", "INTEGER NOT NULL DEFAULT 0"),
        ("arrival_rate", "REAL DEFAULT 0.5"),
        ("duration", "REAL DEFAULT 60.0"),
        ("batch_id", "TEXT"),
        ("config_json", "TEXT NOT NULL DEFAULT '{}'"),
        ("summary_metrics_json", "TEXT NOT NULL DEFAULT '{}'"),
    ]
    for col_name, col_def in columns_to_add:
        if col_name not in existing_cols:
            cursor.execute(
                f"ALTER TABLE simulation_runs ADD COLUMN {col_name} {col_def};"
            )

    # Indexes on simulation_runs for fast querying and filtering
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_sim_runs_type ON simulation_runs(intersection_type);"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_sim_runs_seed ON simulation_runs(random_seed);"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_sim_runs_batch ON simulation_runs(batch_id);"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_sim_runs_created ON simulation_runs(created_at DESC);"
    )

    # 3. Run Metrics table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS run_metrics (
            run_id TEXT,
            tick INTEGER,
            metrics_json TEXT NOT NULL,
            PRIMARY KEY (run_id, tick),
            FOREIGN KEY (run_id) REFERENCES simulation_runs(id) ON DELETE CASCADE
        );
        """
    )

    # 4. Sweep Sessions table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS sweep_sessions (
            id TEXT PRIMARY KEY,
            name TEXT,
            config_json TEXT NOT NULL,
            results_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    # 5. Saved Replays table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS saved_replays (
            id TEXT PRIMARY KEY,
            name TEXT,
            config_json TEXT NOT NULL,
            metrics_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    conn.commit()
    conn.close()


def get_db_connection() -> Generator[sqlite3.Connection, None, None]:
    """Yields a database connection context manager configured with WAL and foreign keys."""
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
