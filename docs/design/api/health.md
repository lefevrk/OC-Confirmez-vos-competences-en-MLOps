# Health & readiness

## `GET /health`

Liveness pure : répond `200` dès que le process a démarré, sans vérifier ses dépendances.

```json
{"status": "ok"}
```

## `GET /ready`

Readiness : vérifie activement le modèle chargé et la connexion PostgreSQL.

```json
{
  "status": "ready",
  "checks": {"model": "ok", "database": "ok"}
}
```

`200` si les deux checks sont `ok`, `503` avec `status: "degraded"` sinon — le détail par dépendance permet de diagnostiquer laquelle est en cause sans consulter les logs.

## `GET /metrics`

Expose les métriques au format texte Prometheus (`prometheus_client.generate_latest()`). Voir [Monitoring](../../operations/monitoring.md#metriques) pour la liste complète et leur rôle.
