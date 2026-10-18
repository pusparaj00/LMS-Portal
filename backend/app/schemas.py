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
    academic_history: Text | None = Field(default=None, max_length=1000, description="past academic history")
    interests: Text | None = Field(default=None, max_length=500, description="areas of interest")


class LoginRequest(BaseModel):
    email: Text = Field(examples=["student@example.com"])
    password: Text = Field(examples=["a-long-password"])


class LtiCode(BaseModel):
    code: Text = Field(max_length=100)


class LtiSession(BaseModel):
    access_token: str
    token_type: Literal["bearer"]
    role: Literal["student", "instructor"]
    course_id: int


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"]
    role: Literal["student", "instructor", "admin"]
    must_change_password: bool = False


Role = Literal["student", "instructor", "admin"]
DisplayName = Annotated[Text, Field(min_length=1, max_length=80)]


class Me(BaseModel):
    id: int
    email: str
    role: Role
    display_name: str | None
    academic_history: str | None
    interests: str | None
    must_change_password: bool
    opened_from_lms: bool


class ProfileUpdate(BaseModel):
    display_name: DisplayName | None = Field(description="shown to your teachers; never sent to the AI model")
    academic_history: Text | None = Field(default=None, max_length=1000, description="past academic history")
    interests: Text | None = Field(default=None, max_length=500, description="areas of interest")


class PasswordChange(BaseModel):
    current_password: Text = Field(max_length=200)
    new_password: Text = Field(min_length=8, max_length=72)


class AdminUser(BaseModel):
    id: int
    email: str
    role: Role
    display_name: str | None
    disabled: bool
    must_change_password: bool
    opened_from_lms: bool
    created_at: datetime


class StaffCreate(BaseModel):
    email: Text = Field(max_length=254)
    role: Literal["instructor", "admin"]
    display_name: DisplayName | None = None


class RoleChange(BaseModel):
    role: Role


class TemporaryPassword(BaseModel):
    user: AdminUser
    temporary_password: str = Field(description="shown once; the user must replace it at their next login")




class ConceptTag(BaseModel):
    concept_id: int
    name: str
    weight: float


class Course(BaseModel):
    id: int
    title: str
    instructor_id: int
    enrolled: bool
    archived: bool = False


class CourseRename(BaseModel):
    title: Text = Field(min_length=1, max_length=200)


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


class ErasureStatus(BaseModel):
    confirm_with: Literal["password", "lms"] = Field(
        description="how a request is confirmed: the password, or (for an account opened from an LMS) a confirmation"
    )
    pending: bool
    kind: Literal["requested", "retention"] | None
    notified_at: datetime | None
    due_at: datetime | None


class ErasureRequest(BaseModel):
    password: Text | None = Field(default=None, max_length=200, description="the student's password, to confirm")
    confirm: bool = Field(default=False, description="for an account opened from an LMS, which has no password")


class ConsentAccept(BaseModel):
    version: Text = Field(max_length=40, description="the notice version the student was shown")
    adult: bool = Field(False, description="the student confirms they are 18 or older (TR-S-10)")


class AssignmentProblemIn(BaseModel):
    problem_id: int
    points: float = Field(default=1.0, gt=0, le=100)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("give the due time with its time zone, for example 2026-11-01T23:59:00+05:30")
    return value


class AssignmentIn(BaseModel):
    title: Text = Field(min_length=1, max_length=200)
    due_at: Annotated[datetime, AfterValidator(_aware)]
    problems: list[AssignmentProblemIn] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def _distinct(self):
        if len({p.problem_id for p in self.problems}) != len(self.problems):
            raise ValueError("each problem can be in an assignment only once")
        return self


class AssignmentProblemOut(BaseModel):
    problem_id: int
    title: str
    points: float


Status = Literal["complete", "in_progress", "late", "missing", "not_started"]


class MyScore(BaseModel):
    score: float
    with_late: float
    possible: float
    status: Status


class AssignmentOut(BaseModel):
    id: int
    course_id: int
    title: str
    due_at: datetime
    possible: float
    problems: list[AssignmentProblemOut]
    mine: MyScore | None = Field(default=None, description="the signed-in student's own score; absent for staff")


class GradebookAssignment(BaseModel):
    id: int
    title: str
    due_at: datetime
    possible: float


class GradebookCell(BaseModel):
    assignment_id: int
    score: float
    with_late: float
    status: Status


class GradebookRow(BaseModel):
    student_id: int
    label: str
    synthetic: bool
    cells: list[GradebookCell]
    total: float
    total_with_late: float


class Gradebook(BaseModel):
    assignments: list[GradebookAssignment]
    students: list[GradebookRow]
    possible: float
    lms_grades: Literal["none", "not_allowed", "ready"] = Field(
        default="none", description="whether grades can be sent to the LMS the course was opened from"
    )


class GradeSendFailure(BaseModel):
    assignment_id: int
    student_id: int | None
    error: str


class GradeSendResult(BaseModel):
    assignments: int
    scores_sent: int
    students_not_from_lms: int
    failures: list[GradeSendFailure]


class AnnouncementIn(BaseModel):
    title: Text = Field(min_length=1, max_length=200)
    body: Text = Field(min_length=1, max_length=5000, description="plain text; line breaks are kept")

    @model_validator(mode="after")
    def _not_blank(self):
        if not self.title.strip() or not self.body.strip():
            raise ValueError("an announcement needs a title and some text")
        return self


class Announcement(BaseModel):
    id: int
    course_id: int
    title: str
    body: str
    created_at: datetime
    edited_at: datetime | None


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
    archived: bool = False
    param_source: Literal["prior", "estimated"] = "prior"
    # Only filled for the student who asks, from their own submissions (F-60).
    my_status: Literal["solved", "tried", "new"] | None = None

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
    difficulty_b: float | None = Field(
        ge=-2, le=2, description="empty: estimated from the text and concepts (F-23), and marked as estimated",
    )
    discrimination_a: float
    concepts: list[ConceptTag]
    reference_solution: Text
    test_cases: list[TestCaseIn]


class ProblemDraftRequest(BaseModel):
    course_id: int
    concept_id: int


class ProblemDraftOut(BaseModel):
    """A checked draft for the instructor to review and save through POST /problems (TR-L-10). Not saved yet."""

    title: str
    statement: str
    reference_solution: str
    test_cases: list[TestCaseIn]
    concept_id: int
    wrong_category: str
    checks: list[str]
    attempts: int


class ProblemSource(ProblemCreate):
    """Everything an instructor needs to edit a coding problem, hidden tests and reference solution included."""

    param_source: Literal["prior", "estimated"]


class SubmissionCreate(BaseModel):
    problem_id: int
    code: Text = Field(max_length=50_000, examples=["print(sum(map(int, input().split())))"])


class CustomRun(BaseModel):
    problem_id: int
    code: Text = Field(max_length=50_000)
    stdin: Text = Field(default="", max_length=10_000)


class CustomRunResult(BaseModel):
    status: str
    stdout: str
    stderr: str
    runtime_ms: int


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


class VisibleTestResult(BaseModel):
    input: str
    expected: str
    passed: bool


class ExplanationRecord(BaseModel):
    requested: bool
    attempts: int
    outcome: Literal["verified", "template"] | None = Field(description="verified by the checks, or a fallback")
    from_cache: bool = Field(description="served from the stored-explanation cache instead of a model call")
    text: str | None = Field(description="what the student was shown, while it is still cached (24 hours)")


class StudentSubmission(BaseModel):
    submission_id: int
    problem_id: int
    problem_title: str
    created_at: datetime
    status: str
    passed: int
    failed: int


class StudentWork(BaseModel):
    student_id: int
    label: str
    synthetic: bool
    concepts: list[ConceptMastery]
    misconceptions: list[SuspectedMisconception]
    submissions: list[StudentSubmission]


class SubmissionDetail(StudentSubmission):
    code: str
    error_type: str | None
    failed_categories: list[str]
    visible_tests: list[VisibleTestResult] | None = Field(
        description="per-test results for the examples; absent when the tests were changed after this submission"
    )
    hidden_failed: int | None = Field(description="how many hidden tests failed; their inputs are never shown")
    explanation: ExplanationRecord


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
    example_input: str | None = None  # an input on which the program was shown to go wrong (TR-L-05)
    example_output: str | None = None  # what the student's own program printed for it, never the reference's output


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
    leak_threshold: float | None = Field(
        default=None, ge=0.3, le=0.7,
        description="stricter leak guard for this problem: 0.5 strict, 0.3 very strict; empty uses the tuned 0.7",
    )


class ProblemPolicyOut(ProblemPolicy):
    effective_leak_threshold: float


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


class CourseProgress(BaseModel):
    course_id: int
    title: str
    assignments: int
    completed: int
    score: float
    possible: float
    percent: float | None
    next_due_at: datetime | None


class UpcomingAssignment(BaseModel):
    assignment_id: int
    course_id: int
    course_title: str
    title: str
    due_at: datetime
    status: str | None = None
    students_complete: int | None = None
    students: int | None = None


class StudentStats(BaseModel):
    enrolled_courses: int
    average_percent: float | None
    assignments_complete: int
    assignments_total: int
    courses: list[CourseProgress]
    upcoming: list[UpcomingAssignment]


class GradeLine(BaseModel):
    assignment_id: int
    title: str
    due_at: datetime
    score: float
    with_late: float
    possible: float
    status: str


class CourseGrades(BaseModel):
    course_id: int
    title: str
    score: float
    possible: float
    percent: float | None
    assignments: list[GradeLine]


class InstructorCourseStats(BaseModel):
    course_id: int
    title: str
    students: int
    assignments: int
    submissions_7d: int
    completion_rate: float | None
    rating_count: int
    average_course_rating: float | None


class InstructorStats(BaseModel):
    courses: int
    students: int
    upcoming_assignments: int
    submissions_7d: int
    course_stats: list[InstructorCourseStats]
    upcoming: list[UpcomingAssignment]


class ScoreBucket(BaseModel):
    label: str
    students: int


class AssignmentProgress(BaseModel):
    assignment_id: int
    title: str
    due_at: datetime
    complete: int
    in_progress: int
    late: int
    missing: int
    not_started: int


class RatingSummary(BaseModel):
    count: int
    average_course: float | None
    average_instructor: float | None


class CourseAnalytics(BaseModel):
    course_id: int
    title: str
    students: int
    assignments: int
    submissions_total: int
    submissions_7d: int
    completion_rate: float | None
    average_percent: float | None
    distribution: list[ScoreBucket]
    per_assignment: list[AssignmentProgress]
    ratings: RatingSummary


class RatingIn(BaseModel):
    course_rating: int = Field(ge=1, le=5)
    instructor_rating: int = Field(ge=1, le=5)
    review: Text | None = Field(default=None, max_length=1000)


class RatingOut(BaseModel):
    course_rating: int
    instructor_rating: int
    review: str | None
    created_at: datetime


class CourseRatings(BaseModel):
    summary: RatingSummary
    mine: RatingOut | None
    reviews: list[RatingOut]
