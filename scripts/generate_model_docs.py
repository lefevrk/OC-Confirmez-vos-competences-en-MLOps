"""Regenerate docs/design/model.md and its plots from the current MLflow champion.

Keeps "Modèle de scoring" honest without a human re-typing numbers by hand
each time a new champion is promoted: resolves the `credit_scoring`
registered model's `champion` alias, pulls that run's metrics/params, and
re-renders the page + the 3 plot images from the exact same MLflow REST
calls already documented on the page itself (`registered-models/alias`,
`runs/get`, `get-artifact`).

Not committed back to the repo — run from CI (see .github/workflows/docs.yml)
right before `mkdocs build`, so the published site always reflects whatever
model is champion *right now*, and a stale page never lingers between runs.

Deliberately tolerant of a missing/unreachable MLflow: this is a docs nicety,
not a build gate. If MLFLOW_TRACKING_URI is unset or the API call fails, it
logs a warning and leaves docs/design/model.md untouched (whatever is
already checked into the working tree — the last generated version, or the
hand-written original) rather than failing the docs build.

The metric/param key names below match the training repo's convention as of
2026-08-27 (verified against a real run — see METRICS/HYPERPARAMS below). If
the training repo's logging changes, a key will silently be skipped from its
table rather than crash — check the rendered page after any training-side
change.

Run from CI or locally:
    MLFLOW_TRACKING_URI=... MLFLOW_TRACKING_USERNAME=... MLFLOW_TRACKING_PASSWORD=... \
        uv run python scripts/generate_model_docs.py
"""

from datetime import UTC, datetime
import os
from pathlib import Path

from dotenv import load_dotenv
import httpx

MODEL_NAME = "credit_scoring"
MODEL_ALIAS = "champion"
DOCS_PAGE = Path("docs/design/model.md")
ASSETS_DIR = Path("docs/assets/model")

PLOT_ARTIFACTS = {
    "roc_curve.png": "Courbe ROC du modèle champion",
    "score_distribution.png": "Distribution des scores par classe",
    "feature_importance_top30.png": "Top 30 features par importance",
}

# (label, metric key, note, unit) — skipped from the table if the key is absent.
# Key names match this training repo's logging convention (verified against
# a real run on 2026-08-27): "test_*" for test-set metrics, unprefixed for
# metrics computed once (pr_auc, brier_score, inference_time_ms).
METRICS = [
    ("ROC-AUC", "test_roc_auc", "discrimination globale", ""),
    (
        "PR-AUC (average precision)",
        "pr_auc",
        "plus pertinente que le ROC-AUC vu le déséquilibre de classes",
        "",
    ),
    ("Precision", "test_precision", "", ""),
    ("Recall", "test_recall", "", ""),
    ("F1", "test_f1", "", ""),
    ("Log loss", "test_log_loss", "", ""),
    ("Brier score", "brier_score", "", ""),
    (
        "Coût métier",
        "test_business_cost",
        "fonction de coût définie dans le dépôt d'entraînement (pas documentée ici)",
        "",
    ),
    ("Temps d'inférence", "inference_time_ms", "mesuré côté entraînement", " ms"),
]

# (label, param key) — "best_*" prefix matches this training repo's
# hyperparameter-search convention (verified against a real run on 2026-08-27).
HYPERPARAMS = [
    ("scale_pos_weight", "scale_pos_weight"),
    ("n_estimators", "best_n_estimators"),
    ("learning_rate", "best_learning_rate"),
    ("num_leaves", "best_num_leaves"),
    ("min_child_samples", "best_min_child_samples"),
    ("subsample", "best_subsample"),
    ("colsample_bytree", "best_colsample_bytree"),
    ("reg_lambda", "best_reg_lambda"),
]


class MlflowClient:
    """Thin wrapper around the MLflow REST endpoints this script needs."""

    def __init__(self, base_url: str, username: str, password: str) -> None:
        """Configure the tracking server and its Basic Auth credentials."""
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"), auth=(username, password), timeout=30
        )

    def get_run(self, run_id: str) -> dict:
        """Fetch a single run by id."""
        response = self._client.get("/api/2.0/mlflow/runs/get", params={"run_id": run_id})
        response.raise_for_status()
        return response.json()["run"]

    def resolve_champion_run(self) -> dict:
        """Return the run dict for the registered model's current champion alias."""
        response = self._client.get(
            "/api/2.0/mlflow/registered-models/alias",
            params={"name": MODEL_NAME, "alias": MODEL_ALIAS},
        )
        response.raise_for_status()
        version = response.json()["model_version"]
        return {**self.get_run(version["run_id"]), "version": version["version"]}

    def download_artifact(self, run_id: str, artifact_path: str, output_path: Path) -> None:
        """Save one run artifact (a plot PNG) to output_path."""
        response = self._client.get(
            "/get-artifact", params={"run_id": run_id, "path": artifact_path}
        )
        response.raise_for_status()
        output_path.write_bytes(response.content)


def _metrics_by_key(run: dict) -> dict[str, float]:
    return {m["key"]: m["value"] for m in run["data"].get("metrics", [])}


def _params_by_key(run: dict) -> dict[str, str]:
    return {p["key"]: p["value"] for p in run["data"].get("params", [])}


def _format_number(value: str) -> str:
    """Render an MLflow param string as a plain int, or a float to 4 decimals."""
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.4f}".rstrip("0").rstrip(".")


def _render_metrics_rows(metrics: dict[str, float]) -> str:
    rows = [
        f"    | {label} | {metrics[key]:.4f}{unit} | {note} |"
        for label, key, note, unit in METRICS
        if key in metrics
    ]
    return "\n".join(rows)


def _render_hyperparam_rows(params: dict[str, str]) -> str:
    rows = [
        f"    | `{label}` | **{_format_number(params[key])}** |"
        for label, key in HYPERPARAMS
        if key in params
    ]
    return "\n".join(rows)


def _render_page(run: dict, run_name: str, captured_at: str) -> str:
    metrics = _metrics_by_key(run)
    params = _params_by_key(run)
    roc_auc = metrics.get("test_roc_auc")
    recall = metrics.get("test_recall")
    threshold = _format_number(params["best_threshold"]) if "best_threshold" in params else "?"

    return f"""# Modèle de scoring

Ce dépôt ne fait pas l'entraînement du modèle — c'est le dépôt de **déploiement** (voir [Accueil](../index.md)). Cette page documente le champion résolu depuis le registre MLflow externe au démarrage (`src/api/infra/mlflow_model.py`) : registre `{MODEL_NAME}`, alias `{MODEL_ALIAS}`, **version {run["version"]}**, run `{run_name}` (`{run["info"]["run_id"]}`), régénérée le {captured_at}. Tenue à jour automatiquement — à chaque push touchant la doc, et sur demande (`workflow_dispatch`, voir [CI/CD & déploiement](../operations/deployment.md)).

<div class="grid cards" markdown>

-   __ROC-AUC__

    ---

    ### {f"{roc_auc:.2f}" if roc_auc is not None else "?"}

    discrimination globale

-   __Recall__

    ---

    ### {f"{recall:.2f}" if recall is not None else "?"}

    des défauts réels détectés

-   __Seuil de décision__

    ---

    ### {threshold}

    refus si `probability >= {threshold}`

-   __Version__

    ---

    ### v{run["version"]}

    alias `{MODEL_ALIAS}`

</div>

## Contrat métier

- `decision = 1` signifie **refusé**, `decision = 0` signifie **accepté** — un score au-dessus du seuil ({threshold}) refuse le dossier.
- Ce score est une **recommandation**, pas une décision d'octroi finale au sens réglementaire : voir les limites déjà posées sur la [page d'accueil](../index.md#contexte).
- L'API ne modélise aucun circuit d'approbation ou de contestation humaine — s'il existe, il est externe à ce dépôt.

!!! info "Pourquoi le score n'est pas une probabilité calibrée"
    Le modèle est entraîné avec `scale_pos_weight={_format_number(params["scale_pos_weight"]) if "scale_pos_weight" in params else "?"}`, qui rééquilibre artificiellement la fonction de perte pour compenser le déséquilibre de classes (la classe "défaut" est minoritaire dans les données d'entraînement). Ce rééquilibrage déplace mécaniquement la distribution des scores de sortie loin d'une vraie probabilité calibrée — c'est la cause technique concrète de la remarque déjà faite dans [Scoring](api/scoring.md#post-predictions) : `probability` n'est pas une probabilité de défaut au sens statistique, seulement un score utilisé pour trancher par rapport à un seuil.

## Performance

=== "Métriques (jeu de test)"

    | Métrique | Valeur | Note |
    |---|---|---|
{_render_metrics_rows(metrics)}

=== "Hyperparamètres"

    | Paramètre | Valeur |
    |---|---|
{_render_hyperparam_rows(params)}

## Courbe ROC

![Courbe ROC du modèle champion](../assets/model/roc_curve.png)

## Distribution des scores

![Distribution des scores par classe](../assets/model/score_distribution.png)

Les deux classes se chevauchent largement — attendu pour un problème aussi déséquilibré.

## Feature importance

![Top 30 features par importance](../assets/model/feature_importance_top30.png)

Les 3 scores de solvabilité externe (`EXT_SOURCE_1/2/3`) dominent généralement ce type de jeu de données — voir le graphique ci-dessus pour le classement exact de cette version.

## Traçabilité et rafraîchissement

??? note "Comment cette page est générée, et comment la régénérer"
    Cette page n'est pas écrite à la main : `scripts/generate_model_docs.py` interroge l'API REST du serveur MLflow (`MLFLOW_TRACKING_URI`, Basic Auth) pour résoudre le champion `{MODEL_NAME}`/`{MODEL_ALIAS}`, en tire les métriques/hyperparamètres du run et télécharge ses 3 graphiques, puis réécrit ce fichier. Exécuté automatiquement avant chaque build du site (`.github/workflows/docs.yml`), jamais commité — voir [CI/CD & déploiement](../operations/deployment.md).

    ```bash
    MLFLOW_TRACKING_URI=... MLFLOW_TRACKING_USERNAME=... MLFLOW_TRACKING_PASSWORD=... \\
        uv run python scripts/generate_model_docs.py
    ```
"""


def main() -> None:
    """Regenerate the model docs page, or leave it untouched if MLflow is unreachable."""
    load_dotenv()
    mlflow_tracking_uri = os.environ.get("MLFLOW_TRACKING_URI")
    mlflow_tracking_username = os.environ.get("MLFLOW_TRACKING_USERNAME")
    mlflow_tracking_password = os.environ.get("MLFLOW_TRACKING_PASSWORD")
    if not mlflow_tracking_uri or not mlflow_tracking_username or not mlflow_tracking_password:
        print("MLFLOW_TRACKING_URI/USERNAME/PASSWORD not set — leaving model.md as-is.")
        return

    client = MlflowClient(mlflow_tracking_uri, mlflow_tracking_username, mlflow_tracking_password)
    try:
        run = client.resolve_champion_run()
    except httpx.HTTPError as exc:
        print(f"Could not reach MLflow ({exc}) — leaving model.md as-is.")
        return

    # A champion run that only converts an existing model (e.g. to ONNX for
    # inference latency) doesn't retrain, so it has no reason to re-log the
    # training hyperparameters/threshold — it points back to the run it
    # converted instead (`source_champion_run_id`). Fall back to that run's
    # params for anything the champion run itself doesn't have, so the page
    # still shows real numbers instead of "?".
    current_params = _params_by_key(run)
    source_run_id = current_params.get("source_champion_run_id")
    if "scale_pos_weight" not in current_params and source_run_id:
        source_params = _params_by_key(client.get_run(source_run_id))
        run["data"]["params"] = [
            {"key": key, "value": value}
            for key, value in {**source_params, **current_params}.items()
        ]

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    for filename in PLOT_ARTIFACTS:
        try:
            client.download_artifact(
                run["info"]["run_id"], f"plots/{filename}", ASSETS_DIR / filename
            )
        except httpx.HTTPStatusError as exc:
            # Not every champion run re-logs the diagnostic plots (e.g. an ONNX
            # conversion run promoted for its inference latency, not retrained) —
            # keep whatever plot is already committed rather than fail the build.
            print(f"Could not download plots/{filename} ({exc}) — keeping the existing file.")

    captured_at = datetime.now(UTC).strftime("%Y-%m-%d")
    DOCS_PAGE.write_text(_render_page(run, run["info"]["run_name"], captured_at))
    print(f"Regenerated {DOCS_PAGE} from {MODEL_NAME}/{MODEL_ALIAS} v{run['version']}.")


if __name__ == "__main__":
    main()
