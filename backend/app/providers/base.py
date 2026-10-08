from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel

from app.analysis.pdf import AnalysisError


@dataclass
class LlmResponse[T: BaseModel]:
    data: T
    provider: str
    model: str
    token_usage: dict[str, int]


class LlmProvider(Protocol):
    async def extract[T: BaseModel](
        self, document_text: str, instruction: str, response_model: type[T]
    ) -> LlmResponse[T]: ...


class ProviderError(AnalysisError):
    pass
