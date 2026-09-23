import pytest
from pydantic import ValidationError

from research_agent.models import Task
from research_agent.providers.base import Usage
from research_agent.providers.fake import FakeProvider


# 1. Answers come out in the order the test scripted them.
async def test_returns_answers_in_order():
    fake = FakeProvider([
        {"id": "t1", "question": "first?"},
        {"id": "t2", "question": "second?"},
    ])

    first, _ = await fake.ask("prompt 1", Task)
    second, _ = await fake.ask("prompt 2", Task)

    assert first == Task(id="t1", question="first?")
    assert second == Task(id="t2", question="second?")


# 2. Every prompt is recorded, in order. Later tests read this to check what was sent.
async def test_records_every_prompt():
    fake = FakeProvider([
        {"id": "t1", "question": "Q?"},
        {"id": "t2", "question": "Q?"},
    ])

    await fake.ask("prompt 1", Task)
    await fake.ask("prompt 2", Task)

    assert fake.prompts == ["prompt 1", "prompt 2"]


# 3. Every answer comes with a Usage, for engine/budget.py.
async def test_returns_usage():
    fake = FakeProvider([{"id": "t1", "question": "Q?"}])

    _, usage = await fake.ask("prompt", Task)

    assert usage == Usage(input_tokens=10, output_tokens=5)


# 4. A bad answer raises ValidationError and is used up, so a retry gets the next one.
async def test_bad_answer_is_used_up():
    fake = FakeProvider([
        {"id": "t1"},                    # missing "question" -> invalid
        {"id": "t1", "question": "Q?"},  # valid
    ])

    with pytest.raises(ValidationError):
        await fake.ask("first try", Task)

    answer, _ = await fake.ask("retry", Task)
    assert answer == Task(id="t1", question="Q?")


# 5. Running out of answers fails loudly instead of returning something made up.
async def test_running_out_raises_clear_error():
    fake = FakeProvider([])

    with pytest.raises(RuntimeError, match="ran out of scripted responses"):
        await fake.ask("prompt", Task)


# 6. The fake works on its own copy: the test's list is never emptied.
async def test_does_not_change_the_callers_list():
    script = [{"id": "t1", "question": "Q?"}]
    fake = FakeProvider(script)

    await fake.ask("prompt", Task)

    assert script == [{"id": "t1", "question": "Q?"}]