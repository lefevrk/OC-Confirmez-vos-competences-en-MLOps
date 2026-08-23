"""Unit tests for the manually maintained serving schema."""

from pydantic import ValidationError
import pytest
from tests.payloads import valid_payload

from api.modules.scoring.presentation.schemas import PredictionRequest


def test_schema_matches_the_frozen_field_and_alias_contract() -> None:
    """The schema's field identity and alias mapping are locked, not just their counts.

    A count alone would not catch one champion column silently swapped for
    another under a different name at the same field total. Two independent
    sets would not catch two aliases swapped between fields either (e.g.
    DAYS_BIRTH and DAYS_ID_PUBLISH) — the mapping itself must match.
    """
    expected_field_names = {
        "amt_annuity",
        "amt_credit",
        "amt_goods_price",
        "annuity_income_ratio",
        "bureau_active_amt_credit_max_overdue_mean",
        "bureau_active_amt_credit_sum_mean",
        "bureau_active_amt_credit_sum_sum",
        "bureau_active_days_credit_enddate_min",
        "bureau_active_days_credit_max",
        "bureau_active_days_credit_update_mean",
        "bureau_amt_credit_max_overdue_mean",
        "bureau_amt_credit_sum_sum",
        "bureau_closed_days_credit_max",
        "bureau_closed_days_credit_update_mean",
        "bureau_days_credit_enddate_max",
        "bureau_days_credit_max",
        "code_gender",
        "credit_card_cnt_drawings_atm_current_mean",
        "days_birth",
        "days_employed",
        "days_id_publish",
        "days_registration",
        "employment_birth_ratio",
        "ext_source_1",
        "ext_source_2",
        "ext_source_3",
        "income_credit_ratio",
        "installment_amt_instalment_max",
        "installment_amt_instalment_sum",
        "installment_amt_payment_sum",
        "installment_days_before_due_max",
        "installment_days_before_due_sum",
        "installment_days_entry_payment_max",
        "installment_days_entry_payment_mean",
        "installment_days_entry_payment_sum",
        "installment_days_past_due_mean",
        "installment_payment_difference_mean",
        "name_education_type",
        "name_family_status",
        "occupation_type",
        "organization_type",
        "payment_credit_ratio",
        "pos_months_balance_size",
        "pos_sk_dpd_def_mean",
        "previous_application_credit_ratio_mean",
        "previous_approved_cnt_payment_mean",
        "previous_approved_cnt_payment_sum",
        "previous_approved_days_decision_max",
        "previous_cnt_payment_mean",
        "previous_days_decision_mean",
    }
    expected_aliases_by_field = {
        "amt_annuity": "AMT_ANNUITY",
        "amt_credit": "AMT_CREDIT",
        "amt_goods_price": "AMT_GOODS_PRICE",
        "code_gender": "CODE_GENDER",
        "days_birth": "DAYS_BIRTH",
        "days_employed": "DAYS_EMPLOYED",
        "days_id_publish": "DAYS_ID_PUBLISH",
        "days_registration": "DAYS_REGISTRATION",
        "ext_source_1": "EXT_SOURCE_1",
        "ext_source_2": "EXT_SOURCE_2",
        "ext_source_3": "EXT_SOURCE_3",
        "name_education_type": "NAME_EDUCATION_TYPE",
        "name_family_status": "NAME_FAMILY_STATUS",
        "occupation_type": "OCCUPATION_TYPE",
        "organization_type": "ORGANIZATION_TYPE",
    }

    assert set(PredictionRequest.model_fields) == expected_field_names
    assert {
        name: field.alias for name, field in PredictionRequest.model_fields.items() if field.alias
    } == expected_aliases_by_field


def test_schema_accepts_aliases_and_preserves_model_column_names() -> None:
    """Client aliases are accepted and passed to the model without renaming."""
    payload = valid_payload()
    payload["EXT_SOURCE_2"] = 0.42

    request = PredictionRequest.model_validate(payload)

    assert request.model_features()["EXT_SOURCE_2"] == 0.42
    assert "ext_source_2" not in request.model_features()


def test_schema_allows_omitting_an_optional_feature() -> None:
    """An omitted optional input reaches the model payload as null."""
    request = PredictionRequest.model_validate(valid_payload())

    assert request.model_features()["EXT_SOURCE_1"] is None


@pytest.mark.parametrize(
    "field_name",
    ["amt_credit", "days_birth", "organization_type"],
)
def test_schema_rejects_missing_required_feature(field_name: str) -> None:
    """A missing required model input is an invalid API request."""
    payload = valid_payload()
    del payload[field_name]

    with pytest.raises(ValidationError):
        PredictionRequest.model_validate(payload)


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("payment_credit_ratio", "not-a-number"),
        ("days_birth", "not-an-integer"),
        ("organization_type", "unseen-organization"),
        ("code_gender", "unknown-gender"),
        ("occupation_type", "unknown-occupation"),
        ("name_family_status", "unknown-family-status"),
        ("name_education_type", "unknown-education"),
    ],
)
def test_schema_rejects_invalid_feature_value(
    field_name: str,
    invalid_value: str,
) -> None:
    """Invalid types and values outside closed categories fail validation."""
    payload = valid_payload()
    payload[field_name] = invalid_value

    with pytest.raises(ValidationError):
        PredictionRequest.model_validate(payload)


def test_schema_rejects_unknown_feature() -> None:
    """A field not known by the model contract is not silently accepted."""
    with pytest.raises(ValidationError):
        PredictionRequest.model_validate({**valid_payload(), "unexpected": 1})


def test_schema_rejects_an_ext_source_outside_the_unit_range() -> None:
    """External source scores are normalized and must stay within [0, 1]."""
    with pytest.raises(ValidationError):
        PredictionRequest.model_validate({**valid_payload(), "ext_source_2": 1.5})


def test_schema_rejects_a_non_positive_monetary_amount() -> None:
    """Credit, annuity and goods price amounts cannot be zero or negative."""
    with pytest.raises(ValidationError):
        PredictionRequest.model_validate({**valid_payload(), "amt_credit": 0})


@pytest.mark.parametrize(
    ("field_name", "out_of_sign_value"),
    [
        # "days"-style fields count backward from the application date and
        # are never positive in the training data.
        ("days_birth", 100),
        ("days_id_publish", 1),
        ("DAYS_EMPLOYED", 1),
        # ratios, amounts and counts are never negative in the training data.
        ("income_credit_ratio", -1),
        ("payment_credit_ratio", -0.1),
        ("installment_amt_payment_sum", -1),
    ],
)
def test_schema_rejects_a_value_outside_its_observed_sign(
    field_name: str, out_of_sign_value: float
) -> None:
    """Bounds derived from the training data reject values of the wrong sign."""
    with pytest.raises(ValidationError):
        PredictionRequest.model_validate({**valid_payload(), field_name: out_of_sign_value})


@pytest.mark.parametrize(
    "field_name",
    ["payment_credit_ratio", "EXT_SOURCE_2", "AMT_ANNUITY", "installment_amt_payment_sum"],
)
def test_schema_accepts_null_on_a_field_nullable_in_the_training_data(field_name: str) -> None:
    """Fields with real missing values in the training data accept null, not just omission."""
    request = PredictionRequest.model_validate({**valid_payload(), field_name: None})

    assert request.model_features()[field_name] is None
