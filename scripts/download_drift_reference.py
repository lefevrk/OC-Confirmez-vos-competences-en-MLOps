"""Download the drift reference dataset from the private HF Storage Bucket.

Mirrors the model repo's own `download.py` (same `HfFileSystem` pattern, same
`HF_BUCKET_ID`/`HF_BUCKET_READ_TOKEN` env vars) so the bucket-access mechanic
isn't reinvented — just pointed at this use case's fixed remote path. The
model repo's `upload.py` is the one-off, manual counterpart that publishes
`reduced/serving_50_features.parquet` (alongside its existing `raw/` and
`aggregated/` bucket folders) after a champion is promoted; it is not run
from here.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from huggingface_hub import HfFileSystem
import typer

app = typer.Typer()

REMOTE_PATH = "reduced/serving_50_features.parquet"


@app.command()
def main(
    output_path: Path = Path("data/drift/reference/serving_50_features.parquet"),
) -> None:
    """Download the reference Parquet using the read-scoped bucket token."""
    load_dotenv()
    bucket = os.environ["HF_BUCKET_ID"]
    token = os.environ["HF_BUCKET_READ_TOKEN"]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    HfFileSystem(token=token).get(f"buckets/{bucket}/{REMOTE_PATH}", str(output_path))
    typer.echo(f"Downloaded hf://buckets/{bucket}/{REMOTE_PATH} to {output_path}")


if __name__ == "__main__":
    app()
