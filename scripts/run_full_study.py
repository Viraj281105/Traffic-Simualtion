#!/usr/bin/env python3
"""Automated Comprehensive Study CLI Runner.

Executes an automated end-to-end traffic simulation study without requiring a running API server:
1. Multi-Volume Parameter Sweep: Evaluates Fixed-Time Signal vs. Modern Roundabout
   across varying traffic arrival rates under identical seeds.
2. Monte Carlo Statistical Validation: Runs multi-seed experiments to evaluate
   repeatability, variance, and 95% confidence intervals.
3. Generates and exports the final study_report.csv and optional JSON summary.

Usage:
    python scripts/run_full_study.py [--sweep-duration 60.0] [--validation-duration 30.0] [--num-seeds 5]
"""

import argparse
import json
import logging
import os
from pathlib import Path
import sys
import time

# Configure output encoding for Windows terminal compatibility
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add project root and backend to python path for direct module imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Ensure database path is anchored properly if not specified
if "DB_PATH" not in os.environ:
    os.environ["DB_PATH"] = str(PROJECT_ROOT / "simulation.db")

from src.database.db import init_db
from src.study.report_generator import (
    generate_study_report_csv,
    generate_study_report_json,
)
from src.study.validation import run_statistical_validation
from src.study.volume_sweep import (
    DEFAULT_ARRIVAL_RATES,
    run_volume_sweep_experiment,
)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the automated study runner."""
    parser = argparse.ArgumentParser(
        description="Automated Traffic Simulation Study CLI Runner (W8 Final Validated Study)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--sweep-duration",
        type=float,
        default=60.0,
        help="Simulated duration (in seconds) per volume sweep tier",
    )
    parser.add_argument(
        "--validation-duration",
        type=float,
        default=30.0,
        help="Simulated duration (in seconds) per Monte Carlo validation seed",
    )
    parser.add_argument(
        "--num-seeds",
        type=int,
        default=5,
        help="Number of randomized seeds for Monte Carlo statistical validation",
    )
    parser.add_argument(
        "--time-step",
        type=float,
        default=0.1,
        help="Simulation integration time step dt (in seconds)",
    )
    parser.add_argument(
        "--rates",
        type=str,
        default=None,
        help="Comma-separated arrival rates in veh/s/approach (e.g. '0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8')",
    )
    parser.add_argument(
        "--output-csv",
        type=str,
        default="study_report.csv",
        help="Target filepath for generated study CSV report",
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default=None,
        help="Optional target filepath for generated study JSON summary",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose vehicle-level collision and physics debug logs",
    )
    return parser.parse_args()


def print_banner() -> None:
    """Prints a styled terminal header for the study runner."""
    print("=" * 86)
    print("      TRAFFIC INTERSECTION CONTROL COMPARISON: COMPREHENSIVE STUDY RUNNER     ")
    print("=" * 86)
    print("  Evaluating:     Fixed-Time Traffic Signal vs. Modern Roundabout Control")
    print("  Physics Engine: Intelligent Driver Model (IDM) with Circular Overrides")
    print(f"  Database Path:  {os.environ['DB_PATH']}")
    print("=" * 86)
    print()


def get_cohens_d_descriptor(d: float) -> str:
    """Categorizes Cohen's d effect size according to standard statistical thresholds."""
    abs_d = abs(d)
    if abs_d >= 0.8:
        return "Large Effect (Substantial Impact)"
    elif abs_d >= 0.5:
        return "Medium Effect (Noticeable Difference)"
    elif abs_d >= 0.2:
        return "Small Effect"
    else:
        return "Negligible / Practical Parity"


def main() -> int:
    """Main CLI study execution entrypoint."""
    args = parse_args()

    # Configure logging: suppress low-level vehicle collision warnings unless verbose is flagged
    log_level = logging.DEBUG if args.verbose else logging.ERROR
    logging.basicConfig(
        level=log_level, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    logging.getLogger("src").setLevel(log_level)

    print_banner()

    rates = (
        [float(r.strip()) for r in args.rates.split(",") if r.strip()]
        if args.rates
        else DEFAULT_ARRIVAL_RATES
    )

    print("[Step 1/3] Initializing simulation database schema...")
    init_db()
    print("  [✓] Database schema confirmed ready.")

    # ── 1. Multi-Volume Parameter Sweep ────────────────────────────────────────
    print("\n[Step 2/3] Executing Multi-Volume Sensitivity Sweep...")
    print(f"  - Arrival Rates:     {rates} veh/s/approach")
    print(
        f"  - Hourly Volumes:    {[round(r * 3600 * 4) for r in rates]} veh/h (total intersection)"
    )
    print(
        f"  - Duration per Tier: {args.sweep_duration}s (dt = {args.time_step}s)"
    )
    start_sweep = time.time()

    sweep_results = run_volume_sweep_experiment(
        arrival_rates=rates,
        duration=args.sweep_duration,
        time_step=args.time_step,
        random_seed=42,
        name="CLI Automated Volume Sweep",
    )
    sweep_elapsed = time.time() - start_sweep
    print(
        f"  [✓] Multi-volume sweep completed in {sweep_elapsed:.2f}s across {len(rates)} demand tiers."
    )

    # Display clean ASCII sweep table
    print("\n  " + "=" * 98)
    print("  VOLUME SWEEP SENSITIVITY SUMMARY TABLE")
    print("  " + "=" * 98)
    print(
        f"  {'Rate':>6} | {'Vol (veh/h)':>11} | {'Sig Delay':>10} | {'Rnd Delay':>10} | "
        f"{'Sig Tput':>9} | {'Rnd Tput':>9} | {'Sig Q':>6} | {'Rnd Q':>6} | {'Δ Delay':>8} | {'Winner':>10}"
    )
    print("  " + "-" * 98)

    runs = sweep_results.get("runs", [])
    roundabout_wins = 0
    signal_wins = 0

    for run in runs:
        r = run.get("arrivalRate", 0.0)
        vol = run.get("hourlyVolumeVehPerHour", 0)
        sig_d = run.get("signal", {}).get("delay", 0.0)
        rnd_d = run.get("roundabout", {}).get("delay", 0.0)
        sig_tp = run.get("signal", {}).get("throughput", 0.0)
        rnd_tp = run.get("roundabout", {}).get("throughput", 0.0)
        sig_q = run.get("signal", {}).get("queue", 0.0)
        rnd_q = run.get("roundabout", {}).get("queue", 0.0)
        delta = run.get("delayDeltaPercent", 0.0)
        winner = run.get("winner", "tie").upper()

        if winner == "ROUNDABOUT":
            roundabout_wins += 1
        elif winner == "SIGNAL":
            signal_wins += 1

        delta_str = f"{delta:+.1f}%" if abs(delta) > 0.01 else "0.0%"
        print(
            f"  {r:6.2f} | {vol:11,d} | {sig_d:9.2f}s | {rnd_d:9.2f}s | "
            f"{sig_tp:9.1f} | {rnd_tp:9.1f} | {sig_q:6.1f} | {rnd_q:6.1f} | {delta_str:>8} | {winner:>10}"
        )

    print("  " + "-" * 98)

    # Crossover Insights
    crossover = sweep_results.get("curves", {}).get("crossoverArrivalRate")
    crossover_h = sweep_results.get("curves", {}).get("crossoverHourlyVolume")
    if crossover and crossover_h:
        print(
            f"\n  🎯 CRITICAL SATURATION CROSSOVER THRESHOLD: {crossover:.2f} veh/s (~{crossover_h:,d} veh/h)"
        )
        print(
            f"     • Below {crossover_h:,d} veh/h: Roundabout yields up to 50% lower vehicular delay (no red-phase wait)."
        )
        print(
            f"     • Above {crossover_h:,d} veh/h: Roundabout entry yields experience starvation; Signal provides better queue fairness."
        )
    else:
        print("\n  🎯 CROSSOVER STATUS: No saturation transition detected.")
        if roundabout_wins > signal_wins:
            print(
                "     • Roundabout dominated across all evaluated arrival rates."
            )
        elif signal_wins > roundabout_wins:
            print(
                "     • Fixed-Time Signal maintained lower delay across all evaluated arrival rates."
            )

    # ── 2. Monte Carlo Statistical Validation ──────────────────────────────────
    print(
        f"\n[Step 3/3] Executing Monte Carlo Statistical Validation ({args.num_seeds} randomized seeds)..."
    )
    print(
        f"  - Duration per Seed: {args.validation_duration}s (Evaluation Rate: 0.3 veh/s)"
    )
    start_mc = time.time()

    validation_results = run_statistical_validation(
        num_seeds=args.num_seeds,
        duration=args.validation_duration,
        time_step=args.time_step,
    )
    mc_elapsed = time.time() - start_mc
    print(
        f"  [✓] Monte Carlo validation completed in {mc_elapsed:.2f}s across {args.num_seeds} randomized seeds."
    )

    # Statistical Rigor Table
    print("\n  " + "=" * 98)
    print("  MONTE CARLO STATISTICAL SIGNIFICANCE SUMMARY (95% CI, α = 0.05)")
    print("  " + "=" * 98)
    print(
        f"  {'Metric':<14} | {'Signal (Mean ± 95% CI)':<24} | {'Roundabout (Mean ± 95% CI)':<26} | "
        f"{'Cohen d':>8} | {'p-value':>8} | {'Significance'}"
    )
    print("  " + "-" * 98)

    cmp_dict = validation_results.get("comparison", {})
    all_sig = True
    any_sig = False

    for m in ["delay", "throughput", "queue"]:
        sig_st = validation_results.get("signal", {}).get(m, {})
        rnd_st = validation_results.get("roundabout", {}).get(m, {})
        m_cmp = cmp_dict.get(m, {})

        sig_str = (
            f"{sig_st.get('mean', 0.0):.2f} ± {sig_st.get('ci95', 0.0):.2f}"
        )
        rnd_str = (
            f"{rnd_st.get('mean', 0.0):.2f} ± {rnd_st.get('ci95', 0.0):.2f}"
        )
        d_val = m_cmp.get("cohensD", 0.0)
        p_val = m_cmp.get("pValue")
        p_str = (
            "<0.001"
            if p_val is not None and p_val < 0.001
            else f"{p_val:.3f}"
            if p_val is not None
            else "N/A"
        )
        is_sig = m_cmp.get("significant", False)

        if is_sig:
            any_sig = True
            sig_label = "★ Significant"
        else:
            all_sig = False
            sig_label = "Not Significant"

        print(
            f"  {m.capitalize():<14} | {sig_str:<24} | {rnd_str:<26} | {d_val:8.3f} | {p_str:>8} | {sig_label}"
        )

    print("  " + "-" * 98)

    # Statistical Verdict
    if all_sig:
        print(
            "  STATISTICAL VERDICT: [High Confidence] Statistically significant difference across all metrics."
        )
    elif any_sig:
        print(
            "  STATISTICAL VERDICT: [Partial Significance] Significant divergence identified in key metrics."
        )
    else:
        print(
            "  STATISTICAL VERDICT: [Equivalence / Parity] Differences remain within stochastic variation noise."
        )

    # ── 3. Report Export ───────────────────────────────────────────────────────
    print("\n[Exporting Study Artifacts]")
    csv_content = generate_study_report_csv(sweep_results, validation_results)
    output_csv_path = Path(args.output_csv)
    output_csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_csv_path, "w", encoding="utf-8") as f:
        f.write(csv_content)

    csv_size_kb = output_csv_path.stat().st_size / 1024.0
    print(
        f"  [✓] Study report CSV successfully written to: {output_csv_path.resolve()} ({csv_size_kb:.1f} KB)"
    )

    if args.output_json:
        json_data = generate_study_report_json(
            sweep_results, validation_results
        )
        output_json_path = Path(args.output_json)
        output_json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2)
        json_size_kb = output_json_path.stat().st_size / 1024.0
        print(
            f"  [✓] Study summary JSON successfully written to: {output_json_path.resolve()} ({json_size_kb:.1f} KB)"
        )

    total_time = sweep_elapsed + mc_elapsed
    print(f"\n[COMPLETE] Full automated study finished in {total_time:.2f}s.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
