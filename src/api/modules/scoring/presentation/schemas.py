"""Manual Pydantic schema for champion v3 serving inputs.

Required/optional and numeric bounds are audited against the training
dataset (`serving_50_features.parquet`, 307,511 rows — see
`scripts/generate_drift_fixtures.py` for the same source): a field is
optional whenever the training data actually contains missing values for
it, and gets a `ge=0`/`le=0` bound whenever the training data shows no
exception to that sign. Fields with a mixed-sign range in the training
data (e.g. `bureau_active_days_credit_enddate_min`, which can be in the
future relative to the application) are left unconstrained rather than
guessing a bound the data doesn't support.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PredictionRequest(BaseModel):
    """The 50 client-facing fields expected by the champion preprocessing pipeline."""

    model_config = ConfigDict(extra="forbid", validate_by_name=True, validate_by_alias=True)

    payment_credit_ratio: float | None = Field(None, ge=0)
    ext_source_2: float | None = Field(None, ge=0, le=1, alias="EXT_SOURCE_2")
    ext_source_1: float | None = Field(None, ge=0, le=1, alias="EXT_SOURCE_1")
    ext_source_3: float | None = Field(None, ge=0, le=1, alias="EXT_SOURCE_3")
    days_birth: int = Field(le=0, alias="DAYS_BIRTH")
    amt_annuity: float | None = Field(None, gt=0, alias="AMT_ANNUITY")
    organization_type: Literal[
        "Advertising",
        "Agriculture",
        "Bank",
        "Business Entity Type 1",
        "Business Entity Type 2",
        "Business Entity Type 3",
        "Cleaning",
        "Construction",
        "Culture",
        "Electricity",
        "Emergency",
        "Government",
        "Hotel",
        "Housing",
        "Industry: type 1",
        "Industry: type 10",
        "Industry: type 11",
        "Industry: type 12",
        "Industry: type 13",
        "Industry: type 2",
        "Industry: type 3",
        "Industry: type 4",
        "Industry: type 5",
        "Industry: type 6",
        "Industry: type 7",
        "Industry: type 8",
        "Industry: type 9",
        "Insurance",
        "Kindergarten",
        "Legal Services",
        "Medicine",
        "Military",
        "Mobile",
        "Other",
        "Police",
        "Postal",
        "Realtor",
        "Religion",
        "Restaurant",
        "School",
        "Security",
        "Security Ministries",
        "Self-employed",
        "Services",
        "Telecom",
        "Trade: type 1",
        "Trade: type 2",
        "Trade: type 3",
        "Trade: type 4",
        "Trade: type 5",
        "Trade: type 6",
        "Trade: type 7",
        "Transport: type 1",
        "Transport: type 2",
        "Transport: type 3",
        "Transport: type 4",
        "University",
        "XNA",
    ] = Field(alias="ORGANIZATION_TYPE")
    previous_approved_cnt_payment_mean: float | None = Field(None, ge=0)
    days_employed: float | None = Field(None, le=0, alias="DAYS_EMPLOYED")
    days_id_publish: int = Field(le=0, alias="DAYS_ID_PUBLISH")
    annuity_income_ratio: float | None = Field(None, ge=0)
    previous_cnt_payment_mean: float | None = Field(None, ge=0)
    bureau_active_days_credit_max: float | None = Field(None, le=0)
    installment_days_past_due_mean: float | None = Field(None, ge=0)
    amt_credit: float = Field(gt=0, alias="AMT_CREDIT")
    installment_amt_payment_sum: float | None = Field(None, ge=0)
    income_credit_ratio: float = Field(ge=0)
    bureau_days_credit_max: float | None = Field(None, le=0)
    days_registration: float = Field(le=0, alias="DAYS_REGISTRATION")
    bureau_closed_days_credit_max: float | None = Field(None, le=0)
    amt_goods_price: float | None = Field(None, gt=0, alias="AMT_GOODS_PRICE")
    code_gender: Literal["F", "M", "XNA"] = Field(alias="CODE_GENDER")
    bureau_active_days_credit_enddate_min: float | None = None
    installment_days_before_due_sum: float | None = Field(None, ge=0)
    installment_days_entry_payment_max: float | None = Field(None, le=0)
    pos_months_balance_size: float | None = Field(None, ge=0)
    installment_payment_difference_mean: float | None = None
    credit_card_cnt_drawings_atm_current_mean: float | None = Field(None, ge=0)
    employment_birth_ratio: float | None = Field(None, ge=0)
    previous_days_decision_mean: float | None = Field(None, le=0)
    bureau_active_amt_credit_sum_sum: float | None = Field(None, ge=0)
    occupation_type: Literal[
        "Accountants",
        "Cleaning staff",
        "Cooking staff",
        "Core staff",
        "Drivers",
        "HR staff",
        "High skill tech staff",
        "IT staff",
        "Laborers",
        "Low-skill Laborers",
        "Managers",
        "Medicine staff",
        "Private service staff",
        "Realty agents",
        "Sales staff",
        "Secretaries",
        "Security staff",
        "Waiters/barmen staff",
        "__MISSING__",
    ] = Field(alias="OCCUPATION_TYPE")
    installment_days_before_due_max: float | None = Field(None, ge=0)
    installment_days_entry_payment_mean: float | None = Field(None, le=0)
    previous_application_credit_ratio_mean: float | None = Field(None, ge=0)
    previous_approved_days_decision_max: float | None = Field(None, le=0)
    name_family_status: Literal[
        "Civil marriage", "Married", "Separated", "Single / not married", "Unknown", "Widow"
    ] = Field(alias="NAME_FAMILY_STATUS")
    bureau_closed_days_credit_update_mean: float | None = Field(None, le=0)
    bureau_days_credit_enddate_max: float | None = None
    previous_approved_cnt_payment_sum: float | None = Field(None, ge=0)
    bureau_active_amt_credit_max_overdue_mean: float | None = Field(None, ge=0)
    bureau_amt_credit_max_overdue_mean: float | None = Field(None, ge=0)
    installment_amt_instalment_sum: float | None = Field(None, ge=0)
    installment_days_entry_payment_sum: float | None = Field(None, le=0)
    pos_sk_dpd_def_mean: float | None = Field(None, ge=0)
    name_education_type: Literal[
        "Academic degree",
        "Higher education",
        "Incomplete higher",
        "Lower secondary",
        "Secondary / secondary special",
    ] = Field(alias="NAME_EDUCATION_TYPE")
    bureau_amt_credit_sum_sum: float | None = Field(None, ge=0)
    installment_amt_instalment_max: float | None = Field(None, ge=0)
    bureau_active_amt_credit_sum_mean: float | None = Field(None, ge=0)
    bureau_active_days_credit_update_mean: float | None = None

    def model_features(self) -> dict[str, float | int | str | None]:
        """Return model column names without any API-only transformation."""
        return self.model_dump(by_alias=True)


class PredictionResponse(BaseModel):
    """Scoring response returned by the predictions endpoint."""

    prediction_id: str = Field(description="Identifiant unique (UUID) de cette prédiction")
    probability: float = Field(
        description="Score du modèle — pas une probabilité de défaut calibrée, "
        "seulement une valeur à comparer au seuil de décision"
    )
    decision: int = Field(description="1 = dossier refusé (probability >= seuil), 0 = accepté")
    model_version: str = Field(description="Version MLflow du modèle champion ayant scoré")
