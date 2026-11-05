import json

import pytest
from google.genai import errors, types

import ai_handler


class FakeModels:
    """Rejects candidate_count > 1 with `multi_error`; answers single-candidate requests."""

    def __init__(self, multi_error):
        self.multi_error = multi_error
        self.candidate_counts = []

    def generate_content(self, model, contents, config):
        self.candidate_counts.append(config.candidate_count)
        if config.candidate_count > 1:
            raise self.multi_error
        content = types.Content(role="model", parts=[types.Part(text="好呀")])
        return types.GenerateContentResponse(candidates=[types.Candidate(content=content)])


@pytest.fixture
def fake_client(monkeypatch):
    def install(multi_error):
        models = FakeModels(multi_error)
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


@pytest.mark.parametrize("reply_count, expected", [(0, 1), (50, 8)])
def test_reply_count_is_clamped_to_1_to_8(fake_client, reply_count, expected):
    models = fake_client(api_error(400, "INVALID_ARGUMENT"))

    assert ai_handler._generate("sys", [], {"reply_count": reply_count, "model_name": "m"}) == ["好呀"] * expected
    assert models.candidate_counts.count(1) == expected  # one parallel request per missing reply


class FlakySingleModels(FakeModels):
    """Like FakeModels, but the first `failures` single-candidate requests raise."""

    def __init__(self, failures):
        super().__init__(api_error(400, "INVALID_ARGUMENT"))
        self.failures = failures

    def generate_content(self, model, contents, config):
        if config.candidate_count == 1 and self.failures > 0:
            self.failures -= 1
            raise api_error(503, "UNAVAILABLE")
        return super().generate_content(model, contents, config)


def test_one_failed_single_request_keeps_the_other_replies(monkeypatch):
    models = FlakySingleModels(failures=1)
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
