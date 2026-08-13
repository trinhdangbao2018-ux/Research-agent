import hashlib
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, computed_field, model_validator


def fingerprint_of(text: str) -> str:
    normalised = " ".join(text.split())
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


class Task(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    question: str


class Source(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: str
    title: str
    retrieved_at: AwareDatetime
    fingerprint: str
    excerpt: str = ""

    @computed_field
    @property
    def id(self) -> str:
        return "s" + self.fingerprint[:16]


class Evidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    task_id: str
    statements: tuple[str, ...]
    sources: tuple[Source, ...]
    limitations: tuple[str, ...] = ()


class Result(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["final", "partial"]
    question: str
    report_md: str
    sources: tuple[Source, ...] = ()
    gaps: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _partial_must_state_gaps(self) -> "Result":
        if self.status == "partial" and not self.gaps:
            raise ValueError("status='partial' requires gaps: name what was left unanswered")
        return self
