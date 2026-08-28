# Monitoring

## `GET /evidently`

Sert le rapport de drift le plus récent (`reports/drift_report.html`, généré par CI). `404` tant qu'aucun rapport n'a été généré, `401` sans les bons identifiants Basic (`API_TOKEN` — le seul endpoint encore protégé, voir [Sécurité](../security.md#authentification)).

Comment ce rapport est produit et ce qu'il montre : voir [Analyse du drift](../../operations/drift-analysis.md).
