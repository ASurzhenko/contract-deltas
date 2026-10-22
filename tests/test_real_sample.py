"""The parsers run on a captured real model response (results/raw, deal D02), not on one the tests built."""

import json
import shutil
from pathlib import Path

import pytest

from contract_deltas import extract
from contract_deltas.bedrock import strip_response
from contract_deltas.schema import SchemaError, validate_changes

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "real_raw_response.json"


@pytest.fixture
def real():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def final_tool_input(real):
    message = real["attempts"][-1]["message"]
    return next(block["toolUse"]["input"] for block in message["content"] if "toolUse" in block)


def test_validator_parses_the_real_tool_input_into_non_default_values(real):
    changes = validate_changes(final_tool_input(real))

    assert {c.clause_type for c in changes} == {"payment_terms", "liability_cap", "data_processing"}
    added = next(c for c in changes if c.clause_type == "data_processing")
    assert added.change == "added" and added.direction == "buyer-favorable"
    assert added.signed_excerpt and added.summary
    assert all(c.summary and c.direction for c in changes)


def test_cache_loader_reads_the_real_file_back_with_its_usage_and_changes(real, tmp_path):
    path = tmp_path / "D02.json"
    shutil.copy(FIXTURE, path)

    loaded = extract._load_cached(path, real["cache_key"])

    assert loaded["outcome"] == "accepted" and len(loaded["changes"]) == 3
    assert loaded["attempts"][-1]["usage"]["inputTokens"] > 0
    assert extract._sum_usage(loaded["attempts"])["totalTokens"] == loaded["attempts"][-1]["usage"]["totalTokens"]
    assert extract._load_cached(path, "a-different-key") is None


def test_strip_response_keeps_the_real_shape(real):
    attempt = real["attempts"][-1]
    response = {
        "output": {"message": attempt["message"]},
        "stopReason": attempt["stopReason"],
        "usage": attempt["usage"],
        "metrics": {"latencyMs": attempt["latencyMs"]},
        "ResponseMetadata": {"RequestId": "must-not-survive"},
    }

    stripped = strip_response(response)

    assert stripped == {"message": attempt["message"], "stopReason": "tool_use",
                        "usage": attempt["usage"], "latencyMs": attempt["latencyMs"]}
    assert stripped["latencyMs"] > 0


def test_malformed_inputs_are_refused(real, tmp_path):
    path = tmp_path / "D02.json"
    path.write_text("{ not json", encoding="utf-8")
    assert extract._load_cached(path, real["cache_key"]) is None

    path.write_text(json.dumps({"cache_key": real["cache_key"]}), encoding="utf-8")
    assert extract._load_cached(path, real["cache_key"]) is None

    broken = final_tool_input(real)
    del broken["changes"][0]["direction"]
    with pytest.raises(SchemaError):
        validate_changes(broken)
