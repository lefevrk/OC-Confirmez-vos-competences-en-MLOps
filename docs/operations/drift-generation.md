# Génération du trafic de drift

Pour vérifier qu'une détection de dérive fonctionne vraiment, il faut un trafic dont on connaît *exactement* l'intensité de dérive — sinon impossible de dire si une alerte est juste ou un faux positif. L'idée simple retenue ici : prendre de vraies lignes du jeu de référence et les décaler progressivement, jamais inventer de données synthétiques.

Deux scripts distincts, un pour générer les données, un pour les rejouer contre l'API — pensés pour tourner en local plutôt qu'en CI, pas automatisés, volontairement manuels.

## Générer les données : `scripts/generate_drift_fixtures.py`

Construit un scénario de "récession" économique en déplaçant progressivement des groupes de features cohérents (scores externes, emploi, ratios d'endettement, stress bureau, délinquance de paiement, accès au crédit, catégories socio-professionnelles précaires), à partir d'un échantillon du jeu de référence réel.

L'intensité du décalage suit une interpolation linéaire, `_scale_toward()` :

```python
def _scale_toward(multiplier: float, intensity: float) -> float:
    return 1 + intensity * (multiplier - 1)
```

Exemple concret pour le groupe "ratio d'endettement qui empire" (`ratio_worse_multiplier = 1.5`) :

| Intensité | Facteur appliqué | Effet |
|---|---|---|
| 0.0 (payload 0) | 1.0 | valeur inchangée |
| 0.5 (milieu de la fixture) | 1.25 | +25 % |
| 1.0 (dernier payload) | 1.5 | +50 % |

La fixture entière (`scripts/k6/fixtures/drifted_payloads.json`, 10 000 payloads par défaut) a son intensité répartie linéairement de 0 à 1 sur l'ensemble des lignes — le payload 0 est un exemple de référence non modifié, le dernier est le scénario de récession complet.

## Rejouer le trafic : `scripts/k6/predict_load.js`

Rejoue la fixture contre `POST /predictions`, avec une contrainte précise : la dérive doit être visible dans le **temps réel** (sur le dashboard Grafana pendant que le test tourne), pas seulement dans l'ordre des données. Avec 20 utilisateurs virtuels (VUs) tournant en parallèle, il faut que chaque "tick" (une itération de chaque VU) consomme des payloads *consécutifs* de la fixture, pas des payloads espacés :

```javascript
const index = __ITER * VUS + (__VU - 1);
```

À l'itération 0, les 20 VUs consomment les payloads 0 à 19 (peu de dérive) ; à l'itération 499 (la dernière, pour 10 000 payloads / 20 VUs), ils consomment 9980 à 9999 (dérive complète). Sans ce calcul, chaque tick mélangerait des payloads à faible et forte intensité, et la progression ne serait plus visible sur un dashboard qui agrège en temps réel.

## Bout en bout

```bash
make download-drift-reference   # télécharge le jeu de référence (bucket HF)
make generate-drift-fixtures    # génère scripts/k6/fixtures/drifted_payloads.json
make load-test-drift            # rejoue contre BASE_URL (localhost par défaut, ~15 min)
make generate-drift-report      # analyse les prédictions qui viennent d'être enregistrées
```

Le résultat observable : le dashboard Grafana local montre le trafic et les scores prédits dériver progressivement pendant les ~15 minutes du test, puis `make generate-drift-report` confirme la détection — voir [Analyse du drift](drift-analysis.md).

`BASE_URL` pointe par défaut sur `http://localhost:8000` — le script avertit explicitement dans ses commentaires contre un usage pointé vers le VPS de prod, qui injecterait du trafic synthétique dans le monitoring réel.
