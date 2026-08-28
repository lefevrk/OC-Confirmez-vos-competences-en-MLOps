"""Pure, testable helpers for the inference bottleneck-detection scripts.

Kept separate from `profile_predict.py` (which needs a live MLflow champion
and a live Postgres connection) so the percentile math, sample loading and
report formatting can be unit-tested without a running stack — the same
split `scripts/drift_analysis.py` uses for the drift tooling.
"""

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class StageStats:
    """Latency distribution for one profiled stage, in milliseconds."""

    mean_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float


def _percentile(sorted_values: list[float], fraction: float) -> float:
    """Linearly-interpolated percentile of an already-sorted list."""
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = fraction * (len(sorted_values) - 1)
    lower, upper = int(rank), min(int(rank) + 1, len(sorted_values) - 1)
    weight = rank - lower
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * weight


def stage_stats(durations_ms: list[float]) -> StageStats:
    """Summarize a stage's per-call durations into mean/p50/p95/p99/max."""
    if not durations_ms:
        raise ValueError("durations_ms must not be empty")
    values = sorted(durations_ms)
    return StageStats(
        mean_ms=sum(values) / len(values),
        p50_ms=_percentile(values, 0.50),
        p95_ms=_percentile(values, 0.95),
        p99_ms=_percentile(values, 0.99),
        max_ms=max(values),
    )


def load_sample_features(csv_path: Path, count: int) -> list[dict[str, Any]]:
    """Cycle through the demo CSV's real rows, alias-keyed and NaN turned into None.

    Reuses `src/ui/sample_data/demo_samples.csv` — the same real client
    records already used by the Gradio demo (`src/ui/blocks.py`) — so a
    profiling run scores realistic, varied inputs instead of one payload
    repeated `count` times.
    """
    frame = pd.read_csv(csv_path)
    rows = frame.to_dict(orient="records")
    if not rows:
        raise ValueError(f"{csv_path} contains no sample rows")
    return [
        {key: (None if pd.isna(value) else value) for key, value in rows[index % len(rows)].items()}
        for index in range(count)
    ]


def identify_bottleneck(stages: dict[str, StageStats]) -> str:
    """Name the atomic stage (pass validation/inference/persistence, not a composite) that dominates."""
    ranked = sorted(stages.items(), key=lambda item: item[1].mean_ms, reverse=True)
    leader_name, leader = ranked[0]
    total = sum(stage.mean_ms for stage in stages.values())
    share = leader.mean_ms / total if total else 0.0
    return f"{leader_name} ({leader.mean_ms:.3f} ms/appel en moyenne, {share:.0%} du temps mesuré)"


def stats_to_json(
    *,
    label: str,
    generated_at: str,
    model_version: str,
    sample_size: int,
    stages: dict[str, StageStats],
) -> dict[str, Any]:
    """Serialize a run's stage stats for later reuse (e.g. a before/after comparison chart)."""
    return {
        "label": label,
        "generated_at": generated_at,
        "model_version": model_version,
        "sample_size": sample_size,
        "stages": {name: asdict(stats) for name, stats in stages.items()},
    }


def render_markdown_report(
    *,
    label: str,
    generated_at: str,
    model_version: str,
    sample_size: int,
    stages: dict[str, StageStats],
    bottleneck: str,
) -> str:
    """Render the bottleneck report as Markdown, mirroring the drift report's summary style."""
    rows = "\n".join(
        f"| {name} | {stats.mean_ms:.3f} | {stats.p50_ms:.3f} | {stats.p95_ms:.3f} | "
        f"{stats.p99_ms:.3f} | {stats.max_ms:.3f} |"
        for name, stats in stages.items()
    )
    return (
        f"# Rapport de profiling — {label}\n\n"
        f"Généré le {generated_at} — {sample_size} appels mesurés par étage, "
        f"modèle champion v{model_version}.\n\n"
        f"**Goulot identifié : {bottleneck}**\n\n"
        "| Étage | Moyenne (ms) | p50 (ms) | p95 (ms) | p99 (ms) | Max (ms) |\n"
        "|---|---|---|---|---|---|\n"
        f"{rows}\n\n"
        "`end_to_end` mesure l'appel complet à `services.predict.predict` "
        "(validation exclue) — le comparer à `inference + persistence` donne "
        "l'overhead propre à `predict()` (fingerprint, logging, décision).\n\n"
        "Voir le `.prof` du même run pour le détail fonction par fonction "
        "(`uv run snakeviz <fichier>.prof`, ou `pstats.Stats(...)`).\n"
    )
