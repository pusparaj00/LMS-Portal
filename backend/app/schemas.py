import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_PASSWORD_BYTES = 72  # bcrypt ignores or rejects anything longer


def _no_nul(value: str) -> str:
    if "\x00" in value:
        raise ValueError("must not contain a NUL character")
    return value


def _email(value: str) -> str:
    value = _no_nul(value).strip()
    if len(value) > 254 or not EMAIL_PATTERN.match(value):
        raise ValueError("must be an email address of at most 254 characters")
    return value


def _password(value: str) -> str:
    if len(_no_nul(value).encode()) > MAX_PASSWORD_BYTES:
        raise ValueError(f"must be at most {MAX_PASSWORD_BYTES} bytes")
    return value


Text = Annotated[str, AfterValidator(_no_nul)]  # Postgres text cannot hold NUL
Email = Annotated[str, AfterValidator(_email)]
Password = Annotated[str, Field(min_length=8), AfterValidator(_password)]


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
    email: Email = Field(examples=["student@example.com"])
    password: Password = Field(examples=["a-long-password"])


class LoginRequest(BaseModel):
    email: Text = Field(examples=["student@example.com"])
    password: Text = Field(examples=["a-long-password"])


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


class CourseConcept(BaseModel):
    concept_id: int
    name: str


class ConsentProvider(BaseModel):
    name: str
    order: str


class ConsentSection(BaseModel):
    heading: str
    paragraphs: list[str]


class ConsentNotice(BaseModel):
    version: str
    title: str
    sections: list[ConsentSection]
    providers: list[ConsentProvider]


class ConsentStatus(BaseModel):
    version: str
    accepted: bool
    accepted_at: datetime | None
    withdrawn_at: datetime | None


class ConsentAccept(BaseModel):
    version: Text = Field(max_length=40, description="the notice version the student was shown")


class ConceptCreate(BaseModel):
    name: Text = Field(min_length=2, max_length=60, examples=["string formatting"])


class CourseCreate(BaseModel):
    title: Text = Field(min_length=1, max_length=200)


class Problem(BaseModel):
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

    input: Text
    expected: Text
    hidden: bool
    category: Text


class ProblemCreate(BaseModel):
    course_id: int
    title: Text
    statement: Text
    difficulty_b: float
    discrimination_a: float
    concepts: list[ConceptTag]
    reference_solution: Text
    test_cases: list[TestCaseIn]


class SubmissionCreate(BaseModel):
    problem_id: int
    code: Text = Field(max_length=50_000, examples=["print(sum(map(int, input().split())))"])


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
    code: Text | None = Field(default=None, max_length=50_000)


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


class SourceOut(BaseModel):
    chunk_id: int
    title: str
    section: str
    text: str


RouteLabel = Literal["explain", "hint", "progress", "recommend", "lms", "general"]


class ChatRequest(BaseModel):
    message: Text = Field(min_length=1, max_length=2000, examples=["Why does my loop skip the last item?"])
    problem_id: int | None = Field(default=None, description="The problem the student has open, if any")
    route: RouteLabel | None = Field(default=None, description="Set when the student corrects the route")


class RouterInfo(BaseModel):
    how: Literal["llm", "keyword", "student"]
    confidence: float | None
    reason: str
    provider: str | None


class ChatResponse(BaseModel):
    message_id: int
    reply: str
    route: RouteLabel
    router: RouterInfo
    tools: list[str]
    sources: list[SourceOut]


class DocumentCreate(BaseModel):
    """Notes as text, or as a PDF sent as base64 (about 4 MB at most); exactly one of the two."""

    title: Text = Field(min_length=1, max_length=200)
    source_ref: Text | None = Field(default=None, max_length=200)
    concept: Text | None = None
    text: Text | None = Field(default=None, min_length=1, max_length=50_000)
    pdf_base64: str | None = Field(default=None, min_length=1, max_length=5_400_000)

    @model_validator(mode="after")
    def one_source(self):
        if (self.text is None) == (self.pdf_base64 is None):
            raise ValueError("send either text or pdf_base64, not both and not neither")
        return self


class DocumentOut(BaseModel):
    id: int
    title: str
    concept: str | None
    status: Literal["pending", "ready", "failed"]
    detail: str | None


class ExplanationOut(BaseModel):
    claim: str
    line: int
    concept: str | None
    hint_level: int
    sources: list[SourceOut]


class ProbeOut(BaseModel):
    problem_id: int
    kind: Literal["code", "mcq"]
    title: str
    statement: str
    options: list[OptionOut]


class ExplainResponse(BaseModel):
    status: Literal["verified", "fallback"]
    attempts: int
    cached: bool = False  # a stored (demo or failure-signature) explanation, verified again for this submission
    explanation: ExplanationOut | None
    fallback_text: str | None
    fallback_sources: list[SourceOut]
    probe: ProbeOut | None


class HintResponse(BaseModel):
    level: int
    max_level: int
    kind: Literal["concept", "location", "example"]
    text: str
    source_title: str | None = None
    example_title: str | None = None
    example_solution: str | None = None


class ProbeAnswerRequest(BaseModel):
    submission_id: int
    option_id: int | None = None
    code: Text | None = Field(default=None, max_length=50_000)


class ProbeResult(BaseModel):
    correct: bool
    mastery_changes: list[MasteryChange]


class ProblemPolicy(BaseModel):
    max_hint_level: int = Field(ge=1, le=3)


class StoredExplanation(BaseModel):
    """One failure-signature cache entry, for instructor review (F-62)."""

    signature: str
    problem_id: int
    problem_title: str
    claim: str
    line: int
    line_text: str | None
    concept: str
    test_category: str
    status: Literal["auto_verified", "instructor_approved", "rejected"]
    hit_count: int
    approved_by: int | None
    updated_at: datetime


class ExplanationDecision(BaseModel):
    decision: Literal["approve", "reject"]
    claim: Text | None = Field(default=None, min_length=1, max_length=400, description="an edited claim, approve only")


class ClassStudent(BaseModel):
    student_id: int
    label: str
    synthetic: bool
    mastery: list[ConceptMastery]


class ClassMastery(BaseModel):
    concepts: list[ConceptMastery]  # class average per concept
    students: list[ClassStudent]


class ClassMisconception(BaseModel):
    name: str
    description: str
    concept: str
    students: int  # students whose probability of holding it is above the suspicion threshold
    mean_probability: float
