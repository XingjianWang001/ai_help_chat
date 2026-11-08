import json

import pytest
from google.genai import errors, types

import ai_handler


class FakeModels:
    """A candidate_count > 1 request raises `multi` if it is an error, else returns `multi` replies
    (0: the prompt was blocked, so there are no candidates); single-candidate requests return `single`."""

    def __init__(self, multi, single=1):
        self.multi, self.single = multi, single
        self.candidate_counts = []

    def generate_content(self, model, contents, config):
        self.candidate_counts.append(config.candidate_count)
        replies = self.single if config.candidate_count == 1 else self.multi
        if isinstance(replies, Exception):
            raise replies
        content = types.Content(role="model", parts=[types.Part(text="好呀")])
        candidates = [types.Candidate(content=content)] * replies
        return types.GenerateContentResponse(candidates=candidates or None)  # a blocked prompt has no candidates


@pytest.fixture
def fake_client(monkeypatch):
    def install(multi, single=1):
        models = FakeModels(multi, single)
        monkeypatch.setattr(ai_handler, "_client", lambda: type("Client", (), {"models": models})())
        monkeypatch.setattr(ai_handler, "_single_candidate_models", set())
        return models
    return install


def api_error(code, status):
    return errors.ClientError(code, {"error": {"code": code, "status": status, "message": status}})


def test_falls_back_to_single_requests_when_model_rejects_candidate_count(fake_client):
    models = fake_client(api_error(400, "INVALID_ARGUMENT"))

    assert ai_handler._generate("sys", [], {"reply_count": 3, "model_name": "m"}) == ["好呀"] * 3
    assert models.candidate_counts == [3, 1, 1, 1]
    assert "m" in ai_handler._single_candidate_models


def test_rate_limit_is_reported_without_extra_requests(fake_client):
    models = fake_client(api_error(429, "RESOURCE_EXHAUSTED"))

    with pytest.raises(errors.ClientError):
        ai_handler._generate("sys", [], {"reply_count": 3, "model_name": "m"})
    assert models.candidate_counts == [3]
    assert "m" not in ai_handler._single_candidate_models


# A model that takes candidate_count answers in one request, however few replies come back;
# the 400 and 429 answers are covered above.
@pytest.mark.parametrize("multi", [3, 1, 0], ids=["full", "some candidates filtered", "prompt blocked"])
def test_an_answered_candidate_count_request_is_the_only_request(fake_client, multi):
    models = fake_client(multi)

    assert ai_handler._generate("sys", [], {"reply_count": 3, "model_name": "m"}) == ["好呀"] * multi
    assert models.candidate_counts == [3]


def test_a_blocked_prompt_stops_the_single_request_fallback(fake_client):
    models = fake_client(api_error(400, "INVALID_ARGUMENT"), single=0)

    for expected in ([8, 1], [1], [1]):  # the first click finds out the model needs single requests
        models.candidate_counts = []
        assert ai_handler._generate("sys", [], {"reply_count": 8, "model_name": "m"}) == []
        assert models.candidate_counts == expected


@pytest.mark.parametrize("reply_count, expected", [(0, 1), (50, 8)])
def test_reply_count_is_clamped_to_1_to_8(fake_client, reply_count, expected):
    models = fake_client(api_error(400, "INVALID_ARGUMENT"))

    assert ai_handler._generate("sys", [], {"reply_count": reply_count, "model_name": "m"}) == ["好呀"] * expected
    assert models.candidate_counts.count(1) == expected  # one parallel request per missing reply


class FlakySingleModels(FakeModels):
    """Like FakeModels, but after the first `after` single-candidate requests, the next `failures` raise."""

    def __init__(self, failures, after=0):
        super().__init__(api_error(400, "INVALID_ARGUMENT"))
        self.failures, self.after = failures, after

    def generate_content(self, model, contents, config):
        if config.candidate_count == 1 and self.after > 0:
            self.after -= 1
        elif config.candidate_count == 1 and self.failures > 0:
            self.failures -= 1
            raise api_error(503, "UNAVAILABLE")
        return super().generate_content(model, contents, config)


def test_one_failed_single_request_keeps_the_other_replies(monkeypatch):
    models = FlakySingleModels(failures=1, after=1)  # the first request answered, so the rest were sent
    monkeypatch.setattr(ai_handler, "_client", lambda: type("Client", (), {"models": models})())
    monkeypatch.setattr(ai_handler, "_single_candidate_models", {"m"})

    assert ai_handler._generate("sys", [], {"reply_count": 3, "model_name": "m"}) == ["好呀"] * 2


def test_error_is_raised_when_every_single_request_fails(monkeypatch):
    models = FlakySingleModels(failures=3)
    monkeypatch.setattr(ai_handler, "_client", lambda: type("Client", (), {"models": models})())
    monkeypatch.setattr(ai_handler, "_single_candidate_models", {"m"})

    with pytest.raises(errors.ClientError):
        ai_handler._generate("sys", [], {"reply_count": 3, "model_name": "m"})


class RejectAllModels(FakeModels):
    """Every request fails with a 400, as with an invalid API key."""

    def generate_content(self, model, contents, config):
        self.candidate_counts.append(config.candidate_count)
        raise api_error(400, "INVALID_ARGUMENT")


def test_a_400_that_single_requests_also_get_is_raised_without_marking_the_model(monkeypatch):
    models = RejectAllModels(None)
    monkeypatch.setattr(ai_handler, "_client", lambda: type("Client", (), {"models": models})())
    monkeypatch.setattr(ai_handler, "_single_candidate_models", set())

    with pytest.raises(errors.ClientError):
        ai_handler._generate("sys", [], {"reply_count": 8, "model_name": "m"})
    assert models.candidate_counts == [8, 1]
    assert "m" not in ai_handler._single_candidate_models


@pytest.fixture
def config_file(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    monkeypatch.setattr(ai_handler, "CONFIG_FILE", str(path))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    for name in ("API_KEY", "GLOBAL_PROMPT", "MODEL_NAME"):  # load_app_config rewrites these globals
        monkeypatch.setattr(ai_handler, name, getattr(ai_handler, name))
    return path


CONFIG = {"gemini_api_key": "AIza-real", "model_name": "gemini-flash-latest", "global_prompt": "我是一名大学生"}


def test_config_saved_with_a_bom_is_read(config_file):  # older Windows Notepad adds one
    config_file.write_bytes(json.dumps(CONFIG, ensure_ascii=False).encode("utf-8-sig"))

    ai_handler.load_app_config()

    assert ai_handler.API_KEY == "AIza-real"


@pytest.mark.parametrize("content", [json.dumps(CONFIG, ensure_ascii=False).encode("gbk"), b"[]"], ids=["gbk", "not an object"])
def test_unreadable_config_does_not_stop_the_app(config_file, content):
    config_file.write_bytes(content)

    ai_handler.load_app_config()  # also runs on `import ai_handler`, i.e. at app start

    assert ai_handler.API_KEY is None


def test_failed_config_save_keeps_the_api_key(config_file, monkeypatch):
    config_file.write_text(json.dumps(CONFIG), encoding="utf-8")

    def disk_full(obj, f, **kwargs):  # write part of the file, then the disk fills up
        f.write("{")
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(ai_handler.json, "dump", disk_full)
    with pytest.raises(OSError):
        ai_handler.save_app_config("gemini-3.8-flash", "新的人设")

    assert json.loads(config_file.read_text(encoding="utf-8")) == CONFIG
    assert [p.name for p in config_file.parent.iterdir()] == ["config.json"]


def test_saving_keeps_a_private_config_private(config_file):
    config_file.write_text(json.dumps(CONFIG), encoding="utf-8")
    config_file.chmod(0o600)  # the file holds the API key

    ai_handler.save_app_config("gemini-3.8-flash", "新的人设")

    assert config_file.stat().st_mode & 0o777 == 0o600


def test_first_config_save_is_private(config_file):
    ai_handler.save_app_config("gemini-3.8-flash", "新的人设")

    assert config_file.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("content", ["[]", "null", '"key"'])
def test_config_that_is_not_an_object_can_still_be_saved(config_file, content):
    config_file.write_text(content, encoding="utf-8")

    ai_handler.save_app_config("gemini-3.8-flash", "新的人设")

    assert ai_handler.MODEL_NAME == "gemini-3.8-flash"


def test_null_global_prompt_reads_as_empty(config_file):
    config_file.write_text(json.dumps({**CONFIG, "global_prompt": None}), encoding="utf-8")

    ai_handler.load_app_config()

    assert ai_handler.GLOBAL_PROMPT == ""
