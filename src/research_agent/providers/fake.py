from pydantic import BaseModel

from research_agent.providers.base import Usage


class FakeProvider:
    def __init__(self, responses: list[dict]) -> None:
        self.responses = list(responses)   # own copy, kept on self: ask() can reach it, and popping won't empty the test's list
        self.prompts = []          # every prompt ask() receives, so tests can check what was sent 
        self.usage = Usage(input_tokens =10,output_tokens =5 )     

    async def ask(self, prompt: str, schema: type[BaseModel]) -> tuple[BaseModel, Usage]:
        self.prompts.append(prompt)

        if not self.responses:          # If there're no responsess, raise error
            raise RuntimeError(
                f"FakeProvider ran out of scripted responses on call #{len(self.prompts)} "
                f"(schema {schema.__name__}). Add another response to the test."
            )

        data = self.responses.pop(0)          # used up even if validation fails below
        answer = schema.model_validate(data)  # dict -> object, or raises ValidationError
        return answer, self.usage