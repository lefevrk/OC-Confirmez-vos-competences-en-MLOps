"""Unit tests for the recession-scenario drift transform.

Pure-function tests against a small synthetic DataFrame — no real reference
data or I/O needed.
"""

import numpy as np
import pandas as pd
import pytest
from scripts.generate_drift_fixtures import (
    RecessionShiftConfig,
    apply_recession_shift,
    build_payloads,
)


def _synthetic_reference(size: int = 500) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    return pd.DataFrame(
        {
            "SK_ID_CURR": np.arange(size),
            "TARGET": rng.integers(0, 2, size),
            "EXT_SOURCE_1": rng.uniform(0.3, 0.9, size),
            "EXT_SOURCE_2": rng.uniform(0.3, 0.9, size),
            "EXT_SOURCE_3": rng.uniform(0.3, 0.9, size),
            "DAYS_EMPLOYED": rng.uniform(-6000, -100, size),
            "employment_birth_ratio": rng.uniform(0.0, 0.3, size),
            "income_credit_ratio": rng.uniform(0.1, 1.0, size),
            "annuity_income_ratio": rng.uniform(0.05, 0.5, size),
            "payment_credit_ratio": rng.uniform(0.05, 0.5, size),
            "previous_application_credit_ratio_mean": rng.uniform(0.1, 1.0, size),
            "bureau_active_amt_credit_sum_sum": rng.uniform(0, 100000, size),
            "bureau_active_amt_credit_sum_mean": rng.uniform(0, 50000, size),
            "bureau_amt_credit_sum_sum": rng.uniform(0, 100000, size),
            "bureau_active_amt_credit_max_overdue_mean": rng.uniform(0, 5000, size),
            "bureau_amt_credit_max_overdue_mean": rng.uniform(0, 5000, size),
            "installment_amt_payment_sum": rng.uniform(1000, 50000, size),
            "installment_days_past_due_mean": rng.uniform(0, 30, size),
            "pos_sk_dpd_def_mean": rng.uniform(0, 10, size),
            "installment_payment_difference_mean": rng.uniform(-5000, 5000, size),
            "previous_approved_cnt_payment_mean": rng.uniform(5, 40, size),
            "previous_approved_cnt_payment_sum": rng.uniform(5, 200, size),
            "previous_cnt_payment_mean": rng.uniform(5, 40, size),
            "credit_card_cnt_drawings_atm_current_mean": rng.uniform(0, 10, size),
            "ORGANIZATION_TYPE": "Bank",
            "OCCUPATION_TYPE": "Accountants",
        }
    )


def test_ext_source_columns_are_shifted_down_and_stay_in_range() -> None:
    """Full-intensity shift pulls external credit scores down, clipped to [0, 1]."""
    reference = _synthetic_reference()

    shifted = apply_recession_shift(reference, intensity=1.0, seed=1)

    for column in ("EXT_SOURCE_1", "EXT_SOURCE_2", "EXT_SOURCE_3"):
        assert shifted[column].mean() < reference[column].mean()
        assert shifted[column].min() >= 0
        assert shifted[column].max() <= 1


def test_employment_columns_move_toward_zero() -> None:
    """Shorter average tenure: DAYS_EMPLOYED (negative) and its ratio shrink toward 0."""
    reference = _synthetic_reference()

    shifted = apply_recession_shift(reference, intensity=1.0, seed=1)

    assert shifted["DAYS_EMPLOYED"].abs().mean() < reference["DAYS_EMPLOYED"].abs().mean()
    assert shifted["employment_birth_ratio"].mean() < reference["employment_birth_ratio"].mean()


def test_ratio_columns_move_in_their_documented_direction() -> None:
    """Debt-burden ratios worsen; income_credit_ratio (inverse) improves-labeled-worse."""
    reference = _synthetic_reference()

    shifted = apply_recession_shift(reference, intensity=1.0, seed=1)

    for column in ("annuity_income_ratio", "payment_credit_ratio"):
        assert shifted[column].mean() > reference[column].mean()
    assert shifted["income_credit_ratio"].mean() < reference["income_credit_ratio"].mean()


def test_bureau_stress_columns_increase() -> None:
    """More active/total debt and overdue amounts under financial pressure."""
    reference = _synthetic_reference()

    shifted = apply_recession_shift(reference, intensity=1.0, seed=1)

    for column in (
        "bureau_active_amt_credit_sum_sum",
        "bureau_amt_credit_max_overdue_mean",
    ):
        assert shifted[column].mean() > reference[column].mean()


def test_payment_delinquency_worsens() -> None:
    """Less paid, more days past due, more shortfall."""
    reference = _synthetic_reference()

    shifted = apply_recession_shift(reference, intensity=1.0, seed=1)

    assert (
        shifted["installment_amt_payment_sum"].mean()
        < reference["installment_amt_payment_sum"].mean()
    )
    assert (
        shifted["installment_days_past_due_mean"].mean()
        > reference["installment_days_past_due_mean"].mean()
    )
    assert (
        shifted["installment_payment_difference_mean"].mean()
        < reference["installment_payment_difference_mean"].mean()
    )


def test_credit_access_tightens() -> None:
    """Fewer/shorter approved previous loans and less credit-card drawdown."""
    reference = _synthetic_reference()

    shifted = apply_recession_shift(reference, intensity=1.0, seed=1)

    for column in (
        "previous_approved_cnt_payment_mean",
        "credit_card_cnt_drawings_atm_current_mean",
    ):
        assert shifted[column].mean() < reference[column].mean()


def test_precarious_category_share_increases() -> None:
    """A configured share of rows move to precarious organization/occupation types."""
    reference = _synthetic_reference(size=2000)
    config = RecessionShiftConfig(precarious_category_share=0.4)

    shifted = apply_recession_shift(reference, config=config, intensity=1.0, seed=1)

    precarious_share = (
        shifted["ORGANIZATION_TYPE"].isin(config.precarious_organization_types).mean()
    )
    assert precarious_share == pytest.approx(config.precarious_category_share, abs=0.05)


def test_zero_intensity_is_the_identity() -> None:
    """intensity=0 leaves every column exactly as sampled from the reference."""
    reference = _synthetic_reference()

    shifted = apply_recession_shift(reference, intensity=0.0, seed=1)

    pd.testing.assert_frame_equal(shifted, reference)


def test_build_payloads_ramps_intensity_from_zero_to_one() -> None:
    """The first payload matches the untouched sample; the last matches full intensity."""
    reference = _synthetic_reference(size=200)

    payloads = build_payloads(reference, count=200, seed=7)

    assert payloads[0]["EXT_SOURCE_2"] != pytest.approx(payloads[-1]["EXT_SOURCE_2"])
    # The first payload isn't shifted: its EXT_SOURCE_2 must still be a value
    # actually present in the reference (untouched sampling, intensity 0).
    assert payloads[0]["EXT_SOURCE_2"] in reference["EXT_SOURCE_2"].to_numpy()


def test_build_payloads_preserves_nan_as_json_null() -> None:
    """A NaN in the reference becomes an explicit null, not a dropped row."""
    reference = _synthetic_reference(size=50)
    reference.loc[0, "EXT_SOURCE_1"] = float("nan")

    payloads = build_payloads(reference, count=50, seed=1)

    assert any(payload["EXT_SOURCE_1"] is None for payload in payloads)
    assert len(payloads) == 50
