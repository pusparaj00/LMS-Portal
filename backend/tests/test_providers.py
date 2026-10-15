"""TR-A-04: provider adapters and the fallback chain (no real provider is called)."""
import httpx
import pytest

from app.config import Settings
from app.llm import adapter as llm
from app.llm.adapter import FallbackChain, LLMConfig, LLMError, OpenAICompatibleAdapter, StubAdapter, build_adapter

SECRET = "sk-test-secret-value"


def settings(**overrides) -> Settings:
    base = dict(
        database_url="x", redis_url="x", jwt_secret="x", mastery_service_url="x", mastery_service_token="x",
        llm_provider="gemini", llm_model="gemini-test", gemini_api_key="g-key", llm_fallback="groq,deepseek,openai",
        groqcloud_api_key="groq-key", deepseek_api_key="ds-key", openai_api_key="oa-key",
    )
    return Settings(**{**base, **overrides})


class Scripted:
    def __init__(self, provider, *outcomes):
        self.config = LLMConfig(provider, f"{provider}-model", 1.0, 0, 0.1)
        self.outcomes = list(outcomes)
        self.calls = 0

    def complete(self, system, user, json_schema=None):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture
def post(monkeypatch):
    """Replace httpx.post with a scripted sequence of (status, json) answers and record the requests."""
    calls = []
    answers: list[tuple[int, dict]] = []

    def fake(url, json=None, headers=None, timeout=None):
        calls.append({"url": url, "json": json, "headers": headers})
        status, payload = answers.pop(0)
        return httpx.Response(status, json=payload, request=httpx.Request("POST", url))

    monkeypatch.setattr(llm.httpx, "post", fake)
    monkeypatch.setattr(llm.time, "sleep", lambda _s: None)
    return calls, answers


def completion(text):
    return 200, {"choices": [{"message": {"content": text}}]}


def test_the_chain_is_built_in_the_configured_order_with_the_agreed_models():
    chain = build_adapter(settings())
    assert isinstance(chain, FallbackChain)
    assert [(a.config.provider, a.config.model) for a in chain.adapters] == [
        ("gemini", "gemini-test"), ("groq", "openai/gpt-oss-20b"), ("deepseek", "deepseek-flash"),
        ("openai", "gpt-4.1-mini"),
    ]


def test_a_fallback_without_a_key_is_skipped_not_fatal():
    chain = build_adapter(settings(deepseek_api_key=""))
    assert [a.config.provider for a in chain.adapters] == ["gemini", "groq", "openai"]


def test_no_fallback_configured_means_a_single_adapter():
    assert build_adapter(settings(llm_fallback="")).config.provider == "gemini"
    assert isinstance(build_adapter(settings(llm_provider="stub", llm_model="stub")), StubAdapter)


def test_unknown_providers_are_refused():
    with pytest.raises(ValueError):
        build_adapter(settings(llm_provider="nonsense"))
    with pytest.raises(ValueError):
        build_adapter(settings(llm_fallback="groq,nonsense"))


def test_the_next_provider_answers_when_the_first_fails():
    first = Scripted("gemini", LLMError("HTTP 429 from the model"))
    second = Scripted("groq", "from groq")
    chain = FallbackChain([first, second])
    assert chain.config.provider == "gemini"  # before any call, the primary
    assert chain.complete("s", "u") == "from groq"
    assert chain.config.provider == "groq"  # what the log records is the provider that answered
    assert (first.calls, second.calls) == (1, 1)


def test_the_primary_is_used_again_on_the_next_call():
    first = Scripted("gemini", "one", "two")
    chain = FallbackChain([first, Scripted("groq", "unused")])
    assert [chain.complete("s", "u"), chain.complete("s", "u")] == ["one", "two"]


def test_every_provider_failing_raises_one_error_naming_them_all():
    chain = FallbackChain([Scripted("gemini", LLMError("a")), Scripted("groq", LLMError("b"))])
    with pytest.raises(LLMError) as raised:
        chain.complete("s", "u")
    assert "gemini: a" in str(raised.value) and "groq: b" in str(raised.value)


def test_the_openai_compatible_request_has_the_expected_shape(post):
    calls, answers = post
    answers.append(completion('{"route": "hint"}'))
    adapter = OpenAICompatibleAdapter(LLMConfig("groq", "openai/gpt-oss-20b", 5, 0, 0.1), SECRET, "https://example.test/v1")
    schema = {"type": "object", "properties": {"route": {"type": "string"}}}
    assert adapter.complete("be brief", "hello", schema) == '{"route": "hint"}'
    sent = calls[0]
    assert sent["url"] == "https://example.test/v1/chat/completions"
    assert sent["headers"] == {"Authorization": f"Bearer {SECRET}"}
    body = sent["json"]
    assert body["model"] == "openai/gpt-oss-20b" and body["temperature"] == 0.1
    assert body["response_format"] == {"type": "json_object"}
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    assert body["messages"][0]["content"].startswith("be brief") and "JSON schema" in body["messages"][0]["content"]


def test_plain_text_requests_do_not_ask_for_json(post):
    calls, answers = post
    answers.append(completion("hi"))
    OpenAICompatibleAdapter(LLMConfig("openai", "m", 5, 0, 0.1), SECRET, "https://x/v1").complete("s", "u")
    assert "response_format" not in calls[0]["json"]


def test_a_transient_error_is_retried_and_a_rejected_request_is_not(post):
    calls, answers = post
    config = LLMConfig("openai", "m", 5, 2, 0.1)
    answers += [(503, {"error": "busy"}), completion("ok")]
    assert OpenAICompatibleAdapter(config, SECRET, "https://x/v1").complete("s", "u") == "ok" and len(calls) == 2
    calls.clear()
    answers += [(401, {"error": "bad key"}), completion("never reached")]
    with pytest.raises(LLMError):
        OpenAICompatibleAdapter(config, SECRET, "https://x/v1").complete("s", "u")
    assert len(calls) == 1


def test_errors_never_contain_the_key(post):
    calls, answers = post
    answers.append((500, {"error": SECRET}))
    with pytest.raises(LLMError) as raised:
        OpenAICompatibleAdapter(LLMConfig("openai", "m", 5, 0, 0.1), SECRET, "https://x/v1").complete("s", "u")
    assert SECRET not in str(raised.value)


def test_a_daily_quota_answer_is_not_retried_and_the_chain_moves_on(post):
    calls, answers = post
    quota = {"error": {"message": "quota", "details": [{"retryDelay": "44138s"}]}}
    answers += [(429, quota), completion("from the fallback")]
    gemini = llm.GeminiAdapter(LLMConfig("gemini", "g", 5, 2, 0.1), SECRET)
    groq = OpenAICompatibleAdapter(LLMConfig("groq", "m", 5, 2, 0.1), SECRET, "https://x/v1")
    assert FallbackChain([gemini, groq]).complete("s", "u") == "from the fallback"
    assert len(calls) == 2  # one try on the exhausted provider, not three


def test_a_short_provider_delay_is_waited_out(post, monkeypatch):
    calls, answers = post
    slept = []
    monkeypatch.setattr(llm.time, "sleep", slept.append)
    answers += [(429, {"error": {"details": [{"retryDelay": "7s"}]}}), (200, {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]})]
    assert llm.GeminiAdapter(LLMConfig("gemini", "g", 5, 2, 0.1), SECRET).complete("s", "u") == "ok"
    assert slept == [7.0]


def test_a_billing_or_quota_429_is_not_retried(post):
    calls, answers = post
    answers += [(429, {"error": {"code": "insufficient_quota", "message": "You exceeded your current quota"}}),
                completion("never reached")]
    config = LLMConfig("openai", "m", 5, 2, 0.1)
    with pytest.raises(LLMError):
        OpenAICompatibleAdapter(config, SECRET, "https://x/v1").complete("s", "u")
    assert len(calls) == 1


def test_a_plain_rate_limit_429_is_still_retried(post):
    calls, answers = post
    answers += [(429, {"error": {"message": "Rate limit reached, slow down"}}), completion("ok")]
    config = LLMConfig("groq", "m", 5, 2, 0.1)
    assert OpenAICompatibleAdapter(config, SECRET, "https://x/v1").complete("s", "u") == "ok" and len(calls) == 2


def test_mistral_and_openrouter_join_the_chain_with_their_own_endpoints_and_models():
    chain = build_adapter(
        settings(llm_fallback="mistral,openrouter", mistral_api_key="m-key", openrouter_api_key="or-key")
    )
    assert [(a.config.provider, a.config.model) for a in chain.adapters] == [
        ("gemini", "gemini-test"), ("mistral", "mistral-small-2603"), ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free"),
    ]
    assert chain.adapters[1]._url == "https://api.mistral.ai/v1/chat/completions"
    assert chain.adapters[2]._url == "https://openrouter.ai/api/v1/chat/completions"
