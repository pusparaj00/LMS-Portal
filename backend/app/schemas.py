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
    section: str | None = None
    subject: str | None = None
    color: str | None = None


COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")


class CourseUpdate(BaseModel):
    """Only the fields sent change; null clears a section, subject or colour."""

    title: Text | None = Field(default=None, min_length=1, max_length=200)
    section: Text | None = Field(default=None, max_length=100)
    subject: Text | None = Field(default=None, max_length=100)
    color: str | None = None

    @model_validator(mode="after")
    def _checked(self):
        if not self.model_fields_set:
            raise ValueError("send a title, section, subject or color")
        if "title" in self.model_fields_set and (self.title is None or not self.title.strip()):
            raise ValueError("a course needs a title")
        for name in ("section", "subject"):
            value = getattr(self, name)
            if value is not None and not value.strip():
                setattr(self, name, None)
        if self.color is not None:
            if not COLOR_PATTERN.match(self.color):
                raise ValueError("a color looks like #1a2b3c")
            self.color = self.color.lower()
        return self


class JoinIn(BaseModel):
    code: str = Field(min_length=1, max_length=40)


class JoinCode(BaseModel):
    code: str
    enabled: bool
    link: str


class JoinCodeEnabled(BaseModel):
    enabled: bool


class Person(BaseModel):
    user_id: int
    label: str


class Teacher(Person):
    owner: bool


class Classmate(Person):
    muted: bool
    joined_at: datetime


class People(BaseModel):
    """Staff get every student; a student gets the teachers and only the number of classmates."""

    teachers: list[Teacher]
    student_count: int
    students: list[Classmate] | None = None
    can_manage_teachers: bool = False


class CoTeacherIn(BaseModel):
    email: Text = Field(min_length=3, max_length=254)


class MuteIn(BaseModel):
    muted: bool


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


class AssignmentQuizIn(BaseModel):
    quiz_id: int
    points: float = Field(default=1.0, gt=0, le=100)


class WorkIn(BaseModel):
    """Handed-in work an assignment asks for: what to do, how many points, and which kinds of hand-in it accepts."""

    instructions: Text = Field(min_length=1, max_length=5000)
    points: float = Field(gt=0, le=100)
    allow_file: bool = True
    allow_link: bool = True
    allow_text: bool = True
    rubric_id: int | None = Field(
        default=None, description="a rubric of this course; its top score must equal the points"
    )

    @model_validator(mode="after")
    def _something_allowed(self):
        if not self.instructions.strip():
            raise ValueError("the work needs instructions")
        if not (self.allow_file or self.allow_link or self.allow_text):
            raise ValueError("allow at least one of file, link or text")
        return self


class AssignmentIn(BaseModel):
    title: Text = Field(min_length=1, max_length=200)
    due_at: Annotated[datetime, AfterValidator(_aware)]
    problems: list[AssignmentProblemIn] = Field(default_factory=list, max_length=50)
    quizzes: list[AssignmentQuizIn] = Field(default_factory=list, max_length=50)
    work: WorkIn | None = None
    module_id: int | None = Field(default=None, description="the topic (course module) it is filed under")
    category_id: int | None = Field(default=None, description="the grade category it counts in")
    students: list[int] | None = Field(
        default=None, max_length=2000, description="the students it is given to; null or empty means the whole class"
    )

    @model_validator(mode="after")
    def _distinct(self):
        if not self.problems and not self.quizzes and self.work is None:
            raise ValueError("an assignment needs at least one problem, quiz or piece of work")
        if len({p.problem_id for p in self.problems}) != len(self.problems):
            raise ValueError("each problem can be in an assignment only once")
        if len({q.quiz_id for q in self.quizzes}) != len(self.quizzes):
            raise ValueError("each quiz can be in an assignment only once")
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


class AssignmentQuizOut(BaseModel):
    quiz_id: int
    title: str
    points: float
    published: bool = True


class AssignmentOut(BaseModel):
    id: int
    course_id: int
    title: str
    due_at: datetime
    possible: float
    problems: list[AssignmentProblemOut]
    quizzes: list[AssignmentQuizOut] = Field(default_factory=list)
    work: WorkIn | None = None
    module_id: int | None = None
    category_id: int | None = None
    students: list[int] | None = Field(default=None, description="staff only: null means the whole class")
    mine: MyScore | None = Field(default=None, description="the signed-in student's own score; absent for staff")


class GradebookAssignment(BaseModel):
    id: int
    title: str
    due_at: datetime
    possible: float


class OverallPart(BaseModel):
    category_id: int
    name: str
    weight: float
    score: float
    possible: float
    percent: float


class Overall(BaseModel):
    """The weighted grade. `percent` is null when nothing in a category was given yet. `uncategorised` counts the
    assignments that have no category and so are not part of it."""

    percent: float | None
    parts: list[OverallPart]
    uncategorised: int



class GradebookCell(BaseModel):
    assignment_id: int
    score: float
    with_late: float
    status: Status
    override_reason: str | None = Field(default=None, description="set when the instructor adjusted this score")


class GradebookRow(BaseModel):
    student_id: int
    label: str
    synthetic: bool
    cells: list[GradebookCell]
    total: float
    total_with_late: float
    possible: float = Field(default=0, description="the points of the assignments given to this student")
    overall: Overall | None = None


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
    """`mode` is publish (now), draft (teachers only) or schedule (visible at `publish_at`, which must be ahead)."""

    title: Text = Field(min_length=1, max_length=200)
    body: Text = Field(min_length=1, max_length=5000, description="plain text; line breaks are kept")
    mode: Literal["publish", "draft", "schedule"] = "publish"
    publish_at: Annotated[datetime, AfterValidator(_aware)] | None = None

    @model_validator(mode="after")
    def _not_blank(self):
        if not self.title.strip() or not self.body.strip():
            raise ValueError("an announcement needs a title and some text")
        if self.mode == "schedule":
            if self.publish_at is None or self.publish_at <= datetime.now(self.publish_at.tzinfo):
                raise ValueError("a scheduled announcement needs a publish time in the future")
        elif self.publish_at is not None:
            raise ValueError("send a publish time only when scheduling")
        return self


class Announcement(BaseModel):
    id: int
    course_id: int
    title: str
    body: str
    created_at: datetime
    edited_at: datetime | None
    state: Literal["published", "draft", "scheduled"] = "published"
    publish_at: datetime | None = None


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
    content_done: int
    content_total: int


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
    override_reason: str | None = Field(default=None, description="set when the instructor adjusted this score")


class CourseGrades(BaseModel):
    course_id: int
    title: str
    score: float
    possible: float
    percent: float | None
    assignments: list[GradeLine]
    overall: Overall | None = None


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


ItemKind = Literal["text", "link", "video", "file"]
LINK_PATTERN = re.compile(r"^https?://[^\s]+$")
MAX_PDF_BASE64 = 6_000_000  # about 4.5 MB of file; the proxy's own limit is 6 MiB for the whole request


def _link(value: str | None) -> str | None:
    if value is not None and not LINK_PATTERN.match(value.strip()):
        raise ValueError("a link must start with http:// or https:// and contain no spaces")
    return value.strip() if value else value


class ModuleIn(BaseModel):
    title: Text = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def _not_blank(self):
        if not self.title.strip():
            raise ValueError("a module needs a title")
        return self


class ModuleUpdate(BaseModel):
    title: Text | None = Field(default=None, min_length=1, max_length=200)
    published: bool | None = None

    @model_validator(mode="after")
    def _something_to_change(self):
        if self.title is None and self.published is None:
            raise ValueError("send a title or published")
        if self.title is not None and not self.title.strip():
            raise ValueError("a module needs a title")
        return self


class ItemIn(BaseModel):
    """A text item has `body`; a link or video item has `url`; a file item has `pdf_base64` and `file_name`."""

    kind: ItemKind
    title: Text = Field(min_length=1, max_length=200)
    body: Text | None = Field(default=None, min_length=1, max_length=20_000, description="plain text, shown as typed")
    url: Text | None = Field(default=None, max_length=2000)
    pdf_base64: str | None = Field(default=None, min_length=1, max_length=MAX_PDF_BASE64)
    file_name: Text | None = Field(default=None, min_length=1, max_length=200)
    published: bool = True

    @model_validator(mode="after")
    def _fields_match_the_kind(self):
        if not self.title.strip():
            raise ValueError("an item needs a title")
        given = {
            "body": self.body is not None, "url": self.url is not None,
            "pdf_base64": self.pdf_base64 is not None, "file_name": self.file_name is not None,
        }
        wanted = {
            "text": {"body"}, "link": {"url"}, "video": {"url"}, "file": {"pdf_base64", "file_name"},
        }[self.kind]
        if {name for name, present in given.items() if present} != wanted:
            raise ValueError(f"a {self.kind} item takes exactly: {', '.join(sorted(wanted))}")
        if self.body is not None and not self.body.strip():
            raise ValueError("the text must not be blank")
        self.url = _link(self.url)
        return self


class ItemUpdate(BaseModel):
    title: Text | None = Field(default=None, min_length=1, max_length=200)
    body: Text | None = Field(default=None, min_length=1, max_length=20_000)
    url: Text | None = Field(default=None, max_length=2000)
    published: bool | None = None

    @model_validator(mode="after")
    def _something_to_change(self):
        if all(v is None for v in (self.title, self.body, self.url, self.published)):
            raise ValueError("send something to change")
        if (self.title is not None and not self.title.strip()) or (self.body is not None and not self.body.strip()):
            raise ValueError("the title and text must not be blank")
        self.url = _link(self.url)
        return self


class Move(BaseModel):
    direction: Literal["up", "down"]


class ItemOut(BaseModel):
    id: int
    kind: ItemKind
    title: str
    body: str | None
    url: str | None
    file_name: str | None
    file_size: int | None
    published: bool
    completed: bool | None = None  # only for a student: whether they have marked it done


class ModuleOut(BaseModel):
    id: int
    title: str
    published: bool
    items: list[ItemOut]
    total: int
    completed: int | None = None  # a student's own count
    completion_rate: float | None = None  # staff: share of the class's possible completions


class ContentOut(BaseModel):
    modules: list[ModuleOut]
    total: int
    completed: int | None = None


QuestionKind = Literal["single", "multiple", "short"]
MAX_OPTIONS = 8


class QuestionIn(BaseModel):
    """A choice question has `options` and the indices of the right ones; a short-answer question has `accepted`."""

    kind: QuestionKind
    prompt: Text = Field(min_length=1, max_length=2000)
    options: list[Annotated[Text, Field(min_length=1, max_length=300)]] = Field(
        default_factory=list, max_length=MAX_OPTIONS
    )
    correct_choices: list[int] = Field(default_factory=list, max_length=MAX_OPTIONS)
    accepted: list[Annotated[Text, Field(min_length=1, max_length=200)]] = Field(default_factory=list, max_length=10)
    weight: float = Field(default=1.0, gt=0, le=100)

    @model_validator(mode="after")
    def _fields_match_the_kind(self):
        if not self.prompt.strip():
            raise ValueError("a question needs a prompt")
        if self.kind == "short":
            if self.options or self.correct_choices:
                raise ValueError("a short-answer question takes accepted answers, not options")
            if not [a for a in self.accepted if a.strip()]:
                raise ValueError("a short-answer question needs at least one accepted answer")
            return self
        if self.accepted:
            raise ValueError("a choice question takes options, not accepted answers")
        if not 2 <= len(self.options) <= MAX_OPTIONS:
            raise ValueError(f"a choice question needs 2 to {MAX_OPTIONS} options")
        if len(set(self.options)) != len(self.options):
            raise ValueError("the options must differ from each other")
        if len(set(self.correct_choices)) != len(self.correct_choices) or not self.correct_choices:
            raise ValueError("give each right option once, and at least one")
        if any(not 0 <= i < len(self.options) for i in self.correct_choices):
            raise ValueError("a right option is not one of the options")
        if self.kind == "single" and len(self.correct_choices) != 1:
            raise ValueError("a single-choice question has exactly one right option")
        return self


class QuizIn(BaseModel):
    title: Text = Field(min_length=1, max_length=200)
    max_attempts: int = Field(default=3, ge=1, le=10)
    show_answers: bool = False
    published: bool = False
    questions: list[QuestionIn] = Field(min_length=1, max_length=50)


class QuestionOut(BaseModel):
    """`correct_choices` and `accepted` are only ever filled for staff."""

    id: int
    kind: QuestionKind
    prompt: str
    options: list[str]
    weight: float
    correct_choices: list[int] | None = None
    accepted: list[str] | None = None


class QuizSummary(BaseModel):
    id: int
    title: str
    max_attempts: int
    show_answers: bool
    published: bool
    questions: int
    in_assignments: int
    attempts_used: int | None = Field(default=None, description="the signed-in student's own attempts")
    best_fraction: float | None = None


class QuizOut(QuizSummary):
    question_list: list[QuestionOut]


class AnswerIn(BaseModel):
    question_id: int
    choices: list[int] = Field(default_factory=list, max_length=MAX_OPTIONS)
    text: Text | None = Field(default=None, max_length=500)


class AttemptIn(BaseModel):
    answers: list[AnswerIn] = Field(max_length=50)


class ReviewItem(BaseModel):
    question_id: int
    correct: bool
    correct_choices: list[int] | None = None
    accepted: list[str] | None = None


class AttemptOut(BaseModel):
    attempt_id: int
    attempt_number: int
    attempts_left: int
    earned: float
    possible: float
    fraction: float
    review: list[ReviewItem] | None = Field(
        default=None, description="only when the instructor allows review and it is open"
    )


class AttemptRow(BaseModel):
    id: int
    number: int
    fraction: float
    submitted_at: datetime


class MyAttempts(BaseModel):
    attempts: list[AttemptRow]
    attempts_left: int
    review: list[ReviewItem] | None = None


WorkState = Literal["assigned", "missing", "turned_in", "graded", "returned"]


class WorkDraftIn(BaseModel):
    """A student's draft. Text and link replace what was saved (null clears them); a file replaces the saved one only
    when `file_base64` is sent, and `remove_file` clears it."""

    text: Text | None = Field(default=None, min_length=1, max_length=20_000)
    link: Text | None = Field(default=None, max_length=2000)
    file_base64: str | None = Field(default=None, min_length=1, max_length=MAX_PDF_BASE64)
    file_name: Text | None = Field(default=None, min_length=1, max_length=200)
    remove_file: bool = False

    @model_validator(mode="after")
    def _checked(self):
        if (self.file_base64 is None) != (self.file_name is None):
            raise ValueError("send a file with its name")
        if self.file_base64 is not None and self.remove_file:
            raise ValueError("send a new file or remove the file, not both")
        if self.text is not None and not self.text.strip():
            raise ValueError("the text must not be blank")
        self.link = _link(self.link)
        return self


class RubricLevelOut(BaseModel):
    id: int
    label: str
    points: float


class RubricCriterionOut(BaseModel):
    id: int
    title: str
    description: str | None
    levels: list[RubricLevelOut]
    chosen_level_id: int | None = None


class RubricOut(BaseModel):
    id: int
    title: str
    max_points: float
    criteria: list[RubricCriterionOut]
    used_by: int = Field(default=0, description="assignments that use it")



class CommentIn(BaseModel):
    body: Text = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def _not_blank(self):
        if not self.body.strip():
            raise ValueError("write a comment")
        return self


class CommentOut(BaseModel):
    id: int
    from_teacher: bool
    mine: bool
    body: str
    created_at: datetime


class MyWork(BaseModel):
    """What a student sees of their own hand-in. The score and feedback stay empty until the work is returned."""

    assignment_id: int
    title: str
    due_at: datetime
    instructions: str
    points: float
    allow_file: bool
    allow_link: bool
    allow_text: bool
    state: Literal["assigned", "missing", "turned_in", "returned"]
    late: bool
    text: str | None = None
    link: str | None = None
    file_name: str | None = None
    file_size: int | None = None
    turned_in_at: datetime | None = None
    score: float | None = None
    feedback: str | None = None
    returned_at: datetime | None = None
    comments: list[CommentOut] = Field(default_factory=list)
    rubric: RubricOut | None = None


class WorkRow(BaseModel):
    student_id: int
    label: str
    synthetic: bool
    state: WorkState
    late: bool
    turned_in_at: datetime | None = None
    score: float | None = None


class WorkList(BaseModel):
    assignment_id: int
    title: str
    due_at: datetime
    points: float
    rows: list[WorkRow]


class TheirWork(BaseModel):
    """One student's hand-in as the instructor sees it, with the saved score even before it is returned."""

    student_id: int
    label: str
    synthetic: bool
    title: str
    due_at: datetime
    instructions: str
    points: float
    state: WorkState
    late: bool
    text: str | None = None
    link: str | None = None
    file_name: str | None = None
    file_size: int | None = None
    turned_in_at: datetime | None = None
    score: float | None = None
    feedback: str | None = None
    graded_at: datetime | None = None
    returned_at: datetime | None = None
    comments: list[CommentOut] = Field(default_factory=list)
    rubric: RubricOut | None = None


class GradeIn(BaseModel):
    """A score, or, for work with a rubric, the level chosen for each criterion (the score is then their sum)."""

    score: float | None = Field(default=None, ge=0, le=100)
    levels: dict[int, int] | None = Field(default=None, description="criterion id to level id")
    feedback: Text | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def _one_way(self):
        if (self.score is None) == (not self.levels):
            raise ValueError("send a score, or the levels chosen for a rubric, but not both")
        return self


class RubricLevelIn(BaseModel):
    label: Text = Field(min_length=1, max_length=100)
    points: float = Field(ge=0, le=100)


class RubricCriterionIn(BaseModel):
    title: Text = Field(min_length=1, max_length=200)
    description: Text | None = Field(default=None, max_length=1000)
    levels: list[RubricLevelIn] = Field(min_length=2, max_length=8)


class RubricIn(BaseModel):
    title: Text = Field(min_length=1, max_length=200)
    criteria: list[RubricCriterionIn] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def _checked(self):
        if not self.title.strip():
            raise ValueError("a rubric needs a title")
        for criterion in self.criteria:
            if not criterion.title.strip():
                raise ValueError("every criterion needs a title")
            if len({lvl.label for lvl in criterion.levels}) != len(criterion.levels):
                raise ValueError("the levels of a criterion must have different names")
            if max(lvl.points for lvl in criterion.levels) <= 0:
                raise ValueError("a criterion's best level must be worth some points")
        return self





class ResultCount(BaseModel):
    count: int


class ReviewGroup(BaseModel):
    course_id: int
    course_title: str
    assignment_id: int
    title: str
    due_at: datetime
    waiting: int
    graded: int
    not_returned: int


class TodoOut(BaseModel):
    assignment_id: int
    course_id: int
    course_title: str
    title: str
    due_at: datetime
    state: Literal["assigned", "missing", "done"]
    score: float
    possible: float
    has_work: bool


class CalendarItem(BaseModel):
    assignment_id: int
    course_id: int
    course_title: str
    title: str
    due_at: datetime
    state: Literal["assigned", "missing", "done"] | None = Field(default=None, description="students only")
    has_work: bool


NotificationKind = Literal["announcement", "work_returned", "work_turned_in", "comment", "due_soon"]


class NotificationOut(BaseModel):
    id: int
    kind: NotificationKind
    title: str
    link: str
    created_at: datetime
    read: bool


class NotificationList(BaseModel):
    unread: int
    items: list[NotificationOut]


class CategoryIn(BaseModel):
    name: Text = Field(min_length=1, max_length=100)
    weight: float = Field(gt=0, le=100)

    @model_validator(mode="after")
    def _not_blank(self):
        if not self.name.strip():
            raise ValueError("a category needs a name")
        return self


class CategoryOut(BaseModel):
    id: int
    name: str
    weight: float
    share: float = Field(description="its share of the total weight, in percent")
    assignments: int




class OverrideIn(BaseModel):
    score: float = Field(ge=0)
    reason: Text = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def _reason(self):
        if not self.reason.strip():
            raise ValueError("give a reason the student can read")
        return self


class AtRiskFactor(BaseModel):
    kind: Literal["missing_work", "low_scores", "falling_scores", "low_mastery", "inactive"]
    summary: str
    evidence: list[str]


class AtRiskStudent(BaseModel):
    student_id: int
    label: str
    synthetic: bool
    factors: list[AtRiskFactor]


class AtRiskReport(BaseModel):
    checked: int
    thresholds: dict[str, float]
    students: list[AtRiskStudent]


class QuestionReport(BaseModel):
    question_id: int
    prompt: str
    kind: Literal["single", "multiple", "short"]
    options: list[str]
    answered: int
    right: int
    percent_right: float | None
    chosen_counts: list[int]
    right_choices: list[int]
    class_missed: bool


class QuizReport(BaseModel):
    quiz_id: int
    title: str
    students: int = Field(description="students who took it; each one's latest attempt is used")
    attempts: int
    average_percent: float | None
    questions: list[QuestionReport]


class Comparison(BaseModel):
    n_with: int
    n_without: int
    average_with: float | None
    average_without: float | None
    difference: float | None = Field(description="null until both groups are big enough to compare")


class ContentItemReport(BaseModel):
    item_id: int
    title: str
    module: str
    kind: str
    completed: int
    not_completed: int
    scores: Comparison
    mastery: Comparison


class ContentReport(BaseModel):
    students: int
    min_group: int
    items: list[ContentItemReport]
