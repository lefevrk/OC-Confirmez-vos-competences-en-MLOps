"""Export a small, committed sample of real feature rows for the Gradio demo.

The full reference dataset (`data/drift/reference/serving_50_features.parquet`,
downloaded by `scripts/download_drift_reference.py`) is gitignored and never
shipped in the deployed image — this script draws a fixed, reproducible
sample from it once, in the exact `PredictionRequest` column order, so the
demo UI always has real values to pre-fill without depending on the
reference bucket at runtime.
"""

from pathlib import Path

import pandas as pd
import typer

from api.modules.scoring.presentation.schemas import PredictionRequest

app = typer.Typer()

NON_FEATURE_COLUMNS = ("SK_ID_CURR", "TARGET")


@app.command()
def main(
    reference_path: Path = Path("data/drift/reference/serving_50_features.parquet"),
    output_path: Path = Path("src/ui/sample_data/demo_samples.csv"),
    count: int = 25,
    seed: int = 42,
) -> None:
    """Write a reproducible sample of real rows, columns ordered like PredictionRequest."""
    aliases = [field.alias or name for name, field in PredictionRequest.model_fields.items()]
    reference = pd.read_parquet(reference_path).drop(columns=list(NON_FEATURE_COLUMNS))
    sample = reference.sample(n=count, random_state=seed)[aliases]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sample.to_csv(output_path, index=False)
    typer.echo(f"Wrote {len(sample)} demo samples to {output_path}.")


if __name__ == "__main__":
    app()
