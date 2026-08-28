"""Profile the real `/predictions` request path to identify the inference bottleneck.

Runs the exact code FastAPI runs per request — `load_champion`,
`connect_prediction_recorder`, `PredictionRequest` validation and
`services.predict.predict` — against a real MLflow champion and a real
Postgres database, broken down stage by stage (validation, inference,
persistence, end-to-end), plus a cProfile pass over the end-to-end call for
a function-level breakdown.

Étape 4 du cahier des charges (`references/PROJET.md`) demande de partir des
données de monitoring réelles pour identifier les goulots d'étranglement
avant de tester une optimisation. Les métriques déjà en prod (histogramme
Prometheus `inference_latency_ms`, table `prediction_events`) ne couvrent
que l'inférence elle-même ; ce script mesure aussi la validation Pydantic et
l'écriture Postgres pour situer l'inférence dans le total.

ATTENTION : ce script écrit de vraies lignes dans `prediction_events` sur la
base pointée par DATABASE_URL. À lancer contre le Postgres local
(`docker compose up -d postgres`), jamais contre Supabase release/production.

Run (depuis la racine du dépôt, comme les autres scripts de scripts/) :
    uv run python -m scripts.profiling.profile_predict --samples 50 --label baseline
"""

import cProfile
from datetime import UTC, datetime
from pathlib import Path
import pstats
from time import perf_counter
import uuid

from scripts.profiling.bottleneck import (
    identify_bottleneck,
    load_sample_features,
    render_markdown_report,
    stage_stats,
)
import typer

from api.infra.config import get_settings
from api.infra.mlflow_model import load_champion
from api.infra.postgres.tracking import connect_prediction_recorder
from api.modules.scoring.domain.entities import PredictionEvent
from api.modules.scoring.presentation.schemas import PredictionRequest
from api.modules.scoring.services.predict import predict

SAMPLES_PATH = Path("src/ui/sample_data/demo_samples.csv")

app = typer.Typer()


@app.command()
def main(
    samples: int = typer.Option(50, help="Calls timed per stage."),
    warmup: int = typer.Option(10, help="Untimed calls run first."),
    label: str = typer.Option("run", help="Tag used in the output filenames."),
    reports_dir: Path = typer.Option(Path("reports/profiling"), help="Output directory."),
) -> None:
    """Load the real champion and Postgres recorder, then profile the request path."""
    settings = get_settings()

    print("Chargement du champion MLflow...")
    load_started = perf_counter()
    model = load_champion(settings)
    print(f"  -> v{model.version} chargé en {(perf_counter() - load_started) * 1_000:.1f} ms")

    print("Connexion à Postgres...")
    recorder = connect_prediction_recorder(settings)

    raw_rows = load_sample_features(SAMPLES_PATH, samples + warmup)
    warmup_rows, timed_rows = raw_rows[:warmup], raw_rows[warmup:]

    print(f"Warm-up ({warmup} appels non mesurés)...")
    for row in warmup_rows:
        features = PredictionRequest(**row).model_features()
        predict(model, recorder, features)

    print(f"Mesure par étage ({samples} appels)...")
    validation_durations: list[float] = []
    features_by_row: list[dict] = []
    for row in timed_rows:
        started = perf_counter()
        features = PredictionRequest(**row).model_features()
        validation_durations.append((perf_counter() - started) * 1_000)
        features_by_row.append(features)

    inference_durations: list[float] = []
    persistence_durations: list[float] = []
    for features in features_by_row:
        started = perf_counter()
        probability = model.probability(features)
        inference_durations.append((perf_counter() - started) * 1_000)

        event = PredictionEvent(
            prediction_id=str(uuid.uuid4()),
            model_version=model.version,
            status="success",
            probability=probability,
            decision=int(probability >= model.threshold),
            inference_latency_ms=inference_durations[-1],
            error_code=None,
        )
        started = perf_counter()
        recorder.record(event, features)
        persistence_durations.append((perf_counter() - started) * 1_000)

    end_to_end_durations: list[float] = []
    for features in features_by_row:
        started = perf_counter()
        predict(model, recorder, features)
        end_to_end_durations.append((perf_counter() - started) * 1_000)

    reports_dir.mkdir(parents=True, exist_ok=True)

    print("Profiling cProfile (détail fonction par fonction) sur l'appel complet...")
    profiler = cProfile.Profile()
    profiler.enable()
    for features in features_by_row:
        predict(model, recorder, features)
    profiler.disable()
    prof_path = reports_dir / f"{label}_predict.prof"
    profiler.dump_stats(str(prof_path))
    print(f"\nTop 20 fonctions par temps cumulé (voir aussi {prof_path}) :")
    pstats.Stats(profiler).sort_stats("cumulative").print_stats(20)

    atomic_stages = {
        "validation": stage_stats(validation_durations),
        "inference": stage_stats(inference_durations),
        "persistence": stage_stats(persistence_durations),
    }
    all_stages = {**atomic_stages, "end_to_end": stage_stats(end_to_end_durations)}
    bottleneck = identify_bottleneck(atomic_stages)

    print("\nRésumé par étage (ms) :")
    for name, stats in all_stages.items():
        print(
            f"  {name:<12} mean={stats.mean_ms:7.3f} p50={stats.p50_ms:7.3f} "
            f"p95={stats.p95_ms:7.3f} p99={stats.p99_ms:7.3f} max={stats.max_ms:7.3f}"
        )
    print(f"\nGoulot identifié : {bottleneck}")

    report = render_markdown_report(
        label=label,
        generated_at=datetime.now(UTC).isoformat(),
        model_version=model.version,
        sample_size=samples,
        stages=all_stages,
        bottleneck=bottleneck,
    )
    report_path = reports_dir / f"{label}_bottleneck_report.md"
    report_path.write_text(report)
    print(f"Rapport écrit dans {report_path}")


if __name__ == "__main__":
    app()
