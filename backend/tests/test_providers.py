"""TR-A-04: provider adapters and the fallback chain (no real provider is called)."""
import time

import httpx
import pytest

from app.config import Settings
from app.llm import adapter as llm
from app.llm.adapter import FallbackChain, LLMConfig, LLMError, OpenAICompatibleAdapter, StubAdapter, build_adapter

SECRET = "sk-test-secret-value"


def settings(**overrides) -> Settings:
    base = dict(
        database_url="x", redis_url="x", jwt_secret="x", mastery_service_url="x", mastery_service_token="x",
        llm_provider="gemini", llm_model="gemini-test", gemini_api_key="g-key", llm_fallback="groq,openai",
        groqcloud_api_key="groq-key", openai_api_key="oa-key",
    )
    return Settings(**{**base, **overrides})


@pytest.fixture(autouse=True)
def no_cooldowns():
    llm._cooling.clear()
    yield
    llm._cooling.clear()


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
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
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
        ("gemini", "gemini-test"), ("groq", "openai/gpt-oss-20b"), ("openai", "gpt-4.1-mini"),
    ]


def test_a_fallback_without_a_key_is_skipped_not_fatal():
    chain = build_adapter(settings(openai_api_key=""))
    assert [a.config.provider for a in chain.adapters] == ["gemini", "groq"]


def test_deepseek_is_no_longer_a_provider():
    with pytest.raises(ValueError):
        build_adapter(settings(llm_fallback="deepseek"))
    with pytest.raises(ValueError):
        build_adapter(settings(llm_provider="deepseek"))


def test_the_second_gemini_key_serves_several_models_and_the_first_key_can_follow():
    chain = build_adapter(settings(
        llm_provider="gemini_pro", llm_model="gemini-3.5-flash-lite", gemini_pro_api_key="pro-key",
        llm_fallback="gemini_pro:gemini-3.1-pro-preview, gemini, groq",
    ))
    assert [(a.config.provider, a.config.model) for a in chain.adapters] == [
        ("gemini_pro", "gemini-3.5-flash-lite"), ("gemini_pro", "gemini-3.1-pro-preview"),
        ("gemini", "gemini-3.5-flash-lite"), ("groq", "openai/gpt-oss-20b"),
    ]
    assert [a._api_key for a in chain.adapters[:3]] == ["pro-key", "pro-key", "g-key"]


def test_a_model_can_be_named_for_any_fallback_and_a_missing_pro_key_is_skipped():
    chain = build_adapter(settings(llm_fallback="groq:llama-test,gemini_pro"))
    assert [(a.config.provider, a.config.model) for a in chain.adapters] == [
        ("gemini", "gemini-test"), ("groq", "llama-test"),
    ]


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
    assert "gemini/gemini-model: a" in str(raised.value) and "groq/groq-model: b" in str(raised.value)


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


def test_the_whole_chain_answers_within_its_budget_or_fails(post, monkeypatch):
    calls, answers = post
    clock = [100.0]
    monkeypatch.setattr(llm.time, "monotonic", lambda: clock[0])
    config = LLMConfig("groq", "m", 12, 2, 0.1)
    adapter = OpenAICompatibleAdapter(config, SECRET, "https://x/v1")
    answers.append(completion("ok"))
    chain = FallbackChain([adapter], budget_s=5.0)
    assert chain.complete("s", "u") == "ok"
    assert calls[0]["timeout"] == 5.0  # the request is cut short by the budget, not the configured 12 s


def test_a_retry_that_cannot_finish_inside_the_budget_is_not_attempted(post, monkeypatch):
    calls, answers = post
    monkeypatch.setattr(llm.time, "monotonic", lambda: 100.0)  # time stands still, so only the budget check can stop it
    answers += [(503, {"error": "busy"}), completion("never reached")]
    adapter = OpenAICompatibleAdapter(LLMConfig("groq", "m", 12, 2, 0.1), SECRET, "https://x/v1")
    with pytest.raises(LLMError, match="time budget used up"):
        FallbackChain([adapter], budget_s=2.0).complete("s", "u")
    assert len(calls) == 1  # the 1.5 s back-off plus a useful second would pass the deadline


def test_no_provider_is_called_when_the_budget_is_already_gone(post):
    calls, answers = post
    adapter = OpenAICompatibleAdapter(LLMConfig("groq", "m", 12, 2, 0.1), SECRET, "https://x/v1")
    with pytest.raises(LLMError):
        FallbackChain([adapter], budget_s=0.2).complete("s", "u")
    assert calls == []


def test_the_budget_does_not_leak_into_later_calls(post):
    calls, answers = post
    answers += [completion("a"), completion("b")]
    adapter = OpenAICompatibleAdapter(LLMConfig("groq", "m", 12, 0, 0.1), SECRET, "https://x/v1")
    FallbackChain([adapter], budget_s=5.0).complete("s", "u")
    assert llm._deadline.get() is None
    assert adapter.complete("s", "u") == "b" and calls[1]["timeout"] == 12  # outside a chain only the config applies


def gemini_reply(text):
    return 200, {"candidates": [{"content": {"parts": [{"text": text}]}}]}


DENIED = (403, {"error": {"code": 403, "status": "PERMISSION_DENIED", "message": "Your project has been denied access."}})
OUT_OF_QUOTA = (429, {"error": {"code": 429, "message": "You exceeded your current quota, please check your plan and billing details.",
                                "details": [{"retryDelay": "30s"}]}})


def test_a_denied_key_is_not_retried_and_goes_to_the_back_of_the_chain(post):
    calls, answers = post
    pro = llm.GeminiAdapter(LLMConfig("gemini_pro", "flash", 5, 2, 0.1), "pro-key")
    backup = llm.GeminiAdapter(LLMConfig("gemini", "flash", 5, 2, 0.1), "g-key")
    chain = FallbackChain([pro, backup])
    answers += [DENIED, gemini_reply("from backup")]
    assert chain.complete("s", "u") == "from backup"
    assert [c["headers"]["x-goog-api-key"] for c in calls] == ["pro-key", "g-key"]  # one try, no retries
    calls.clear()
    answers.append(gemini_reply("again from backup"))
    assert chain.complete("s", "u") == "again from backup"
    assert [c["headers"]["x-goog-api-key"] for c in calls] == ["g-key"]  # the denied key is not tried first now


def test_an_exhausted_quota_moves_on_at_once_instead_of_waiting(post, monkeypatch):
    calls, answers = post
    slept = []
    monkeypatch.setattr(llm.time, "sleep", slept.append)
    pro = llm.GeminiAdapter(LLMConfig("gemini_pro", "pro", 5, 2, 0.1), "pro-key")
    groq = OpenAICompatibleAdapter(LLMConfig("groq", "m", 5, 2, 0.1), SECRET, "https://x/v1")
    answers += [OUT_OF_QUOTA, completion("from groq")]
    assert FallbackChain([pro, groq]).complete("s", "u") == "from groq"
    assert slept == [] and len(calls) == 2
    assert llm._cooling[("gemini_pro", "pro")] > llm.time.monotonic() + 25  # cools down for the delay it asked for


def test_a_cooling_provider_is_still_used_when_everything_else_fails(post):
    calls, answers = post
    pro = llm.GeminiAdapter(LLMConfig("gemini_pro", "flash", 5, 0, 0.1), "pro-key")
    groq = OpenAICompatibleAdapter(LLMConfig("groq", "m", 5, 0, 0.1), SECRET, "https://x/v1")
    llm._cooling[("gemini_pro", "flash")] = llm.time.monotonic() + 600
    answers += [(503, {"error": "busy"}), gemini_reply("the pro key works again")]
    chain = FallbackChain([pro, groq])
    assert chain.complete("s", "u") == "the pro key works again"
    assert chain.config.provider == "gemini_pro"
    assert ("gemini_pro", "flash") not in llm._cooling  # a success ends the cooldown


def test_a_transient_failure_does_not_start_a_cooldown(post):
    calls, answers = post
    first = Scripted("gemini", LLMError("HTTP 503 from gemini"))
    chain = FallbackChain([first, Scripted("groq", "ok")])
    assert chain.complete("s", "u") == "ok"
    assert llm._cooling == {}


def test_a_local_model_is_used_as_primary_or_fallback_with_its_own_host_and_no_key():
    primary = build_adapter(settings(
        llm_provider="local", llm_model="llama3", llm_fallback="", local_llm_base_url="http://host.docker.internal:11434/v1/",
    ))
    assert (primary.config.provider, primary.config.model) == ("local", "llama3")
    assert primary.adapters[0]._url == "http://host.docker.internal:11434/v1/chat/completions"  # trailing slash is fine
    chain = build_adapter(settings(
        llm_fallback="groq,local", local_llm_base_url="http://llm.internal/v1", llm_model_local="qwen",
    ))
    assert [(a.config.provider, a.config.model) for a in chain.adapters][-1] == ("local", "qwen")


def test_a_local_fallback_without_a_host_is_skipped_and_a_hosted_one_is_unaffected():
    chain = build_adapter(settings(llm_fallback="local,groq"))
    assert [a.config.provider for a in chain.adapters] == ["gemini", "groq"]


def test_a_local_request_sends_no_authorization_header_and_works_without_a_key(post):
    calls, answers = post
    answers.append(completion("from the local model"))
    chain = build_adapter(settings(
        llm_provider="local", llm_model="llama3", llm_fallback="", local_llm_base_url="http://llm.internal/v1",
    ))
    assert chain.complete("s", "u") == "from the local model"
    assert calls[0]["url"] == "http://llm.internal/v1/chat/completions" and calls[0]["headers"] == {}
    assert calls[0]["json"]["model"] == "llama3"


def test_a_local_key_is_sent_when_one_is_configured_and_never_appears_in_errors(post):
    calls, answers = post
    answers.append((500, {"error": SECRET}))
    adapter = OpenAICompatibleAdapter(LLMConfig("local", "m", 5, 0, 0.1), SECRET, "http://x/v1", key_required=False)
    with pytest.raises(LLMError) as raised:
        adapter.complete("s", "u")
    assert calls[0]["headers"] == {"Authorization": f"Bearer {SECRET}"} and SECRET not in str(raised.value)


def test_an_unreachable_local_server_is_an_ordinary_provider_failure_and_the_chain_moves_on(monkeypatch):
    def refuse(*args, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(llm.httpx, "post", refuse)
    monkeypatch.setattr(llm.time, "sleep", lambda _s: None)
    local = build_adapter(settings(
        llm_provider="local", llm_model="m", llm_fallback="", local_llm_base_url="http://down/v1", llm_max_retries=0,
    ))
    with pytest.raises(LLMError, match="every provider failed|ConnectError"):
        local.complete("s", "u")
    first = OpenAICompatibleAdapter(LLMConfig("local", "m", 5, 0, 0.1), "", "http://down/v1", key_required=False)
    second = Scripted("groq", "answered by the hosted fallback")
    assert FallbackChain([first, second]).complete("s", "u") == "answered by the hosted fallback"


def test_an_unreachable_provider_is_not_retried_and_is_skipped_for_the_next_requests(monkeypatch):
    """Regression: a local model that was not running cost its retries and backoff on every single request."""
    attempts = []
    sleeps = []

    def refuse(*args, **kwargs):
        attempts.append(1)
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(llm.httpx, "post", refuse)
    monkeypatch.setattr(llm.time, "sleep", sleeps.append)
    down = OpenAICompatibleAdapter(LLMConfig("local", "m", 5, 3, 0.1), "", "http://down/v1", key_required=False)
    hosted = Scripted("groq", "first answer", "second answer")
    chain = FallbackChain([down, hosted])
    assert chain.complete("s", "u") == "first answer"
    assert len(attempts) == 1 and sleeps == []  # three retries were configured, none was spent on a dead address
    assert chain.complete("s", "u") == "second answer"
    assert len(attempts) == 1  # the second request did not try the dead provider first
    assert llm._cooling[("local", "m")] > llm.time.monotonic() + 30


def test_a_real_openai_compatible_server_on_localhost_answers_through_the_chain():
    import json as jsonlib
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = jsonlib.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append((self.path, self.headers.get("Authorization"), body["model"]))
            reply = jsonlib.dumps({"choices": [{"message": {"content": "hello from the local server"}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(reply)))
            self.end_headers()
            self.wfile.write(reply)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        chain = build_adapter(settings(
            llm_provider="local", llm_model="tiny", llm_fallback="", local_llm_base_url=f"http://127.0.0.1:{server.server_port}/v1",
        ))
        assert chain.complete("be brief", "hi") == "hello from the local server"
    finally:
        server.shutdown()
    assert seen == [("/v1/chat/completions", None, "tiny")]  # no key, the configured model, the configured path


class SpendsItsShare:
    """A model too slow for the time it is given: it uses everything it gets, then times out."""

    def __init__(self, provider: str) -> None:
        self.config = LLMConfig(provider, f"{provider}-model", 0.2, 0, 30.0)
        self.calls = 0

    def complete(self, system, user, json_schema=None):
        self.calls += 1
        deadline = llm._deadline.get()
        time.sleep(max(0.0, deadline - time.monotonic()))
        raise LLMError("time budget used up")


def test_a_slow_first_provider_cannot_use_the_whole_budget_and_goes_behind_the_others():
    slow, quick = SpendsItsShare("local"), Scripted("groq", "from groq", "again")
    chain = FallbackChain([slow, quick], budget_s=6)
    started = time.monotonic()
    assert chain.complete("s", "u") == "from groq"
    first_took = time.monotonic() - started
    assert first_took < 5  # the slow one got a share (half here), not the 6 seconds
    started = time.monotonic()
    assert chain.complete("s", "u") == "again"
    assert time.monotonic() - started < 1  # it is tried last now, so the quick one answers at once
    assert slow.calls == 1


def test_the_last_provider_may_use_all_the_time_that_is_left():
    chain = FallbackChain([Scripted("gemini", LLMError("HTTP 503")), Scripted("groq", "late")], budget_s=6)
    assert chain.complete("s", "u") == "late"


def test_a_gemini_primary_with_another_providers_model_name_is_refused_at_start():
    with pytest.raises(ValueError, match="not a Gemini model"):
        build_adapter(settings(llm_provider="gemini_pro", llm_model="qwen2.5:3b", gemini_pro_api_key="pro-key"))


@pytest.mark.parametrize("model", ["gemini-3.5-flash-lite", "gemma-3-27b-it", "models/gemini-2.5-flash"])
def test_the_models_the_gemini_api_serves_are_accepted(model):
    chain = build_adapter(settings(llm_provider="gemini_pro", llm_model=model, gemini_pro_api_key="pro-key"))
    assert chain.adapters[0].config.model == model
