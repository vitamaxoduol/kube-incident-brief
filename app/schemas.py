from typing import Annotated, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationInfo,
    model_validator,
)


EvidenceText = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=2000)
]
BriefText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
EvidenceIDs = Annotated[list[Annotated[int, Field(strict=True, ge=1)]], Field(min_length=1)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class AnalyzeRequest(StrictModel):
    evidence: Annotated[list[EvidenceText], Field(min_length=1, max_length=30)]


class Observation(StrictModel):
    finding: BriefText
    evidence_ids: EvidenceIDs


class PossibleCause(StrictModel):
    hypothesis: BriefText
    evidence_ids: EvidenceIDs


class IncidentBrief(StrictModel):
    observations: list[Observation]
    possible_causes: list[PossibleCause]
    next_checks: list[BriefText]

    @model_validator(mode="after")
    def check_evidence_ids(self, info: ValidationInfo) -> Self:
        # The endpoint validates with the submitted evidence count. FastAPI
        # may also validate the response without request context.
        if info.context is not None:
            evidence_count = info.context["evidence_count"]
            for statement in [*self.observations, *self.possible_causes]:
                if any(evidence_id > evidence_count for evidence_id in statement.evidence_ids):
                    raise ValueError("Citation refers to evidence outside this request")
        return self
