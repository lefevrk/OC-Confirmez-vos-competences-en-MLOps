# Sécurité

## Authentification

`POST /predictions` et `GET /` (démo Gradio) sont **ouverts, sans authentification** — un choix délibéré pour ce projet d'évaluation : l'examinateur doit pouvoir tester l'API et la démo sans configurer le moindre secret. Ce n'est pas une recommandation pour un déploiement de production réel, où ces routes seraient protégées.

Seul `GET /evidently` reste gardé, en HTTP Basic (`API_TOKEN`, voir [Installation & configuration](../getting-started/configuration.md)) — pop-up navigateur natif, nom d'utilisateur ignoré, seul le mot de passe compte (`src/api/common/auth.py`, `verify_basic_auth`). `API_TOKEN` vide désactive cette dernière vérification aussi, pratique en local.

## Gestion des secrets

Tous les secrets applicatifs (`MLFLOW_TRACKING_PASSWORD`, `DATABASE_URL`, `API_TOKEN`, `HF_BUCKET_READ_TOKEN`, identifiants Alloy) vivent dans des fichiers `.env` jamais commités, ou dans les secrets GitHub Actions par environnement — table complète dans [CI/CD & déploiement](../operations/deployment.md#secrets-variables-requis). Aucun secret n'est journalisé : les logs de prédiction (voir [Monitoring](../operations/monitoring.md#logs)) ne contiennent que des métadonnées dérivées (`input_hash`, jamais les valeurs brutes des features).

## Rétention et minimisation des données

Le payload d'une prédiction (revenus, situation familiale, historique de crédit...) pourrait constituer des informations personnelles au sens large — la table `prediction_events`, qui le stocke tel quel, est donc la seule table de ce dépôt traitée comme sensible, avec purge automatique plutôt qu'une conservation indéfinie :

- Un job `pg_cron` purge automatiquement `prediction_events` — 2 jours en `release`, 90 jours en `production` (voir [Configurer Supabase](../getting-started/services/supabase.md#3-retention-des-donnees-pg_cron)).
- Le jeu de référence utilisé pour le drift ne contient que les 50 features réellement consommées par le modèle — pas les données brutes du dossier client (voir [Drift](../operations/drift-analysis.md)).
