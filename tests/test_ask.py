import pytest
from pydantic import ValidationError

from research_agent.lead.ask import ask
from research_agent.models import Task
from research_agent.providers.base import Usage
from research_agent.providers.fake import FakeProvider


# 1. A good answer on the first try comes straight back, with no retry.
async def test_valid_first_answer_is_returned():
    fake = [{"id": "t1", "question": "Q1?"}]            # dict
    provider_object = FakeProvider(fake)                # create fake provider object to plug to ask
    tasking = ask(provider_object, "promt", Task)       # plug fake provider object, a fake "prompt" that not really important at this part, and a schema task from module models
    answer, usage = await tasking                       # async func ask reutrn [schema, Usage] the schema have form of Task from module models
    assert answer == Task(id = "t1", question = "Q1?")
    assert len(provider_object.prompts) == 1
    assert usage  == Usage(input_tokens=10, output_tokens=5)



# 2. A bad answer is retried, and the good one after it is returned.
async def test_bad_answer_is_retried():
    fake = [{"id": "t1"}, {"id": "t1", "question": "Q1?"}]
    provider_object = FakeProvider(fake)
    tasking = ask(provider_object, "prompt", Task)
    answer, usage = await tasking
    assert answer == Task(id ="t1", question = "Q1?")
    assert len(provider_object.prompts) == 2
    assert usage  == Usage(input_tokens=10, output_tokens=5)



# 3. The retry prompt carries the validation error, so the model can fix its mistake.
async def test_retry_prompt_contains_the_error():
    prompt = "Split: is coffee bad for the heart?"
    script = [{"id": "t1"}, {"id": "t1", "question": "Q1?"}]
    fake = FakeProvider(script)

    await ask(fake, prompt, Task)

    first, second = fake.prompts
    assert first == prompt                  # 1st try: sent exactly as given
    assert second.startswith(prompt)        # retry keeps the prompt question
    assert "question" in second               # names the field that was wrong
    assert "Field required" in second         # says what was wrong with it



# 4. After max_attempts bad answers, ask gives up and raises. It never tries a 4th time.
async def test_gives_up_after_max_attempts():
    fake = [{"id": "t1"}, {"id": "t1"}, {"id": "t1"}, {"id": "t1", "question": "Q1?"}] 
    provider_object = FakeProvider(fake)
    tasking = ask(provider_object, "prompt", Task)
    with pytest.raises(ValidationError):
        await tasking                           # the error happens here and is caught
    assert len(provider_object.responses) == 1    # runs after, because the error was caught
    assert len(provider_object.prompts) == 3      # The fail after max attempt



# 5. A max_attempts passed in by the caller is respected.
async def test_max_attempts_is_respected():
    fake = [{"id": "t1"}, {"id": "t1", "question": "Q1?"}]
    provider_object = FakeProvider(fake)
    tasking = ask(provider_object, "prompt", Task, max_attempts = 1)
    with pytest.raises(ValidationError):
        await tasking
    assert len(provider_object.responses) == 1
    assert len(provider_object.prompts) == 1



# 6. Usage from the provider is passed through unchanged, for engine/budget.py.
async def test_usage_is_passed_through():
    fake = [{"id": "t1", "question": "Q1?"}]            
    provider_object = FakeProvider(fake)                
    tasking = ask(provider_object, "promt", Task)       
    answer, usage = await tasking                       
    assert usage  == Usage(input_tokens=10, output_tokens=5)



# 7. Only ValidationError is retried. Any other error goes straight up to the caller.
async def test_other_errors_are_not_retried():
    fake = []
    provider_object = FakeProvider(fake)
    tasking = ask(provider_object, "prompt", Task)
    with pytest.raises(RuntimeError):
        await tasking
    assert len(provider_object.prompts) == 1