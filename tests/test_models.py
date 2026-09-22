from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from research_agent.models import Evidence, Result, Source, Task, fingerprint_of


def make_source(text: str = "some text") -> Source:
    """A valid Source, so each test starts from a known-good object."""
    return Source(
        url="https://example.eu/page",
        title="Page",
        retrieved_at=datetime.now(timezone.utc),
        fingerprint=fingerprint_of(text),
    )


# 1. Two mirrors of one page must deduplicate: whitespace must not change the hash.
def test_fingerprint_ignores_whitespace():
    assert fingerprint_of("a b c") == fingerprint_of("a   b\n\tc ")
    assert fingerprint_of("a b c") != fingerprint_of("a b d")


# 2. The [s<id>] marker comes from the content, not from anything stored separately.
def test_source_id_is_derived():
    source = make_source("a b c")
    assert source.id.startswith("s")
    assert len(source.id) == 17
    assert source.id == "s" + source.fingerprint[:16]

    same_words = make_source("a \n b \n c")
    assert source.fingerprint == same_words.fingerprint
    assert source.id == same_words.id


# 3. Saving to sources.json and loading it back must lose nothing.
#    Source object --model_dump()--> dict --model_validate()--> Source object
def test_source_round_trip():
    source = make_source("a b c")
    data = source.model_dump()  # serialise, as if writing to sources.json
    loaded = Source.model_validate(data)  # rebuild, as if reading it back

    assert loaded == source
    assert loaded.retrieved_at.tzinfo is not None  # the timezone must survive
    assert "id" in data  # the computed field must be included in the dump


# 4. Every timestamp carries a timezone
def test_naive_datetime_rejected():
    with pytest.raises(ValidationError):
        Source(
            url="https://example.eu/page",
            title="Page",
            retrieved_at=datetime.now(),  # no tzinfo -> naive -> must be rejected
            fingerprint=fingerprint_of("a b c"),
        )


# 5. Mechanism 4: a partial result cannot hide what is missing
def test_partial_requires_gaps():
    with pytest.raises(ValidationError):
        Result(status="partial", question="", report_md="")  # partial, no gaps

    Result(  # partial, with a gap named -> ok
        status="partial", question="", report_md="",
        gaps=("penalties for non-compliance not covered",),
    )
    Result(status="final", question="", report_md="")  # final, no gaps -> ok


# 6. Nothing can change a Source after it is minted
def test_models_are_frozen():
    source = make_source("a b c")
    with pytest.raises(ValidationError):
        source.url = "x"


# Optional extras: the same patterns above, applied to the other models

# A worker that hit no problems should not have to state that explicitly
def test_evidence_limitations_defaults_empty():
    evidence = Evidence(task_id="t1", statements=(), sources=())
    assert evidence.limitations == ()


# status is restricted to the two Literal values; nothing else is accepted
def test_result_status_rejects_unknown_value():
    with pytest.raises(ValidationError):
        Result(status="done", question="", report_md="")


# Immutability applies to every model, not only Source
def test_task_and_evidence_are_frozen():
    task = Task(id="t1", question="q")
    with pytest.raises(ValidationError):
        task.question = "x"

    evidence = Evidence(task_id="t1", statements=(), sources=())
    with pytest.raises(ValidationError):
        evidence.task_id = "x"