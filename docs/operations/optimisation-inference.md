# Optimisation d'inférence (ONNX)

Étape 4 du cahier des charges : partir des données de monitoring réelles pour identifier un goulot d'étranglement, tester une stratégie d'optimisation, et prouver le gain sans régression. Contrainte du projet : la mécanique MLflow reste la source de vérité du modèle servi — pas de fichier modèle posé sur disque en dehors du registre, contrairement à une conversion ONNX qui bypasserait MLflow au moment du serving.

Ce dépôt ne fait pas l'entraînement ni la conversion (voir [Modèle de scoring](../design/model.md)) — la conversion ONNX et sa validation de non-régression ont été faites dans le dépôt d'entraînement, sur un modèle enregistré sous l'alias `challenger` (registre `credit_scoring`, même mécanique que `champion`).

## Goulot identifié

Mesuré en local avec `scripts/profiling/profile_predict.py` (voir [Tests & qualité](testing.md) pour le lancer), 200 appels contre le champion sklearn (v4) alors en place :

| Étage | Moyenne | Part du temps atomique |
|---|---|---|
| `validation` (Pydantic) | 0.009 ms | négligeable |
| `inference` (`model.probability`) | 2.251 ms | 53 % |
| `persistence` (écriture Postgres) | 1.999 ms | 47 % |

Le détail fonction par fonction (`cProfile`, voir le `.prof` du même run) montre que `inference` n'est pas dominé par le calcul LightGBM lui-même, mais par le **preprocessing scikit-learn** (`ColumnTransformer.transform`) et un **overhead `joblib.parallel`** — la pipeline sklearn dispatche son travail en parallèle même pour une seule ligne à la fois, ce qui est du pur overhead dans ce contexte de scoring unitaire.

## Stratégie retenue

Conversion du pipeline (preprocessing + LightGBM) en un graphe ONNX unique dans le dépôt d'entraînement, ce qui élimine précisément ce dispatch Python/joblib par appel. Côté serving, `src/api/infra/mlflow_model.py` charge ce graphe **directement via `onnxruntime`** plutôt que par `mlflow.pyfunc.load_model` générique — le wrapper `pyfunc` intégré de `mlflow.onnx` ne marshalle pas correctement un graphe à 50 entrées nommées séparément et de types mixtes (float/string), reproduit et documenté lors de l'implémentation.

Compromis assumé : `mlflow_model.py` n'est plus totalement agnostique du format de modèle (il sait qu'il charge un graphe ONNX). La résolution par alias MLflow (`champion`/`challenger`), le téléchargement et la validation du `threshold.json` restent inchangés — seul le format du fichier modèle chargé a changé.

## Validation de non-régression

Comparaison `@champion` (v4, sklearn) vs `@challenger` (v5, ONNX) sur le même jeu de test, au même seuil de décision (0.53), faite dans le dépôt d'entraînement :

| Métrique | Champion (sklearn) | Challenger (ONNX) | Écart |
|---|:---:|:---:|:---:|
| ROC-AUC | 0.7804 | 0.7804 | -7.8e-07 |
| Log loss | 0.5256 | 0.5256 | +1.3e-06 |
| Precision | 0.1977 | 0.1977 | +0 |
| Recall | 0.6528 | 0.6528 | +0 |
| F1 | 0.3035 | 0.3035 | +0 |
| Coût métier | 0.4942 | 0.4942 | +0 |

Écart de probabilité prédite entre les deux modèles, ligne par ligne sur le jeu de test : écart moyen `7.2e-07`, écart maximal `0.0172` (arrondi de précision flottante lié à la conversion, sans effet sur la décision au seuil 0.53).

## Résultat mesuré

Même protocole de profiling, 200 appels, rejoué contre le challenger ONNX :

![Latence par étage avant/après optimisation ONNX](../assets/model/onnx_inference_latency_comparison.png)

*Généré par `make plot-profile-comparison` à partir de deux runs `scripts/profiling/profile_predict.py` (`reports/profiling/baseline-sklearn_stats.json` et `challenger-onnx_stats.json`, non commités).*

| Étage | Champion (sklearn) | Challenger (ONNX) | Gain |
|---|:---:|:---:|:---:|
| `inference` | 2.251 ms | 0.107–0.266 ms selon le run | **~8 à 20×** plus rapide |
| `persistence` | 1.999 ms | 1.810–3.291 ms | inchangé (bruit Postgres normal, indépendant du modèle) |
| **Goulot dominant** | `inference` (53 %) | `persistence` (92–94 %) | le modèle n'est plus le facteur limitant |

L'inférence n'est plus un facteur significatif de la latence de `/predictions` — la persistance PostgreSQL devient de très loin le poste dominant. C'est un **second goulot, indépendant du modèle**, hors scope de cette optimisation (voir [Monitoring & métriques](monitoring.md) pour comment il est surveillé) ; à traiter séparément si nécessaire (écriture asynchrone, batching...).

!!! note "Capture Grafana à ajouter après promotion en production"
    Les deux comparaisons ci-dessus viennent d'un profiling local (`scripts/profiling/`), pas encore de trafic de production réel. Une fois le challenger promu sur l'alias `champion` et redéployé, ajouter ici une capture du dashboard Grafana (`api-overview`, section latence — voir [Monitoring & métriques](monitoring.md)) montrant la bascule visible de `credit_scoring_inference_duration_seconds` avant/après le déploiement, comme preuve en conditions réelles.

    <!--
    ![Latence d'inférence en production avant/après la bascule ONNX](../assets/screenshots/grafana-onnx-latency-comparison.png)
    -->

## Reproduire

```bash
docker compose up -d postgres
make db-migrate

# Pointer temporairement MODEL_ALIAS sur le champion actuel puis sur le challenger
# (voir .env) et relancer le profiling pour chacun :
SAMPLES=200 LABEL=baseline-sklearn make profile-predict
SAMPLES=200 LABEL=challenger-onnx make profile-predict

make plot-profile-comparison
```

Détail fonction par fonction d'un run : `uv run snakeviz reports/profiling/<label>_predict.prof`.
