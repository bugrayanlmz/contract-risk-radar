from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_serializer, model_validator

SCHEMA_VERSION = "2.0"
AI_RUBRIC_VERSION = "1.0"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Money(StrictModel):
    amount: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    currency: str | None = Field(pattern=r"^[A-Z]{3}$")

    @field_serializer("amount")
    def serialize_amount(self, value: Decimal) -> str:
        return format(value, "f")


class Category(StrEnum):
    AUTO_RENEWAL = "AUTO_RENEWAL"
    EARLY_TERMINATION = "EARLY_TERMINATION"
    SECURITY_DEPOSIT = "SECURITY_DEPOSIT"
    LATE_PAYMENT = "LATE_PAYMENT"
    RENT_INCREASE = "RENT_INCREASE"
    LANDLORD_TERMINATION = "LANDLORD_TERMINATION"
    TENANT_LIABILITY = "TENANT_LIABILITY"


Days = Annotated[int, Field(strict=True, ge=0, le=36500)]
Months = Annotated[int, Field(strict=True, ge=0, le=1200)]
Percent = Annotated[Decimal, Field(ge=0, le=10000, max_digits=10, decimal_places=4)]
DayBasis = Literal["calendar", "business", "unspecified"]
Quote = Annotated[str, Field(min_length=1, max_length=12000)]


class ContractEvidence(StrictModel):
    start_date: Quote | None
    end_date: Quote | None
    monthly_rent: Quote | None
    deposit_amount: Quote | None


class ContractFacts(StrictModel):
    start_date: date | None
    end_date: date | None
    monthly_rent: Money | None
    deposit_amount: Money | None
    evidence: ContractEvidence
    warnings: list[str] = Field(max_length=30)
    contract_type: Literal["residential_rental", "other", "unknown"]
    language: Literal["english", "german", "other", "unknown"]

    @model_validator(mode="after")
    def dates_ordered(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("Conflicting dates must be returned as null with a warning.")
        return self


class AutoRenewalAttributes(StrictModel):
    automatic: StrictBool | None
    renewal_months: Months | None
    notice_days: Days | None
    notice_day_basis: DayBasis | None
    notice_anchor: Literal["contract_end", "other"] | None


class EarlyTerminationAttributes(StrictModel):
    allowed: StrictBool | None
    fee_amount: Money | None
    fee_rent_months: Percent | None
    remaining_rent_due: StrictBool | None

    @model_validator(mode="after")
    def exclusive_fee(self):
        if self.fee_amount is not None and self.fee_rent_months is not None:
            raise ValueError("Use only one representation of the termination fee.")
        return self


class SecurityDepositAttributes(StrictModel):
    refundable: StrictBool | None
    return_days: Days | None
    return_day_basis: DayBasis | None
    unrestricted_deductions: StrictBool | None


class LatePaymentAttributes(StrictModel):
    fee_amount: Money | None
    fee_percent_of_rent: Percent | None
    grace_days: Days | None
    grace_day_basis: DayBasis | None
    accrues_daily: StrictBool | None

    @model_validator(mode="after")
    def exclusive_fee(self):
        if self.fee_amount is not None and self.fee_percent_of_rent is not None:
            raise ValueError("Use only one representation of the late fee.")
        return self


class RentIncreaseAttributes(StrictModel):
    allowed: StrictBool | None
    increase_amount: Money | None
    increase_percent: Percent | None
    minimum_interval_months: Months | None
    uncapped: StrictBool | None
    effective_date: date | None

    @model_validator(mode="after")
    def exclusive_amount(self):
        if self.increase_amount is not None and self.increase_percent is not None:
            raise ValueError("Use only one representation of the rent increase.")
        return self


class LandlordTerminationAttributes(StrictModel):
    without_cause: StrictBool | None
    notice_days: Days | None
    notice_day_basis: DayBasis | None


class TenantLiabilityAttributes(StrictModel):
    unlimited: StrictBool | None
    includes_landlord_negligence: StrictBool | None
    includes_structural_repairs: StrictBool | None
    excludes_normal_wear: StrictBool | None


class ClauseBase(StrictModel):
    quote: Quote
    explanation: str = Field(min_length=1, max_length=3000)


class AutoRenewalClause(ClauseBase):
    category: Literal[Category.AUTO_RENEWAL]
    attributes: AutoRenewalAttributes


class EarlyTerminationClause(ClauseBase):
    category: Literal[Category.EARLY_TERMINATION]
    attributes: EarlyTerminationAttributes


class SecurityDepositClause(ClauseBase):
    category: Literal[Category.SECURITY_DEPOSIT]
    attributes: SecurityDepositAttributes


class LatePaymentClause(ClauseBase):
    category: Literal[Category.LATE_PAYMENT]
    attributes: LatePaymentAttributes


class RentIncreaseClause(ClauseBase):
    category: Literal[Category.RENT_INCREASE]
    attributes: RentIncreaseAttributes


class LandlordTerminationClause(ClauseBase):
    category: Literal[Category.LANDLORD_TERMINATION]
    attributes: LandlordTerminationAttributes


class TenantLiabilityClause(ClauseBase):
    category: Literal[Category.TENANT_LIABILITY]
    attributes: TenantLiabilityAttributes


ExtractedClause = Annotated[
    AutoRenewalClause
    | EarlyTerminationClause
    | SecurityDepositClause
    | LatePaymentClause
    | RentIncreaseClause
    | LandlordTerminationClause
    | TenantLiabilityClause,
    Field(discriminator="category"),
]

CLAUSE_MODELS = {
    Category.AUTO_RENEWAL: AutoRenewalClause,
    Category.EARLY_TERMINATION: EarlyTerminationClause,
    Category.SECURITY_DEPOSIT: SecurityDepositClause,
    Category.LATE_PAYMENT: LatePaymentClause,
    Category.RENT_INCREASE: RentIncreaseClause,
    Category.LANDLORD_TERMINATION: LandlordTerminationClause,
    Category.TENANT_LIABILITY: TenantLiabilityClause,
}


class ClauseBatch[T: ClauseBase](StrictModel):
    clauses: list[T] = Field(max_length=30)


class AiFinding(StrictModel):
    title: str = Field(min_length=1, max_length=120)
    related_category: Category | None
    quote: Quote
    explanation: str = Field(min_length=1, max_length=3000)
    model_score: int = Field(strict=True, ge=1, le=5)
    rationale: str = Field(min_length=1, max_length=2000)
    uncertainties: list[str] = Field(max_length=5)


class AiFindingBatch(StrictModel):
    findings: list[AiFinding] = Field(max_length=20)
