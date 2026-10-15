from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Mockable(BaseModel):
    """Mock endpoints return the first OpenAPI example, so contract and mock cannot drift."""

    @classmethod
    def mock(cls):
        return cls.model_validate(cls.model_config["json_schema_extra"]["examples"][0])


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorBody


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "down"]
    redis: Literal["ok", "down"]


class RegisterRequest(BaseModel):
    email: str = Field(examples=["student@example.com"])
    password: str = Field(min_length=8, examples=["a-long-password"])


class LoginRequest(BaseModel):
    email: str = Field(examples=["student@example.com"])
    password: str = Field(examples=["a-long-password"])


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"]
    role: Literal["student", "instructor", "admin"]




class ConceptTag(BaseModel):
    concept_id: int
    name: str
    weight: float


class Course(BaseModel):
    id: int
    title: str
    instructor_id: int
    enrolled: bool


class CourseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class Problem(Mockable):
    id: int
    course_id: int
    title: str
    statement: str
    language: str
    kind: Literal["code", "mcq"]
    difficulty_b: float
    discrimination_a: float
    review_status: Literal["needs human review", "reviewed"]
    concepts: list[ConceptTag]

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": 1,
                    "course_id": 1,
                    "title": "Sum of a list",
                    "statement": "Read n, then n numbers. Print their sum.",
                    "language": "python",
                    "kind": "code",
                    "difficulty_b": -0.5,
                    "discrimination_a": 1.0,
                    "review_status": "needs human review",
                    "concepts": [{"concept_id": 1, "name": "loops", "weight": 1.0}],
                }
            ]
        }
    )


class ProblemList(BaseModel):
    problems: list[Problem]


class Example(BaseModel):
    input: str
    expected: str


class ProblemDetail(Problem):
    examples: list[Example]


class TestCaseIn(BaseModel):
    __test__ = False

    input: str
    expected: str
    hidden: bool
    category: str


class ProblemCreate(BaseModel):
    course_id: int
    title: str
    statement: str
    difficulty_b: float
    discrimination_a: float
    concepts: list[ConceptTag]
    reference_solution: str
    test_cases: list[TestCaseIn]


class SubmissionCreate(BaseModel):
    problem_id: int
    code: str = Field(max_length=50_000, examples=["print(sum(map(int, input().split())))"])


class MasteryChange(BaseModel):
    concept: str
    before: float
    after: float


class VisibleTest(BaseModel):
    input: str
    expected: str
    actual: str
    passed: bool
    status: str


class SubmissionResult(BaseModel):
    submission_id: int | None
    problem_id: int
    status: Literal["passed", "failed", "error"]
    passed: int
    failed: int
    error_type: str | None
    failed_categories: list[str]
    runtime_ms: int
    visible_tests: list[VisibleTest]
    mastery_changes: list[MasteryChange]


class OptionOut(BaseModel):
    id: int
    text: str


class DiagnosticItem(BaseModel):
    problem_id: int
    kind: Literal["code", "mcq"]
    title: str
    statement: str
    options: list[OptionOut]


class DiagnosticStartRequest(BaseModel):
    course_id: int


class ConceptMastery(BaseModel):
    concept_id: int
    name: str
    p_known: float


class SuspectedMisconception(BaseModel):
    name: str
    description: str
    probability: float


class DiagnosticResult(BaseModel):
    mastery: list[ConceptMastery]
    misconceptions: list[SuspectedMisconception]
    ability: float


class DiagnosticStartResponse(BaseModel):
    session_id: str
    item_number: int
    max_items: int
    item: DiagnosticItem


class DiagnosticAnswerRequest(BaseModel):
    session_id: str
    problem_id: int
    option_id: int | None = None
    code: str | None = Field(default=None, max_length=50_000)


class DiagnosticAnswerResponse(BaseModel):
    session_id: str
    done: bool
    item_number: int
    next_item: DiagnosticItem | None
    result: DiagnosticResult | None


class LedgerEntry(BaseModel):
    created_at: str
    concept: str
    p_before: float
    p_after: float
    evidence_type: str
    rule_id: str
    explanation: str
    submission_id: int | None


class RecentSubmission(BaseModel):
    submission_id: int
    problem_id: int
    problem_title: str
    status: str
    passed: int
    failed: int
    created_at: str


class RecommendedProblem(BaseModel):
    problem_id: int
    title: str
    reason: str


class Dashboard(BaseModel):
    concepts: list[ConceptMastery]
    misconceptions: list[SuspectedMisconception]
    recent_submissions: list[RecentSubmission]
    recommended: RecommendedProblem | None
    placement_completed: bool


class ChatRequest(BaseModel):
    message: str = Field(max_length=2000, examples=["Why does my loop skip the last item?"])


class ChatResponse(Mockable):
    reply: str
    route: Literal["explain", "hint", "progress", "recommend", "lms", "general"]
    sources: list[str]

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "reply": "This is a canned reply from the stub LLM adapter.",
                    "route": "explain",
                    "sources": [],
                }
            ]
        }
    )
