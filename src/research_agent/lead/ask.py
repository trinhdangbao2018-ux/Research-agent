from pydantic import BaseModel, ValidationError
from research_agent.providers.base import ModelProvider, Usage

async def ask(provider: ModelProvider, prompt: str, schema: type[BaseModel], max_attempts: int = 3) -> tuple[BaseModel, Usage]:
    '''provider is passed in, not created inside. A test passes the fake, and a real run will pass the real provider. That's how "one argument switches the whole system offline" works.  
    prompt, schema are the same as in provider.ask.
    max_attempts: int = 3 is how many tries before giving up. = 3 is a default value: if the caller doesn't pass it, it's 3.
    It returns the same pair as provider.ask (provider object), (answer, usage).'''

    current_prompt = prompt
    for attempt in range(max_attempts):
        try:
            return await provider.ask(current_prompt, schema)
        except ValidationError as error:
            if attempt ==   max_attempts -1:
                raise
            current_prompt= (
                f"{prompt}\n\n"
                f"Your previous answer was invalid:\n{error}\n\n"
                f"Return a corrected answer."
            )
