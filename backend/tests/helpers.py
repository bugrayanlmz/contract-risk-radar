import asyncio
from typing import get_args

from app.providers.base import LlmResponse, ProviderError
from app.schemas.extraction import CLAUSE_MODELS, AiFindingBatch, Category, ContractFacts

TEXT = """This is a synthetic English residential rental agreement.
The lease starts January 1, 2027 and ends December 31, 2027.
Monthly rent is USD 1000.00. The security deposit is USD 2000.00.
The lease automatically renews for 12 months unless the tenant gives notice 60 calendar days before the contract end date.
Late fees accrue daily at 1 percent of monthly rent, with zero calendar days of grace.
"""


def facts(**updates):
    data = dict(
        start_date="2027-01-01",
        end_date="2027-12-31",
        monthly_rent={"amount": "1000", "currency": "USD"},
        deposit_amount={"amount": "2000", "currency": "USD"},
        evidence={
            "start_date": "The lease starts January 1, 2027 and ends December 31, 2027.",
            "end_date": "The lease starts January 1, 2027 and ends December 31, 2027.",
            "monthly_rent": "Monthly rent is USD 1000.00.",
            "deposit_amount": "The security deposit is USD 2000.00.",
        },
        warnings=[],
        contract_type="residential_rental",
        language="english",
    )
    data.update(updates)
    return ContractFacts.model_validate(data)


def make_clause(
    category=Category.AUTO_RENEWAL,
    quote="The lease automatically renews for 12 months unless the tenant gives notice 60 calendar days before the contract end date.",
    **attributes,
):
    model = CLAUSE_MODELS[category]
    attributes_model = model.model_fields["attributes"].annotation
    values = dict.fromkeys(attributes_model.model_fields, None)
    values.update(attributes)
    return model.model_validate(
        {
            "category": category,
            "quote": quote,
            "explanation": "A synthetic clause explanation.",
            "attributes": values,
        }
    )


class FakeProvider:
    """Test fixture only; never registered as an application provider."""

    def __init__(
        self, contract_facts=None, clauses=None, fail=False, ai_findings=None, fail_ai=False
    ):
        self.facts = contract_facts or facts()
        self.ai_findings, self.fail_ai = ai_findings or [], fail_ai
        self.clauses = (
            clauses
            if clauses is not None
            else [
                make_clause(
                    automatic=True,
                    renewal_months=12,
                    notice_days=60,
                    notice_day_basis="calendar",
                    notice_anchor="contract_end",
                )
            ]
        )
        self.fail, self.calls, self.active, self.max_active = fail, 0, 0, 0

    async def extract(self, text, instruction, response_model):
        self.calls += 1
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0.001)
            if response_model == ContractFacts:
                data = self.facts
            elif response_model == AiFindingBatch:
                if self.fail_ai:
                    raise ProviderError(
                        "INVALID_OUTPUT", "Additional AI review failed. Please retry.", True
                    )
                data = AiFindingBatch.model_validate({"findings": self.ai_findings})
            else:
                if self.fail:
                    raise ProviderError(
                        "INVALID_OUTPUT", "Invalid test provider output. Please retry.", True
                    )
                item_model = get_args(response_model.model_fields["clauses"].annotation)[0]
                category = get_args(item_model.model_fields["category"].annotation)[0]
                data = response_model.model_validate(
                    {
                        "clauses": [
                            clause.model_dump(mode="json")
                            for clause in self.clauses
                            if clause.category == category
                        ]
                    }
                )
            return LlmResponse(
                data, "test", "fixture-model", {"input_tokens": 10, "output_tokens": 20}
            )
        finally:
            self.active -= 1
