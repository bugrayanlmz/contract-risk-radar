from dataclasses import dataclass
from decimal import Decimal

from app.schemas.extraction import Category, ClauseBase, ContractFacts, Money
from app.schemas.responses import RiskFactor

RULES_VERSION = "1.0"


@dataclass
class ScoringDecision:
    score: int | None
    partial: bool
    factors: list[RiskFactor]
    warnings: list[str]


def money_ratio(amount: Money | None, rent: Money | None) -> Decimal | None:
    if amount is None or rent is None or rent.amount <= 0:
        return None
    if not amount.currency or not rent.currency or amount.currency != rent.currency:
        return None
    return amount.amount / rent.amount


def score_clause(clause: ClauseBase, facts: ContractFacts, verified: bool) -> ScoringDecision:
    if not verified:
        return ScoringDecision(
            None,
            True,
            [],
            ["Quote could not be verified; this finding is excluded from scoring and dates."],
        )
    a = clause.attributes
    factors: list[RiskFactor] = []
    inputs: dict = {}
    missing: list[str] = []

    def observe(key, value):
        if value is None:
            missing.append(key)
            return False
        inputs[key] = str(value) if isinstance(value, Decimal) else value
        return True

    def trigger(code, severity, message, **values):
        factors.append(
            RiskFactor(
                code=code,
                severity=severity,
                explanation=message,
                inputs={k: str(v) if isinstance(v, Decimal) else v for k, v in values.items()},
            )
        )

    def calendar_days(key, value, basis):
        if basis != "calendar":
            missing.append(f"{key} (known calendar-day basis required)")
            return None
        return value if observe(key, value) else None

    def fee_severity(value, code, unit):
        if observe(code, value) and value > 0:
            low, high = (
                (Decimal(1), Decimal(2)) if unit == "months of rent" else (Decimal(5), Decimal(10))
            )
            severity = 4 if value > high else 3 if value > low else 2
            trigger(
                code.upper(),
                severity,
                f"The stated charge is {value.normalize()} {unit}.",
                value=value,
            )

    match clause.category:
        case Category.AUTO_RENEWAL:
            observe("automatic", a.automatic)
            if a.automatic is True:
                trigger(
                    "AUTOMATIC_RENEWAL", 2, "The contract renews automatically.", automatic=True
                )
                if observe("renewal_months", a.renewal_months) and a.renewal_months >= 6:
                    trigger(
                        "RENEWAL_LENGTH",
                        4 if a.renewal_months >= 12 else 3,
                        "Automatic renewal commits the tenant to another extended term.",
                        renewal_months=a.renewal_months,
                    )
                days = calendar_days("notice_days", a.notice_days, a.notice_day_basis)
                if days is not None and days > 30:
                    trigger(
                        "RENEWAL_NOTICE",
                        4 if days > 60 else 3,
                        "Avoiding renewal requires notice well before the term ends.",
                        notice_days=days,
                    )
        case Category.EARLY_TERMINATION:
            observe("allowed", a.allowed)
            observe("remaining_rent_due", a.remaining_rent_due)
            if a.allowed is False:
                trigger(
                    "TERMINATION_PROHIBITED",
                    5,
                    "The clause prohibits early termination.",
                    allowed=False,
                )
            if a.remaining_rent_due is True:
                trigger(
                    "REMAINING_RENT",
                    5,
                    "Early termination requires all remaining rent.",
                    remaining_rent_due=True,
                )
            months = (
                a.fee_rent_months
                if a.fee_rent_months is not None
                else money_ratio(a.fee_amount, facts.monthly_rent)
            )
            fee_severity(months, "termination_fee", "months of rent")
        case Category.SECURITY_DEPOSIT:
            observe("refundable", a.refundable)
            observe("unrestricted_deductions", a.unrestricted_deductions)
            if a.refundable is False:
                trigger(
                    "NONREFUNDABLE_DEPOSIT",
                    5,
                    "The deposit is explicitly nonrefundable.",
                    refundable=False,
                )
            if a.unrestricted_deductions is True:
                trigger(
                    "UNRESTRICTED_DEDUCTIONS",
                    4,
                    "The landlord may make unrestricted deductions.",
                    unrestricted_deductions=True,
                )
            ratio = money_ratio(facts.deposit_amount, facts.monthly_rent)
            if observe("deposit_rent_ratio", ratio) and ratio > 1:
                trigger(
                    "DEPOSIT_SIZE",
                    4 if ratio > 2 else 3,
                    "The deposit exceeds one month's rent.",
                    deposit_rent_ratio=ratio,
                )
            days = calendar_days("return_days", a.return_days, a.return_day_basis)
            if days is not None and days > 30:
                trigger(
                    "DEPOSIT_RETURN_PERIOD",
                    3,
                    "The stated deposit return period exceeds 30 calendar days.",
                    return_days=days,
                )
        case Category.LATE_PAYMENT:
            percent = a.fee_percent_of_rent
            if percent is None:
                ratio = money_ratio(a.fee_amount, facts.monthly_rent)
                percent = ratio * 100 if ratio is not None else None
            fee_severity(percent, "late_fee", "percent of monthly rent")
            observe("accrues_daily", a.accrues_daily)
            if a.accrues_daily is True:
                trigger("DAILY_LATE_FEE", 5, "Late fees accrue every day.", accrues_daily=True)
            days = calendar_days("grace_days", a.grace_days, a.grace_day_basis)
            if days == 0:
                trigger(
                    "NO_PAYMENT_GRACE",
                    3,
                    "The clause explicitly gives no payment grace period.",
                    grace_days=0,
                )
        case Category.RENT_INCREASE:
            observe("allowed", a.allowed)
            if a.allowed is not False:
                percent = a.increase_percent
                if percent is None:
                    ratio = money_ratio(a.increase_amount, facts.monthly_rent)
                    percent = ratio * 100 if ratio is not None else None
                fee_severity(percent, "rent_increase", "percent of monthly rent")
                observe("uncapped", a.uncapped)
                if a.uncapped is True:
                    trigger(
                        "UNCAPPED_RENT_INCREASE",
                        5,
                        "The clause explicitly permits uncapped increases.",
                        uncapped=True,
                    )
                if (
                    a.allowed is True
                    and observe("minimum_interval_months", a.minimum_interval_months)
                    and a.minimum_interval_months < 12
                ):
                    trigger(
                        "FREQUENT_RENT_INCREASE",
                        4,
                        "Rent may increase less than 12 months apart.",
                        minimum_interval_months=a.minimum_interval_months,
                    )
        case Category.LANDLORD_TERMINATION:
            observe("without_cause", a.without_cause)
            if a.without_cause is True:
                trigger(
                    "TERMINATION_WITHOUT_CAUSE",
                    4,
                    "The landlord may terminate without cause.",
                    without_cause=True,
                )
            days = calendar_days("notice_days", a.notice_days, a.notice_day_basis)
            if days is not None and days < 30:
                trigger(
                    "SHORT_LANDLORD_NOTICE",
                    5 if days < 7 else 3,
                    "The landlord's termination notice period is short.",
                    notice_days=days,
                )
        case Category.TENANT_LIABILITY:
            for field, severity, code, message in [
                (
                    "unlimited",
                    5,
                    "UNLIMITED_LIABILITY",
                    "Tenant liability is explicitly unlimited.",
                ),
                (
                    "includes_landlord_negligence",
                    5,
                    "LANDLORD_NEGLIGENCE",
                    "The tenant bears liability for landlord negligence.",
                ),
                (
                    "includes_structural_repairs",
                    4,
                    "STRUCTURAL_REPAIRS",
                    "The tenant must cover structural repairs.",
                ),
                (
                    "excludes_normal_wear",
                    3,
                    "NORMAL_WEAR",
                    "Normal wear is explicitly included in tenant liability.",
                ),
            ]:
                value = getattr(a, field)
                if observe(field, value) and value is (
                    False if field == "excludes_normal_wear" else True
                ):
                    trigger(code, severity, message, **{field: value})

    warnings = [f"Not evaluated: {key}." for key in missing]
    if not inputs:
        return ScoringDecision(
            None, True, [], warnings + ["No usable scoring inputs were established."]
        )
    if not factors:
        factors.append(
            RiskFactor(
                code="NO_ESCALATION_OBSERVED",
                severity=1,
                explanation="Available verified inputs trigger no configured escalation. Missing inputs have not been evaluated.",
                inputs=inputs,
            )
        )
    return ScoringDecision(max(f.severity for f in factors), bool(missing), factors, warnings)
