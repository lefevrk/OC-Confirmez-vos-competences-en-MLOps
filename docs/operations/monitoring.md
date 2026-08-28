# Monitoring

Savoir si l'API tourne bien ne suffit pas — il faut aussi savoir ce qu'elle prédit et pour qui. Trois signaux séparés y répondent : des métriques Prometheus pour le débit/la latence/les décisions, des logs structurés JSON pour rejouer un événement précis, et des dashboards Grafana pour tout visualiser au même endroit.

Un unique agent Grafana Alloy collecte ces métriques et logs et les pousse vers Prometheus/Loki, réutilisé tel quel en local, en release et en prod — seule sa destination change : Prometheus/Loki locaux en dev (`compose.yml`), **Grafana Cloud** en release/prod. Le dashboard, lui, n'est pas provisionné automatiquement côté Cloud : il est importé manuellement une fois (voir [Configurer Grafana Cloud](../getting-started/services/grafana-cloud.md)), alors que la stack locale le provisionne au démarrage sans configuration à faire.

## Métriques

`GET /metrics` (`src/api/modules/health/router.py`) expose les métriques au format Prometheus. Elles sont définies dans `src/api/infra/metrics.py` :

| Métrique | Type | Labels | Rôle |
|---|---|---|---|
| `credit_scoring_http_requests_total` | Counter | `method`, `endpoint`, `status_code` | Débit HTTP |
| `credit_scoring_http_errors_total` | Counter | `method`, `endpoint`, `status_code` | Taux d'erreur |
| `credit_scoring_http_request_duration_seconds` | Histogram | `method`, `endpoint` | Latence HTTP |
| `credit_scoring_inference_duration_seconds` | Histogram | — | Latence d'inférence isolée |
| `credit_scoring_prediction_probability` | Histogram | — | Distribution des scores prédits |
| `credit_scoring_prediction_decisions_total` | Counter | `decision` | Taux de décision accepté/refusé |
| `credit_scoring_model_info` | Gauge | `model_version`, `model_alias` | Modèle chargé au démarrage |
| `credit_scoring_mlflow_errors_total` | Counter | — | Échecs de chargement MLflow |
| `credit_scoring_postgres_errors_total` | Counter | — | Indisponibilité PostgreSQL |

Deux origines distinctes, pas une seule : `ObservabilityMiddleware` (`src/api/infra/observability_middleware.py`) pose les métriques HTTP génériques (les 3 premières lignes) pour **toutes** les routes, par route template (`/predictions`, jamais l'URL brute) pour rester à cardinalité basse — mais elle ne voit qu'une requête et une réponse HTTP, jamais le résultat métier. Les métriques ML (score prédit, décision, latence d'inférence) n'existent qu'une fois `predict()` retourné : elles sont donc posées directement dans `scoring/presentation/router.py`, après chaque prédiction réussie, pas dans le middleware.

## Logs

`src/api/infra/logging.py` configure Loguru pour émettre une ligne JSON par log — timestamp, niveau, message, champs additionnels liés (`prediction_id`, `input_hash`...), et la trace complète sur `logger.exception(...)`. Exemple réel, la ligne émise à la fin d'une prédiction réussie (`scoring/services/predict.py`) :

```json
{"timestamp": "2026-08-24T10:15:32.481203+00:00", "level": "INFO", "message": "scoring_completed", "prediction_id": "b3c1e2a4-7f1a-4e3d-9c2b-1a2b3c4d5e6f", "input_hash": "a1b2c3d4e5f6", "feature_count": 50, "probability": 0.341, "decision": 0, "model_version": "4", "inference_latency_ms": 1.71}
```

Les prédictions elles-mêmes sont stockées dans PostgreSQL/Supabase plutôt que dans un moteur de recherche : l'usage est majoritairement analytique en batch (export pour le drift, purge par rétention via `pg_cron` — voir [Configurer Supabase](../getting-started/services/supabase.md)), pas de la recherche full-text sur le contenu des logs — un stockage relationnel simple suffit et coûte moins cher à opérer.

## Collecte : Grafana Alloy

`deploy/alloy/config.alloy` est le **même fichier** en local, en release et en prod — seules des variables d'environnement (`DEPLOY_ENVIRONMENT`, `COMPOSE_PROJECT_FILTER`, cibles Prometheus/Loki) changent la destination :

- `prometheus.scrape` récupère `/metrics` de l'API.
- `prometheus.exporter.cadvisor` + `prometheus.scrape` récupèrent les métriques par conteneur (CPU, mémoire, réseau).
- `discovery.docker` + `loki.source.docker` récupèrent les logs des conteneurs.
- `loki.process` extrait `level` comme label de flux (basse cardinalité) mais préserve la ligne JSON brute comme contenu — interrogeable via `| json` dans Grafana, sans risquer de dénaturer une ligne non-JSON (une trace Python brute, par exemple).
- `prometheus.remote_write` et `loki.write` envoient vers Prometheus/Loki locaux en dev, vers Grafana Cloud en release/prod.

## Deux dashboards, un seul fichier de départ

- `observability/grafana/dashboards/api-overview.json` — provisionné automatiquement dans le Grafana local (`compose.yml`), datasource `prometheus` en dur.
- `deploy/grafana/dashboards/api-overview.json` — même dashboard, avec `__inputs`/`${DS_PROMETHEUS}` pour l'import manuel dans Grafana Cloud (le provisionnement par fichier ne résout pas ce templating, contrairement à l'UI d'import).

Un unique stack Grafana Cloud sert release et prod : ils ne sont **pas** des infrastructures séparées, seulement distingués par un label `environment` injecté par Alloy, et sélectionnés via une variable `$environment` dans le dashboard.

Le dashboard couvre 6 sections : vue d'ensemble (stats clés), scores & décisions, trafic & erreurs, latence, dépendances (MLflow/PostgreSQL), infrastructure (CPU/mémoire/réseau par conteneur via cAdvisor).

![Dashboard Grafana avec du trafic réel sur l'environnement release](../assets/screenshots/grafana-dashboard-release-traffic.png)

*Le dashboard `api-overview` sur l'environnement `release`, avec du trafic réel : distribution des scores prédits dans le temps, mix accepté/refusé, latences d'inférence et HTTP. Ce que ça prouve : les métriques définies dans le code arrivent bien jusqu'au dashboard, en conditions réelles.*

## Stack locale

`compose.yml` ajoute `prometheus`, `loki`, `alloy` et `grafana` aux services existants (`api`, `postgres`). `make docker-run` démarre l'ensemble ; Grafana est accessible sur `http://localhost:3000`.
