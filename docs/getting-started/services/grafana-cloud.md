# Configurer Grafana Cloud

Grafana Cloud héberge le stockage Prometheus/Loki pour les environnements `release` et `production` — un unique stack partagé, distingué par le label `environment` (voir [Monitoring](../../operations/monitoring.md)). L'agent collecteur (Alloy, embarqué dans `compose.yml`/`deploy/compose.yml`) pousse vers ce stack via `remote_write`/`loki.write`. Étapes ci-dessous dans l'ordre réellement suivi, captures à l'appui.

## 1. Créer le premier stack

Après inscription sur [grafana.com](https://grafana.com/), Grafana Cloud propose immédiatement de créer un premier stack — choisir la région de déploiement (le tier gratuit suffit pour ce volume) : pour un utilisateur en France la recommendation est `EU Germany` ou `UK`.

![Création du premier stack Grafana Cloud, choix de la région](../../assets/screenshots/grafana-stack-region-setup.jpg)

Un court questionnaire optionnel aide à orienter la suite ("Skip this and show all options" pour passer directement à l'étape suivante, la configuration est totalement guidée dans cette page) :

![Questionnaire d'accueil Grafana Cloud](../../assets/screenshots/grafana-tailor-setup.jpg)

Le stack est prêt — accueil "Welcome to Grafana Cloud" :

![Accueil Grafana Cloud une fois le stack créé](../../assets/screenshots/grafana-landing.jpg)

## 2. Connecter les métriques (Prometheus)

**Connections → Add new connection**, puis rechercher "Prometheus" :

![Add new connection, recherche Prometheus](../../assets/screenshots/grafana-add-connection.jpg)

Deux options proposées — choisir **Hosted Prometheus Metrics** (l'API envoie ses métriques via Alloy, pas l'inverse) :

![Choix entre Hosted Prometheus Metrics et Prometheus Data Source](../../assets/screenshots/grafana-prometheus-connection-choice.jpg)

L'écran de configuration détaille l'installation d'Alloy et propose de générer un token d'accès directement ici (nom du token, scope `alloy-data-write`) :

![Configuration Hosted Prometheus metrics : installation Alloy + création du token](../../assets/screenshots/grafana-prometheus-hosted-config.jpg)

Une fois le token créé, Grafana Cloud génère le bloc `prometheus.remote_write` à coller dans `deploy/alloy/config.alloy` (`ALLOY_METRICS_URL`/`ALLOY_METRICS_USERNAME`/`ALLOY_API_KEY`) :

![Snippet Alloy prometheus.remote_write généré](../../assets/screenshots/grafana-alloy-prometheus-snippet.jpg)

## 3. Connecter les logs (Loki)

Même page **Add new connection**, rechercher "Hosted Logs" :

![Recherche Hosted Logs dans Add new connection](../../assets/screenshots/grafana-add-hosted-logs.jpg)

L'assistant "Logs onboarding" demande l'infrastructure source (Linux ici) :

![Assistant Logs onboarding, infrastructure Linux sélectionnée](../../assets/screenshots/grafana-logs-onboarding.jpg)

Pas besoin d'un second token : à l'étape d'authentification, choisir **Use an existing token** et réutiliser celui créé pour Prometheus (même Access Policy, scope étendu) :

![Étape "Use an API Token", réutilisation du token existant](../../assets/screenshots/grafana-logs-reuse-token.jpg)

Le bloc `loki.write` généré complète le même fichier `deploy/alloy/config.alloy` (`ALLOY_LOGS_URL`/`ALLOY_LOGS_USERNAME`) :

![Snippet Alloy loki.write généré](../../assets/screenshots/grafana-alloy-loki-snippet.jpg)

## 4. Où placer ces identifiants

- **Local** : `.env` à la racine, avec `ALLOY_METRICS_USERNAME`/`ALLOY_LOGS_USERNAME`/`ALLOY_API_KEY` vides — le stack local pointe vers le Prometheus/Loki de `compose.yml`, pas vers Grafana Cloud (voir [Installation & configuration](../configuration.md)).
- **VPS** (`release` et `production`) : une copie de `deploy/.env` sur chaque environnement plaçé à la racine — **un seul stack Grafana Cloud partagé** entre les deux, différencié uniquement par `DEPLOY_ENVIRONMENT` (`release`/`production`), pas par des identifiants distincts.

## 5. Vérifier

Dans Grafana Cloud : **Explore**, datasource Prometheus, requête `up{environment="release"}` — ou en ligne de commande :

```bash
curl -s -u "$ALLOY_METRICS_USERNAME:$ALLOY_API_KEY" \
  "https://prometheus-<region>.grafana.net/api/prom/api/v1/query?query=up"
```

## 6. Importer le dashboard

**Dashboards**, bouton **New** :

![Liste des dashboards, bouton New](../../assets/screenshots/grafana-dashboards-new-import.jpg)

Choisir **Import dashboard** dans le menu :

![Menu New, option Import dashboard](../../assets/screenshots/grafana-dashboards-new-menu.jpg)

Uploader `deploy/grafana/dashboards/api-overview.json` (ce fichier contient le templating `__inputs`/`${DS_PROMETHEUS}` qui déclenche la sélection de datasource à l'import — voir [Monitoring](../../operations/monitoring.md#deux-dashboards-un-seul-fichier-de-depart)) :

![Écran Import dashboard, upload du fichier JSON](../../assets/screenshots/grafana-import-dashboard-form.jpg)

Nommer le dashboard et sélectionner la datasource Prometheus (elle devrait avoir un nom par défaut `grafanacloud-smallelephant123-prom`) créée à l'étape 2 :

![Formulaire d'import rempli, sélection de la datasource Prometheus](../../assets/screenshots/grafana-import-dashboard-datasource.jpg)

Le dashboard est importé (ici sans trafic encore envoyé, d'où les panels "No data") :

![Dashboard importé, panels sans données](../../assets/screenshots/grafana-dashboard-imported.jpg)

## 7. Synthetic Monitoring

Grafana Cloud Synthetic Monitoring surveille les environnements de l'extérieur (checks HTTP périodiques, indépendants de l'infrastructure surveillée) — non configuré pour ce projet à ce stade. Ce qui est en place et vérifiable dès maintenant, c'est que la chaîne de bout en bout fonctionne : le même dashboard, une fois du trafic réel envoyé, remonte bien les métriques jusqu'à Grafana Cloud :

![Dashboard Grafana avec du trafic réel sur l'environnement release](../../assets/screenshots/grafana-dashboard-release-traffic.png)

*Le dashboard `api-overview` sur `release`, avec du trafic réel — voir [Monitoring](../../operations/monitoring.md#deux-dashboards-un-seul-fichier-de-depart) pour le détail des panels.*
