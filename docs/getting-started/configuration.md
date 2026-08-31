# Installation & configuration

Tout ce qu'il faut pour faire tourner l'API en local, avec ou sans la stack de monitoring complète — du plus rapide (un `uvicorn` nu) au plus complet (Docker Compose avec Prometheus/Loki/Grafana). Les services externes réels (MLflow, Supabase, Grafana Cloud, bucket Hugging Face) ont chacun leur propre tutoriel pas-à-pas dans [Services externes](services/grafana-cloud.md).

## Prérequis

- Python 3.12, [uv](https://docs.astral.sh/uv/getting-started/installation/) pour la gestion des dépendances.
- [Docker](https://docs.docker.com/get-started/get-docker/) et Docker Compose pour la stack locale complète (API + PostgreSQL + monitoring).
- [k6](https://grafana.com/docs/k6/latest/set-up/install-k6/) pour la simulation de trafic drifté (voir [Génération du trafic de drift](../operations/drift-generation.md)) — optionnel, pas requis pour lancer l'API.
- Un accès à un serveur MLflow (registre de modèles) — le modèle lui-même est entraîné et versionné dans un dépôt séparé.
- Une base PostgreSQL accessible et migrée — uniquement pour un lancement sans Docker (`make docker-run` la fournit).

## Installation

```bash
make requirements    # dépendances runtime de l'API (uv sync --extra api)
make setup-hooks     # git hooks (pre-commit, pre-push)
```

Groupes de dépendances additionnels, installés séparément pour ne pas alourdir l'environnement quotidien :

| Groupe | Contenu | Commande |
|---|---|---|
| `dev` | pytest, ruff, pyright, pre-commit, testcontainers | `uv sync` (inclus par défaut) |
| `drift` | Evidently, Jupyter, outils d'analyse de drift | `make drift-requirements` |
| `docs` | mkdocs, mkdocs-material | `make docs-requirements` |

## Lancer l'API

=== "Docker Compose (stack complète)"

    ```bash
    make docker-run
    ```

    Build l'image, migre la base, puis démarre l'API, PostgreSQL, et toute la stack de monitoring (Prometheus, Loki, Alloy, Grafana — voir [Monitoring](../operations/monitoring.md)).

=== "Local (uvicorn)"

    ```bash
    make requirements
    make db-migrate
    make run
    ```

    Suppose une base PostgreSQL déjà lancée (par exemple `docker compose up -d postgres`) et les variables d'environnement déjà configurées (section suivante). `make db-migrate` applique les migrations sur cette base, puis `make run` démarre l'API en local avec autoreload sur `http://localhost:8000`.

## Variables d'environnement

Quatre groupes, selon qui les lit : l'application elle-même au démarrage, les scripts de drift, la stack de monitoring locale, ou le VPS de déploiement — jamais les mêmes secrets au même endroit deux fois. Lues via `pydantic-settings` (`src/api/infra/config.py`, fichier `.env` à la racine) pour les variables applicatives, ou directement par les scripts/workflows pour le reste. `.env.example` (local) et `deploy/.env.example` (VPS) documentent chaque valeur.

!!! warning "Un `$` dans une valeur casse l'interpolation Docker Compose"
    Docker Compose interpole le `.env` qu'il lit (pour son propre `${VAR}` dans `compose.yml`) — un secret généré aléatoirement qui contient un `$` (un mot de passe, un token) y est donc lu comme le début d'une référence de variable, avec un avertissement `variable is not set` et une valeur tronquée au runtime. Entourer la valeur de guillemets simples suffit à la préserver telle quelle :
    ```dotenv
    API_TOKEN='secret-avec-$'
    ```

### Applicatives (`Settings`)

| Variable | Obligatoire | Défaut | Rôle |
|---|---|---|---|
| `MLFLOW_TRACKING_URI` | oui | — | URL du serveur MLflow (registre de modèles) |
| `MLFLOW_TRACKING_USERNAME` | oui | — | Identifiant MLflow |
| `MLFLOW_TRACKING_PASSWORD` | oui | — | Mot de passe MLflow |
| `DATABASE_URL` | oui | — | Connexion PostgreSQL (stockage des prédictions) |
| `MODEL_NAME` | non | `credit_scoring` | Nom du modèle enregistré dans MLflow |
| `MODEL_ALIAS` | non | `champion` | Alias de la version à servir |
| `LOG_LEVEL` | non | `INFO` | Niveau de log |
| `API_TOKEN` | non | *(vide)* | Mot de passe Basic sur `GET /evidently` (seule route encore gardée, voir [Sécurité](../design/security.md#authentification)) — vide désactive cette vérification, pratique en local |
| `SCORING_API_URL` | non | `http://127.0.0.1:8000` | URL de `POST /predictions` utilisée par l'UI Gradio ; définir l'URL HTTPS publique derrière le reverse proxy en production |
| `REPORTS_DIR` | non | `reports` | Répertoire où `GET /evidently` lit le rapport de drift généré |

### Drift (scripts uniquement, jamais lues par l'API)

| Variable | Rôle |
|---|---|
| `HF_BUCKET_ID` | Identifiant du bucket privé contenant le jeu de référence |
| `HF_BUCKET_READ_TOKEN` | Token en lecture seule pour ce bucket |

### Monitoring local (`compose.yml`)

| Variable | Rôle |
|---|---|
| `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD` | Identifiants du Grafana local |
| `DEPLOY_ENVIRONMENT` | Label `environment` injecté par Alloy (`local` en dev) |
| `COMPOSE_PROJECT_FILTER` / `APP_SERVICES_FILTER` | Filtrent quels conteneurs cAdvisor surveille |
| `ALLOY_METRICS_URL` / `ALLOY_LOGS_URL` (+ `_USERNAME`, `ALLOY_API_KEY`) | Cible du `remote_write`/`loki.write` d'Alloy — Prometheus/Loki locaux en dev, Grafana Cloud en release/prod (voir [Monitoring](../operations/monitoring.md)) |

### Déploiement VPS (`deploy/.env.example`, jamais commité avec de vraies valeurs)

| Variable | Rôle |
|---|---|
| `IMAGE_TAG` | Tag de l'image à déployer (`release` ou `prod`) |
| `HOST_PORT` | Port publié sur le VPS pour cet environnement |
| `DEPLOY_ENVIRONMENT` | `release` ou `production` |

## Référence complète des commandes (`Makefile`)

Tout ce qui précède se résume à quelques commandes `make` — la liste complète ci-dessous, regroupée par usage (général, analyse de drift, profiling, documentation). Les 24 commandes disponibles (`make help` régénère cette liste à partir des commentaires du `Makefile`, toujours à jour) :

**Général**

| Commande | Effet |
|---|---|
| `make requirements` | Installe les dépendances Python (API + dev) |
| `make all-requirements` | Installe tous les groupes et extras (API + dev + drift + docs) — tout ce qu'il faut pour la suite de tests complète |
| `make run` | Démarre l'API en local avec autoreload |
| `make docker-build` | Build l'image Docker de l'API |
| `make docker-run` | Build, migre, puis démarre la stack Docker complète |
| `make docker-down` | Arrête la stack Docker Compose locale |
| `make db-migrate` | Rejoue les migrations sans redémarrer une stack déjà lancée |
| `make clean` | Supprime les fichiers Python compilés |
| `make lint` | Lint avec ruff (vérification seule) |
| `make format` | Formate le code source avec ruff |
| `make test` | Lance les tests (si pytest est installé) |
| `make create-environment` | Crée l'environnement virtuel Python |
| `make setup-hooks` | Installe les git hooks (pre-commit, pre-push) |

**Analyse de drift** (voir [Génération du trafic de drift](../operations/drift-generation.md) et [Analyse du drift](../operations/drift-analysis.md))

| Commande | Effet |
|---|---|
| `make drift-requirements` | Installe l'outillage de drift (Evidently, fixtures k6, notebook) |
| `make export-drift-tracking` | Exporte `prediction_events` vers un Parquet local |
| `make download-drift-reference` | Télécharge le jeu de référence depuis le bucket HF privé |
| `make generate-drift-fixtures` | Génère la fixture k6 à intensité croissante |
| `make generate-drift-report` | Analyse les prédictions récentes et écrit `reports/drift_report.html`/`drift_summary.md` |
| `make load-test-drift` | Rejoue la fixture contre `BASE_URL` (~15 min ; `SLEEP_SECONDS=0` pour vitesse max) |

**Profiling** (voir [Optimisation d'inférence (ONNX)](../operations/optimisation-inference.md))

| Commande | Effet |
|---|---|
| `make profile-predict` | Profile le chemin de requête réel (écrit `reports/profiling/<label>_*`) |
| `make plot-profile-comparison` | Génère un graphique de latence avant/après à partir de deux runs `profile-predict` |

**Documentation**

| Commande | Effet |
|---|---|
| `make docs-requirements` | Installe l'outillage de documentation (mkdocs, mkdocs-material) |
| `make docs-serve` | Sert la documentation en local avec rechargement à chaud |
| `make docs-build` | Build le site statique dans `./site` |
