from datetime import timedelta
from uuid import uuid4

from app.schemas.extraction import Category, ContractFacts
from app.schemas.responses import ClauseResult, ImportantDateResponse


def calculate_dates(
    facts: ContractFacts, clauses: list[ClauseResult]
) -> tuple[list[ImportantDateResponse], list[str]]:
    dates, warnings = [], []

    def add(kind, value, basis, sources, clause_id=None):
        dates.append(
            ImportantDateResponse(
                id=uuid4(),
                clause_id=clause_id,
                kind=kind,
                date=value,
                basis=basis,
                source_references=sources,
            )
        )

    if facts.start_date:
        add("contract_start", facts.start_date, "Verified contract start date.", ["start_date"])
    if facts.end_date:
        add("contract_end", facts.end_date, "Verified contract end date.", ["end_date"])
    for result in clauses:
        if not result.quote_verified:
            continue
        clause, a = result.clause, result.clause.attributes
        if clause.category == Category.AUTO_RENEWAL and a.automatic is True:
            if (
                facts.end_date
                and a.notice_days is not None
                and a.notice_day_basis == "calendar"
                and a.notice_anchor == "contract_end"
            ):
                try:
                    deadline = facts.end_date - timedelta(days=a.notice_days)
                    add(
                        "renewal_notice_deadline",
                        deadline,
                        f"Contract end date minus {a.notice_days} calendar days",
                        ["end_date", f"clause:{result.id}"],
                        result.id,
                    )
                except OverflowError:
                    warnings.append("Renewal notice deadline is outside the supported date range.")
            else:
                warnings.append(
                    "Renewal deadline unresolved: verified end date, calendar-day notice, and explicit contract-end anchor are required."
                )
        if clause.category == Category.RENT_INCREASE and a.effective_date:
            add(
                "rent_increase_effective",
                a.effective_date,
                "Effective date explicitly stated in the verified clause.",
                [f"clause:{result.id}"],
                result.id,
            )
        if clause.category == Category.SECURITY_DEPOSIT and a.return_days is not None:
            warnings.append(
                "Deposit return date unresolved: actual move-out date is not available; contract end is not a substitute."
            )
    return sorted(dates, key=lambda item: item.date), warnings
