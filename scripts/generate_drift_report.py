"""Generate the Evidently drift report and a markdown summary.

Runs against a given environment's production database. Deliberately does
not depend on `api.infra.config.Settings` — that model
requires MLflow credentials this job has no use for. `DATABASE_URL` is read
directly from the environment, matching `download_drift_reference.py`'s
convention for its own bucket credentials.

Run from CI (see .github/workflows/drift-report.yml) or locally:
    DATABASE_URL=postgresql://... uv run python scripts/generate_drift_report.py
"""

from datetime import UTC, datetime
import os
from pathlib import Path
from typing import cast

from dotenv import load_dotenv
import pandas as pd
from scripts.drift_analysis import (
    build_datasets,
    classification_summary,
    dataset_drift_test,
    drift_scores,
    load_reference,
    run_drift_report,
    sample_recent_production,
)
import typer

app = typer.Typer()


@app.command()
def main(
    database_url: str | None = typer.Option(None, help="Defaults to the DATABASE_URL env var."),
    environment: str = typer.Option("local", help="Label included in the report/summary."),
    reference_path: Path = Path("data/drift/reference/serving_50_features.parquet"),
    report_path: Path = Path("reports/drift_report.html"),
    summary_path: Path = Path("reports/drift_summary.md"),
) -> None:
    """Analyze the most recent production predictions for drift against the training reference."""
    load_dotenv()
    database_url = database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        raise typer.BadParameter("pass --database-url or set the DATABASE_URL env var")

    reference = load_reference(str(reference_path))
    production = sample_recent_production(database_url)
    production_features = cast(pd.DataFrame, production[reference.columns.tolist()])

    reference_dataset, production_dataset = build_datasets(reference, production_features)
    drift_result = run_drift_report(reference_dataset, production_dataset)

    scores = drift_scores(drift_result)
    test = dataset_drift_test(drift_result)
    refusal_rate, mean_probability = classification_summary(production)
    verdict = "DRIFT DÉTECTÉ" if test["status"].name == "FAIL" else "pas de drift détecté"

    report_path.parent.mkdir(parents=True, exist_ok=True)
    drift_result.save_html(str(report_path))

    summary_lines = [
        f"# Rapport de drift — {environment}",
        "",
        f"Généré le {datetime.now(UTC).isoformat()} — {len(production_features)} prédictions analysées.",
        "",
        f"**Verdict : {verdict}** — {test['description']}",
        "",
        f"Taux de refus : {refusal_rate:.1%} — probabilité de défaut moyenne prédite : {mean_probability:.1%}",
        "",
        "## Top features en dérive",
        "",
        "| feature | drift_score |",
        "|---|---|",
        *(
            f"| {feature} | {score:.3f} |"
            for feature, score in zip(
                scores["feature"].head(10), scores["drift_score"].head(10), strict=True
            )
        ),
    ]
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("\n".join(summary_lines) + "\n")

    typer.echo(f"Rapport écrit dans {report_path}, résumé dans {summary_path}")
    typer.echo(verdict)


if __name__ == "__main__":
    app()
