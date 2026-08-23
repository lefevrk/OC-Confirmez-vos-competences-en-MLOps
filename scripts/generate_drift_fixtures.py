"""Generate the k6 traffic fixture that ramps into a "recession" drift scenario.

Samples rows from the downloaded reference Parquet — the actual training
data, NaN included: a missing bureau/credit-card/previous-application
history is a legitimate business signal (a thinner credit file), not a
defect to filter out. Rows are shifted with a per-row `intensity` that
ramps linearly from 0 (payload 0: an untouched reference sample) to 1
(the last payload: the full recession scenario below), so that a k6 run
replaying the fixture in order shows barely any drift at first and a
clear one by the end.

The scenario is grouped into economically-coherent themes rather than one
multiplier per column — each theme documents its own direction and
rationale, since that's the story the drift notebook interprets. Ratio
formulas aren't available outside the model repo's feature engineering
code; multipliers are a stylized, directionally-reasoned proxy for debt
and employment stress, not a precise economic model.
"""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import typer

app = typer.Typer()

DEFAULT_COUNT = 10000
NON_FEATURE_COLUMNS = ("SK_ID_CURR", "TARGET")

# External credit bureau scores — the strongest predictive signal, shifted
# down directly.
EXT_SOURCE_COLUMNS = ("EXT_SOURCE_1", "EXT_SOURCE_2", "EXT_SOURCE_3")

# Employment instability: DAYS_EMPLOYED is negative (days before the
# application); shrinking its magnitude pulls it toward 0, i.e. shorter
# tenure — more recent hires/job changes in the applicant pool.
# employment_birth_ratio is a non-negative ratio derived from the same
# tenure signal and moves the same way.
EMPLOYMENT_COLUMNS = ("DAYS_EMPLOYED", "employment_birth_ratio")

# Debt-to-income burden worsens: a bigger share of income going to fixed
# obligations (annuity, previous credit) is worse; less income relative to
# the credit line is also worse — opposite multiplier directions.
RATIO_WORSE_COLUMNS = (
    "annuity_income_ratio",
    "payment_credit_ratio",
    "previous_application_credit_ratio_mean",
)
RATIO_BETTER_COLUMNS = ("income_credit_ratio",)

# Bureau (external credit) debt stress: more active/total debt and more
# overdue amounts under financial pressure.
BUREAU_STRESS_COLUMNS = (
    "bureau_active_amt_credit_sum_sum",
    "bureau_active_amt_credit_sum_mean",
    "bureau_amt_credit_sum_sum",
    "bureau_active_amt_credit_max_overdue_mean",
    "bureau_amt_credit_max_overdue_mean",
)

# Payment delinquency: paying less than owed, more days past due, more
# defaulted POS/cash installments.
PAYMENT_SHORTFALL_COLUMNS = ("installment_amt_payment_sum",)
DELINQUENCY_COLUMNS = ("installment_days_past_due_mean", "pos_sk_dpd_def_mean")
# Mixed-sign (can be a surplus or a shortfall) — shifted toward the
# negative tail by a fraction of its own spread, rather than scaled,
# since a multiplier would push a surplus the wrong way.
PAYMENT_DIFFERENCE_COLUMNS = ("installment_payment_difference_mean",)

# Credit access tightens: fewer/shorter approved previous loans, less
# credit-card drawdown, as lenders (and the applicant's own credit use)
# pull back.
CREDIT_ACCESS_COLUMNS = (
    "previous_approved_cnt_payment_mean",
    "previous_approved_cnt_payment_sum",
    "previous_cnt_payment_mean",
    "credit_card_cnt_drawings_atm_current_mean",
)


@dataclass(frozen=True)
class RecessionShiftConfig:
    """Documented, adjustable knobs for the recession drift scenario."""

    ext_source_shift: float = -0.2
    employment_scale: float = 0.4
    ratio_worse_multiplier: float = 1.5
    ratio_better_multiplier: float = 0.7
    bureau_stress_multiplier: float = 1.5
    payment_shortfall_multiplier: float = 0.7
    delinquency_multiplier: float = 1.5
    payment_difference_shift_std_fraction: float = 0.5
    credit_access_multiplier: float = 0.6
    precarious_category_share: float = 0.5
    precarious_organization_types: tuple[str, ...] = (
        "Construction",
        "Self-employed",
        "Restaurant",
        "Trade: type 7",
        "Business Entity Type 3",
    )
    precarious_occupation_types: tuple[str, ...] = (
        "Laborers",
        "Low-skill Laborers",
        "Cleaning staff",
        "Waiters/barmen staff",
        "Drivers",
    )


def _scale_toward(multiplier: float, intensity: pd.Series | float) -> pd.Series | float:
    """Interpolate a multiplicative factor between 1 (no shift) and `multiplier`."""
    return 1 + intensity * (multiplier - 1)


def apply_recession_shift(
    df: pd.DataFrame,
    config: RecessionShiftConfig = RecessionShiftConfig(),
    intensity: pd.Series | float = 1.0,
    seed: int | None = None,
) -> pd.DataFrame:
    """Return a copy of `df` shifted toward the recession scenario by `intensity`.

    `intensity` is 0 (no shift) to 1 (full scenario); it may be a scalar
    (uniform shift) or a per-row Series aligned with `df`'s index (a ramp).
    """
    shifted = df.copy()

    for column in EXT_SOURCE_COLUMNS:
        shifted[column] = (shifted[column] + intensity * config.ext_source_shift).clip(
            lower=0, upper=1
        )

    employment_scale = _scale_toward(config.employment_scale, intensity)
    for column in EMPLOYMENT_COLUMNS:
        shifted[column] = shifted[column] * employment_scale

    worse_scale = _scale_toward(config.ratio_worse_multiplier, intensity)
    for column in RATIO_WORSE_COLUMNS:
        shifted[column] = shifted[column] * worse_scale

    better_scale = _scale_toward(config.ratio_better_multiplier, intensity)
    for column in RATIO_BETTER_COLUMNS:
        shifted[column] = shifted[column] * better_scale

    bureau_scale = _scale_toward(config.bureau_stress_multiplier, intensity)
    for column in BUREAU_STRESS_COLUMNS:
        shifted[column] = shifted[column] * bureau_scale

    shortfall_scale = _scale_toward(config.payment_shortfall_multiplier, intensity)
    for column in PAYMENT_SHORTFALL_COLUMNS:
        shifted[column] = shifted[column] * shortfall_scale

    delinquency_scale = _scale_toward(config.delinquency_multiplier, intensity)
    for column in DELINQUENCY_COLUMNS:
        shifted[column] = shifted[column] * delinquency_scale

    for column in PAYMENT_DIFFERENCE_COLUMNS:
        shift_amount = intensity * config.payment_difference_shift_std_fraction * df[column].std()
        shifted[column] = shifted[column] - shift_amount

    access_scale = _scale_toward(config.credit_access_multiplier, intensity)
    for column in CREDIT_ACCESS_COLUMNS:
        shifted[column] = shifted[column] * access_scale

    rng = np.random.default_rng(seed)
    share = intensity * config.precarious_category_share
    for column, precarious_values in (
        ("ORGANIZATION_TYPE", config.precarious_organization_types),
        ("OCCUPATION_TYPE", config.precarious_occupation_types),
    ):
        mask = rng.random(len(shifted)) < share
        shifted.loc[mask, column] = rng.choice(precarious_values, size=int(mask.sum()))

    return shifted


def _to_native(value: Any) -> Any:
    """Convert a numpy scalar to a plain Python type; NaN becomes JSON null."""
    if pd.isna(value):
        return None
    return value.item() if isinstance(value, np.generic) else value


def build_payloads(
    df: pd.DataFrame,
    count: int,
    seed: int,
    config: RecessionShiftConfig = RecessionShiftConfig(),
) -> list[dict[str, Any]]:
    """Sample `count` rows and ramp their drift intensity from 0 to 1 by position."""
    sample = df.drop(columns=list(NON_FEATURE_COLUMNS)).sample(
        n=count, random_state=seed, replace=count > len(df)
    )
    sample = sample.reset_index(drop=True)
    intensity = pd.Series(np.linspace(0.0, 1.0, count), index=sample.index)
    shifted = apply_recession_shift(sample, config=config, intensity=intensity, seed=seed)
    return [
        {column: _to_native(value) for column, value in row.items()}
        for row in shifted.to_dict(orient="records")
    ]


@app.command()
def main(
    reference_path: Path = Path("data/drift/reference/serving_50_features.parquet"),
    output_path: Path = Path("scripts/k6/fixtures/drifted_payloads.json"),
    count: int = DEFAULT_COUNT,
    seed: int = 42,
) -> None:
    """Write the ramped drift fixture consumed by scripts/k6/predict_load.js."""
    reference = pd.read_parquet(reference_path)
    payloads = build_payloads(reference, count=count, seed=seed)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payloads, indent=2) + "\n")
    typer.echo(f"Wrote {len(payloads)} ramped drift payloads to {output_path}.")


if __name__ == "__main__":
    app()
