r"""Plot a grouped bar chart comparing two profiling runs' stage latencies.

Reads the `<label>_stats.json` files `profile_predict.py` writes for two runs
(e.g. a pre-optimization baseline and a post-optimization challenger) and
renders one grouped bar chart — one group per stage (validation, inference,
persistence, end-to-end), one bar per run — so the improvement (or lack of
one) per stage is visible at a glance. Used to produce the comparison chart
embedded in docs/operations/optimisation-inference.md.

Run:
    uv run python -m scripts.profiling.plot_comparison \\
        --baseline baseline-sklearn --baseline-name "Champion (sklearn)" \\
        --challenger challenger-onnx --challenger-name "Challenger (ONNX)" \\
        --output docs/assets/model/onnx_inference_latency_comparison.png
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt
import numpy as np
import typer

app = typer.Typer()

STAGE_ORDER = ["validation", "inference", "persistence", "end_to_end"]
STAGE_LABELS = {
    "validation": "Validation",
    "inference": "Inférence",
    "persistence": "Persistence",
    "end_to_end": "End-to-end",
}


def _load_means(reports_dir: Path, label: str) -> list[float]:
    """Return the mean latency (ms) per stage, in STAGE_ORDER, for one labeled run."""
    data = json.loads((reports_dir / f"{label}_stats.json").read_text())
    return [data["stages"][stage]["mean_ms"] for stage in STAGE_ORDER]


@app.command()
def main(
    baseline: str = typer.Option(..., help="Label of the pre-optimization run."),
    challenger: str = typer.Option(..., help="Label of the post-optimization run."),
    baseline_name: str = typer.Option("Baseline", help="Legend name for the baseline run."),
    challenger_name: str = typer.Option("Challenger", help="Legend name for the challenger run."),
    reports_dir: Path = typer.Option(
        Path("reports/profiling"), help="Directory containing the *_stats.json files."
    ),
    output: Path = typer.Option(..., help="PNG path to write."),
) -> None:
    """Render a grouped bar chart comparing two profiling runs' stage latencies."""
    baseline_means = _load_means(reports_dir, baseline)
    challenger_means = _load_means(reports_dir, challenger)

    positions = np.arange(len(STAGE_ORDER))
    width = 0.35

    figure, axes = plt.subplots(figsize=(8, 5))
    baseline_bars = axes.bar(
        positions - width / 2, baseline_means, width, label=baseline_name, color="#94a3b8"
    )
    challenger_bars = axes.bar(
        positions + width / 2, challenger_means, width, label=challenger_name, color="#2563eb"
    )

    axes.set_ylabel("Latence moyenne (ms)")
    axes.set_title("Latence par étage — avant/après optimisation")
    axes.set_xticks(positions)
    axes.set_xticklabels([STAGE_LABELS[stage] for stage in STAGE_ORDER])
    axes.legend()
    axes.bar_label(baseline_bars, fmt="%.2f", padding=3, fontsize=8)
    axes.bar_label(challenger_bars, fmt="%.2f", padding=3, fontsize=8)
    figure.tight_layout()

    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=150)
    typer.echo(f"Graphique écrit dans {output}")


if __name__ == "__main__":
    app()
