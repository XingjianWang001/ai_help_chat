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
