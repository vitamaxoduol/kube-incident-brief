import asyncio
import json
from copy import deepcopy
from pathlib import Path

import httpx
import pytest
from google.genai import errors

from app import main
from app.main import app, get_brief_generator


BRIEF = {
    "observations": [{"finding": "The image pull timed out.", "evidence_ids": [1]}],
    "possible_causes": [],
    "next_checks": ["Check whether other nodes can reach harbor.example.test."],
}
EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def fake_output(output):
    async def generate(evidence):
        return output

    app.dependency_overrides[get_brief_generator] = lambda: generate


def test_success_trims_evidence_and_preserves_order(client):
    seen = []
    brief = deepcopy(BRIEF)
    brief["observations"][0]["evidence_ids"] = [1, 2]
    brief["possible_causes"] = [{"hypothesis": "Registry may be unreachable.", "evidence_ids": [2]}]

    async def generate(evidence):
        seen.extend(evidence)
        return json.dumps(brief)

    app.dependency_overrides[get_brief_generator] = lambda: generate
    response = client.post("/incidents/analyze", json={"evidence": [" first ", "\nsecond\t"]})
    assert response.status_code == 200
    assert response.json() == brief
    assert seen == ["first", "second"]


@pytest.mark.parametrize("body", [
    {}, {"evidence": []}, {"evidence": [""]}, {"evidence": [" \n\t "]},
    {"evidence": ["valid", " "]}, {"evidence": ["x"] * 31},
    {"evidence": ["x" * 2001]}, {"evidence": "log"}, {"evidence": [123]},
    {"evidence": [None]}, {"evidence": [True]}, {"evidence": None},
    {"evidence": ["valid"], "extra": "private-log"},
])
def test_invalid_input_does_not_call_provider(client, body):
    calls = []

    async def generate(evidence):
        calls.append(evidence)
        return json.dumps(BRIEF)

    app.dependency_overrides[get_brief_generator] = lambda: generate
    response = client.post("/incidents/analyze", json=body)
    assert response.status_code == 422
    assert calls == []
    assert all("input" not in error for error in response.json()["detail"])
    assert "private-log" not in response.text


def test_malformed_request_json_does_not_echo_logs(client):
    response = client.post(
        "/incidents/analyze", content='{"evidence": ["private-log"',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert "private-log" not in response.text


@pytest.mark.parametrize("evidence", [["x"], ["  " + "x" * 2000 + "  "] * 30])
def test_valid_boundaries_and_empty_possible_causes(client, evidence):
    fake_output(json.dumps(BRIEF))
    response = client.post("/incidents/analyze", json={"evidence": evidence})
    assert response.status_code == 200
    assert response.json()["possible_causes"] == []


@pytest.mark.parametrize("section, text_field", [
    ("observations", "finding"), ("possible_causes", "hypothesis"),
])
@pytest.mark.parametrize("ids", [[], [0], [-1], [2], [1, 2], [True], ["1"], [1.0]])
def test_invalid_citations_use_actual_response_validation(client, section, text_field, ids):
    brief = deepcopy(BRIEF)
    brief[section] = [{text_field: "private-log", "evidence_ids": ids}]
    fake_output(json.dumps(brief))
    response = client.post("/incidents/analyze", json={"evidence": ["one item"]})
    assert response.status_code == 502
    assert response.json() == {"detail": "Gemini returned an invalid incident brief."}


@pytest.mark.parametrize("output", [
    "not JSON: private-log", "", None, "null", "[]", "{}",
    json.dumps({**BRIEF, "unexpected": "private-log"}),
    json.dumps({**BRIEF, "next_checks": ["  "]}),
    json.dumps({**BRIEF, "observations": [{"finding": "private-log"}]}),
    json.dumps({**BRIEF, "possible_causes": None}),
])
def test_malformed_output_uses_actual_response_validation(client, output):
    fake_output(output)
    response = client.post("/incidents/analyze", json={"evidence": ["one item"]})
    assert response.status_code == 502
    assert response.json() == {"detail": "Gemini returned an invalid incident brief."}


@pytest.mark.parametrize("failure, status, detail", [
    (TimeoutError("private-log secret-key"), 504, "Gemini request timed out."),
    (httpx.ReadTimeout("private-log secret-key"), 504, "Gemini request timed out."),
    (errors.APIError(504, {"message": "private-log secret-key"}), 504, "Gemini request timed out."),
    (errors.APIError(429, {"message": "private-log secret-key"}), 502, "Gemini request failed."),
    (RuntimeError("private-log secret-key"), 502, "Gemini request failed."),
])
def test_provider_errors_are_sanitized(client, failure, status, detail):
    async def generate(evidence):
        raise failure

    app.dependency_overrides[get_brief_generator] = lambda: generate
    response = client.post("/incidents/analyze", json={"evidence": ["one item"]})
    assert response.status_code == status
    assert response.json() == {"detail": detail}


def test_overall_timeout_is_enforced(client, monkeypatch):
    monkeypatch.setattr(main, "TIMEOUT_SECONDS", 0.01)
    cancelled = []

    async def generate(evidence):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)

    app.dependency_overrides[get_brief_generator] = lambda: generate
    response = client.post("/incidents/analyze", json={"evidence": ["one item"]})
    assert response.status_code == 504
    assert cancelled == [True]


def test_missing_key_returns_503_without_creating_client(client):
    response = client.post("/incidents/analyze", json={"evidence": ["one item"]})
    assert response.status_code == 503
    assert response.json() == {"detail": "Gemini is not configured. Set GEMINI_API_KEY."}


@pytest.mark.parametrize("filename", ["image-pull.json", "image-pull-with-policy.json"])
def test_demo_requests_are_accepted(client, filename):
    fake_output(json.dumps(BRIEF))
    response = client.post("/incidents/analyze", json=json.loads((EXAMPLES / filename).read_text()))
    assert response.status_code == 200
