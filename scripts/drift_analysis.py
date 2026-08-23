"""Shared drift-analysis logic.

Used by both `notebooks/data_drift.ipynb` and `scripts/generate_drift_report.py`
(the automated CI job) — kept in one place so the two don't silently diverge
on methodology over time.
"""

from typing import Any

from evidently import DataDefinition, Dataset, Report
from evidently.presets import DataDriftPreset
import pandas as pd
from scripts.export_tracking_for_drift import export_predictions
from sqlalchemy import create_engine, text

DRIFT_SHARE_THRESHOLD = 0.2
PRODUCTION_SAMPLE_SIZE = 5000


def load_reference(reference_path: str) -> pd.DataFrame:
    """Load the training-data reference Parquet, dropping the identifier and label columns."""
    return pd.read_parquet(reference_path).drop(columns=["SK_ID_CURR", "TARGET"])


def sample_recent_production(
    database_url: str, sample_size: int = PRODUCTION_SAMPLE_SIZE
) -> pd.DataFrame:
    """Export the `sample_size` most recently recorded predictions.

    Selecting by row count rather than a fixed time window keeps this valid
    regardless of when it's run relative to any given traffic replay.
    """
    engine = create_engine(database_url)
    with engine.connect() as connection:
        (window_start,) = connection.execute(
            text(
                "SELECT min(occurred_at) FROM ("
                "SELECT occurred_at FROM prediction_events "
                "ORDER BY occurred_at DESC LIMIT :sample_size"
                ") AS latest"
            ),
            {"sample_size": sample_size},
        ).one()
    return export_predictions(database_url, start=window_start)


def build_datasets(
    reference: pd.DataFrame, production_features: pd.DataFrame
) -> tuple[Dataset, Dataset]:
    """Build the Evidently reference/production datasets, inferring column types from dtypes."""
    categorical_columns = reference.select_dtypes(include="object").columns.tolist()
    numerical_columns = reference.select_dtypes(exclude="object").columns.tolist()
    definition = DataDefinition(
        numerical_columns=numerical_columns, categorical_columns=categorical_columns
    )
    reference_dataset = Dataset.from_pandas(reference, data_definition=definition)
    production_dataset = Dataset.from_pandas(production_features, data_definition=definition)
    return reference_dataset, production_dataset


def run_drift_report(
    reference_dataset: Dataset,
    production_dataset: Dataset,
    drift_share: float = DRIFT_SHARE_THRESHOLD,
) -> Any:
    """Run the Evidently data drift report, with native pass/fail Tests enabled."""
    report = Report([DataDriftPreset(drift_share=drift_share)], include_tests=True)
    return report.run(production_dataset, reference_dataset)


def drift_scores(drift_result: Any) -> pd.DataFrame:
    """Per-column drift scores, most-drifted first."""
    scores = sorted(
        (
            (metric["config"]["column"], metric["value"])
            for metric in drift_result.dict()["metrics"]
            if metric["metric_name"].startswith("ValueDrift")
        ),
        key=lambda item: -item[1],
    )
    return pd.DataFrame(
        {
            "feature": [feature for feature, _ in scores],
            "drift_score": [score for _, score in scores],
        }
    )


def dataset_drift_test(drift_result: Any) -> dict[str, Any]:
    """The dataset-level `DriftedColumnsCount` native Evidently test result."""
    return next(
        test
        for test in drift_result.dict()["tests"]
        if test["metric_config"]["params"].get("type") == "evidently:metric_v2:DriftedColumnsCount"
    )


def classification_summary(production: pd.DataFrame) -> tuple[float, float]:
    """Refusal rate and mean predicted default probability on this production sample."""
    refusal_rate = float((production["decision"] == 1).mean())
    mean_probability = float(production["probability"].mean())
    return refusal_rate, mean_probability
