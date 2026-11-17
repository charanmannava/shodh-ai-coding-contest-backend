from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ContestCreate(BaseModel):
    organization_id: str
    name: str = Field(min_length=1, max_length=200)
    start_time: datetime
    end_time: datetime
    problem_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_time_range(self) -> "ContestCreate":
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class ContestResponse(BaseModel):
    id: str
    organization_id: str
    name: str
    start_time: datetime
    end_time: datetime
    model_config = ConfigDict(from_attributes=True)


class TestCaseCreate(BaseModel):
    input: str
    expected_output: str
    is_sample: bool = False


class ProblemCreate(BaseModel):
    organization_id: str
    title: str = Field(min_length=1, max_length=250)
    statement: str = Field(min_length=1)
    test_cases: list[TestCaseCreate] = Field(min_length=1)


class ProblemResponse(BaseModel):
    id: str
    title: str
    version: int
    statement: str
    samples: list[dict[str, str]]


class SubmissionCreate(BaseModel):
    contest_id: str
    problem_id: str
    code: str = Field(min_length=1, max_length=100_000)


class SubmissionAccepted(BaseModel):
    submission_id: str
    status: str
    message: str


class SubmissionResponse(BaseModel):
    submission_id: str
    status: str
    verdict: str | None = None
    score: int | None = None
    message: str | None = None
    attempts: list[dict[str, object]] | None = None


class LeaderboardEntry(BaseModel):
    rank: int
    user_id: str
    score: int
    last_accepted_at: datetime | None
