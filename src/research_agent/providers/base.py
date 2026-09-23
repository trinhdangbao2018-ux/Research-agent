#▎ base.py defines a Python interface/protocool (a rule, checked at type-check time)

from typing import Protocol
from pydantic import BaseModel

# This contain the input token and output token
class Usage(BaseModel):
    """Real token counts returned by a provider after a call, for engine/budget.py."""
    input_tokens: int
    output_tokens: int

# This is the protocol for base.py and fake.py
class ModelProvider(Protocol):
    async def ask(self, prompt: str, schema: type[BaseModel]) -> tuple[BaseModel, Usage]:
        ...