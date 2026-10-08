from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.analysis.dates import calculate_dates
from app.analysis.scoring import score_clause
from app.schemas.extraction import Category
from app.schemas.responses import ClauseResult
from tests.helpers import facts, make_clause


@pytest.mark.parametrize("months,expected", [(0, 2), (5, 2), (6, 3), (11, 3), (12, 4), (13, 4)])
def test_renewal_length_boundaries(months, expected):
    clause = make_clause(
        automatic=True, renewal_months=months, notice_days=30, notice_day_basis="calendar"
    )
    assert score_clause(clause, facts(), True).score == expected


@pytest.mark.parametrize("days,expected", [(30, 2), (31, 3), (60, 3), (61, 4)])
def test_renewal_notice_boundaries(days, expected):
    assert (
        score_clause(
            make_clause(
                automatic=True, renewal_months=1, notice_days=days, notice_day_basis="calendar"
            ),
            facts(),
            True,
        ).score
        == expected
    )


@pytest.mark.parametrize(
    "value,expected", [("0", 1), ("1", 2), ("1.0001", 3), ("2", 3), ("2.0001", 4)]
)
def test_termination_fee_boundaries(value, expected):
    assert (
        score_clause(
            make_clause(
                Category.EARLY_TERMINATION,
                allowed=True,
                remaining_rent_due=False,
                fee_rent_months=value,
            ),
            facts(),
            True,
        ).score
        == expected
    )


@pytest.mark.parametrize(
    "category,field,value,expected",
    [
        (Category.EARLY_TERMINATION, "allowed", False, 5),
        (Category.EARLY_TERMINATION, "remaining_rent_due", True, 5),
        (Category.SECURITY_DEPOSIT, "refundable", False, 5),
        (Category.SECURITY_DEPOSIT, "unrestricted_deductions", True, 4),
        (Category.LATE_PAYMENT, "accrues_daily", True, 5),
        (Category.RENT_INCREASE, "uncapped", True, 5),
        (Category.LANDLORD_TERMINATION, "without_cause", True, 4),
        (Category.TENANT_LIABILITY, "unlimited", True, 5),
        (Category.TENANT_LIABILITY, "includes_landlord_negligence", True, 5),
        (Category.TENANT_LIABILITY, "includes_structural_repairs", True, 4),
        (Category.TENANT_LIABILITY, "excludes_normal_wear", False, 3),
    ],
)
def test_boolean_risk_rules(category, field, value, expected):
    assert score_clause(make_clause(category, **{field: value}), facts(), True).score == expected


@pytest.mark.parametrize(
    "category,field",
    [(Category.LATE_PAYMENT, "fee_percent_of_rent"), (Category.RENT_INCREASE, "increase_percent")],
)
@pytest.mark.parametrize(
    "value,expected", [("0", 1), ("5", 2), ("5.0001", 3), ("10", 3), ("10.0001", 4)]
)
def test_percentage_boundaries(category, field, value, expected):
    assert score_clause(make_clause(category, **{field: value}), facts(), True).score == expected


@pytest.mark.parametrize(
    "amount,expected", [("1000", 1), ("1000.0001", 3), ("2000", 3), ("2000.0001", 4)]
)
def test_deposit_ratio_boundaries(amount, expected):
    result = score_clause(
        make_clause(
            Category.SECURITY_DEPOSIT,
            refundable=True,
            unrestricted_deductions=False,
            return_days=30,
            return_day_basis="calendar",
        ),
        facts(deposit_amount={"amount": amount, "currency": "USD"}),
        True,
    )
    assert result.score == expected


@pytest.mark.parametrize("days,expected", [(0, 5), (6, 5), (7, 3), (29, 3), (30, 1)])
def test_landlord_notice(days, expected):
    assert (
        score_clause(
            make_clause(
                Category.LANDLORD_TERMINATION,
                without_cause=False,
                notice_days=days,
                notice_day_basis="calendar",
            ),
            facts(),
            True,
        ).score
        == expected
    )


@pytest.mark.parametrize("days,expected", [(30, 1), (31, 3)])
def test_deposit_return(days, expected):
    assert (
        score_clause(
            make_clause(
                Category.SECURITY_DEPOSIT,
                refundable=True,
                unrestricted_deductions=False,
                return_days=days,
                return_day_basis="calendar",
            ),
            facts(deposit_amount={"amount": "1000", "currency": "USD"}),
            True,
        ).score
        == expected
    )


@pytest.mark.parametrize("months,expected", [(11, 4), (12, 1)])
def test_increase_interval(months, expected):
    assert (
        score_clause(
            make_clause(
                Category.RENT_INCREASE,
                allowed=True,
                increase_percent="0",
                uncapped=False,
                minimum_interval_months=months,
            ),
            facts(),
            True,
        ).score
        == expected
    )


def test_unknown_unverified_false_and_business_days():
    assert score_clause(make_clause(), facts(), True).score is None
    assert score_clause(make_clause(automatic=False), facts(), True).score == 1
    assert score_clause(make_clause(automatic=True), facts(), False).score is None
    partial = score_clause(
        make_clause(automatic=True, notice_days=100, notice_day_basis="business"), facts(), True
    )
    assert partial.score == 2 and partial.partial
    assert (
        score_clause(
            make_clause(Category.LANDLORD_TERMINATION, notice_days=0, notice_day_basis="business"),
            facts(),
            True,
        ).score
        is None
    )
    assert (
        score_clause(
            make_clause(Category.LATE_PAYMENT, grace_days=0, grace_day_basis="calendar"),
            facts(),
            True,
        ).score
        == 3
    )


def test_ratio_currencies_and_zero_denominator():
    clause = make_clause(
        Category.EARLY_TERMINATION, fee_amount={"amount": "3000", "currency": "USD"}
    )
    assert score_clause(clause, facts(), True).score == 4
    for rent in (
        {"amount": "1000", "currency": "EUR"},
        {"amount": "0", "currency": "USD"},
        {"amount": "1000", "currency": None},
    ):
        assert score_clause(clause, facts(monthly_rent=rent), True).score is None


def test_strict_validation_and_exclusive_fees():
    with pytest.raises(ValidationError):
        make_clause(automatic="true")
    with pytest.raises(ValidationError):
        make_clause(renewal_months=-1)
    with pytest.raises(ValidationError):
        make_clause(
            Category.LATE_PAYMENT,
            fee_amount={"amount": "10", "currency": "USD"},
            fee_percent_of_rent="5",
        )
    with pytest.raises(ValidationError):
        make_clause(irrelevant=True)


def result(clause, verified=True):
    return ClauseResult(
        id=uuid4(),
        clause=clause,
        quote_verified=verified,
        score=None,
        partial=True,
        risk_factors=[],
        warnings=[],
    )


def test_dates_cross_leap_month_and_missing_anchors():
    renewal = result(
        make_clause(
            automatic=True, notice_days=1, notice_day_basis="calendar", notice_anchor="contract_end"
        )
    )
    values, _ = calculate_dates(facts(start_date="2028-01-01", end_date="2028-03-01"), [renewal])
    assert next(item.date for item in values if item.kind == "renewal_notice_deadline") == date(
        2028, 2, 29
    )
    values, _ = calculate_dates(facts(end_date="2027-01-01"), [renewal])
    assert next(item.date for item in values if item.kind == "renewal_notice_deadline") == date(
        2026, 12, 31
    )
    for clause in [
        make_clause(automatic=True, notice_days=1, notice_day_basis="calendar"),
        make_clause(
            automatic=True, notice_days=1, notice_day_basis="business", notice_anchor="contract_end"
        ),
    ]:
        values, warnings = calculate_dates(facts(), [result(clause)])
        assert not any(item.kind == "renewal_notice_deadline" for item in values) and warnings
    values, _ = calculate_dates(facts(), [result(renewal.clause, False)])
    assert not any(item.kind == "renewal_notice_deadline" for item in values)


def test_increase_dates_and_no_assumed_move_out():
    increase = result(make_clause(Category.RENT_INCREASE, effective_date="2027-05-01"))
    deposit = result(
        make_clause(Category.SECURITY_DEPOSIT, return_days=10, return_day_basis="calendar")
    )
    values, warnings = calculate_dates(facts(), [increase, deposit])
    assert any(item.kind == "rent_increase_effective" for item in values)
    assert not any("deposit" in item.kind for item in values)
    assert any("move-out" in warning for warning in warnings)
