"""Export `prediction_events` into a flat DataFrame for drift analysis."""

from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
import typer

from api.common.config import get_settings
from api.infra.postgres.models import PredictionEventRecord

app = typer.Typer()


def export_predictions(
    database_url: str,
    start: datetime | None = None,
    end: datetime | None = None,
) -> pd.DataFrame:
    """Load prediction events, with the `features` JSONB column unpacked into flat columns.

    Without `start`/`end`, exports the whole table — sufficient for a
    dedicated local environment holding a single simulated traffic run.
    """
    engine = create_engine(database_url)
    query = select(PredictionEventRecord)
    if start is not None:
        query = query.where(PredictionEventRecord.occurred_at >= start)
    if end is not None:
        query = query.where(PredictionEventRecord.occurred_at <= end)

    with Session(engine) as session:
        rows = session.scalars(query).all()

    records = [
        {
            "occurred_at": row.occurred_at,
            "status": row.status,
            "decision": row.decision,
            "probability": row.probability,
            **row.features,
        }
        for row in rows
    ]
    return pd.DataFrame.from_records(records)


@app.command()
def main(
    start: datetime | None = None,
    end: datetime | None = None,
    output_path: Path = Path("data/drift/export/prediction_events.parquet"),
) -> None:
    """Export `prediction_events` to a local Parquet file for offline analysis."""
    dataset = export_predictions(get_settings().database_url, start, end)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_parquet(output_path, index=False)
    typer.echo(f"Exported {len(dataset)} prediction events to {output_path}.")


if __name__ == "__main__":
    app()
