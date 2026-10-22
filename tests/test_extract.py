import json

import pytest
from botocore.stub import ANY

from contract_deltas import config, extract, prompts
from contract_deltas.bedrock import InfrastructureError
from contract_deltas.extract import ACCEPTED, REJECTED, build_kwargs, extract_deal
from tests.conftest import (FAKE_ARN, FAKE_ID, change_item, empty_response, make_deal, text_response,
                            tool_response, usage)

MODEL = "us.anthropic.claude-sonnet-4-6"


def expected(messages, max_tokens=config.MAX_TOKENS):
    """Pins the request fields that matter; the Stubber checks structure, not enum values."""
    return {
        "modelId": MODEL,
        "system": ANY,
        "messages": messages,
        "toolConfig": {"tools": ANY, "toolChoice": {"tool": {"name": prompts.TOOL_NAME}}},
        "inferenceConfig": {"maxTokens": max_tokens, "temperature": 0},
    }


def base_messages(deal):
    return build_kwargs(MODEL, deal.sent, deal.signed)["messages"]


def run(stubber_client, deal, tmp_path, **flags):
    return extract_deal(stubber_client, deal, MODEL, tmp_path, **flags)


def raw_file(tmp_path, deal_id="D01"):
    return extract.raw_path(tmp_path, MODEL, deal_id)


def runs_lines(tmp_path):
    path = tmp_path / "runs.jsonl"
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def test_valid_first_try(stubbed, tmp_path):
    client, stubber = stubbed
    deal = make_deal()
    stubber.add_response("converse", tool_response([change_item()]), expected(base_messages(deal)))

    result = run(client, deal, tmp_path)

    stubber.assert_no_pending_responses()
    assert result.outcome == ACCEPTED and result.attempts == 1 and result.calls_made == 1
    assert [c.clause_type for c in result.changes] == ["payment_terms"]
    assert result.usage == {"inputTokens": 100, "outputTokens": 50, "totalTokens": 150}
    assert len(runs_lines(tmp_path)) == 1


def test_schema_failure_retries_with_tool_result_carrying_the_same_id(stubbed, tmp_path):
    client, stubber = stubbed
    deal = make_deal()
    bad = tool_response([change_item(clause_type="not_a_type")], tool_use_id="tu-bad")
    stubber.add_response("converse", bad, expected(base_messages(deal)))
    retry_messages = base_messages(deal) + [
        bad["output"]["message"],
        {"role": "user", "content": [{"toolResult": {"toolUseId": "tu-bad", "content": ANY, "status": "error"}}]},
    ]
    stubber.add_response("converse", tool_response([change_item()]), expected(retry_messages))

    result = run(client, deal, tmp_path)

    stubber.assert_no_pending_responses()
    assert result.outcome == ACCEPTED and result.attempts == 2


@pytest.mark.parametrize("first", [
    pytest.param(
        {"output": {"message": {"role": "assistant", "content": [
            {"toolUse": {"toolUseId": "a", "name": prompts.TOOL_NAME, "input": {"changes": []}}},
            {"toolUse": {"toolUseId": "b", "name": prompts.TOOL_NAME, "input": {"changes": []}}}]}},
         "stopReason": "tool_use", "usage": usage(), "metrics": {"latencyMs": 1}},
        id="two-tool-use-blocks"),
    pytest.param(tool_response([], name="some_other_tool"), id="wrong-tool-name"),
    pytest.param(empty_response("malformed_tool_use"), id="malformed-tool-use"),
    pytest.param(empty_response("malformed_model_output"), id="malformed-model-output"),
])
def test_retry_from_original_messages_nothing_echoed(stubbed, tmp_path, first):
    client, stubber = stubbed
    deal = make_deal()
    stubber.add_response("converse", first, expected(base_messages(deal)))
    stubber.add_response("converse", tool_response([change_item()]), expected(base_messages(deal)))

    result = run(client, deal, tmp_path)

    stubber.assert_no_pending_responses()
    assert result.outcome == ACCEPTED and result.attempts == 2


def test_text_only_answer_gets_a_text_follow_up_without_tool_result(stubbed, tmp_path):
    client, stubber = stubbed
    deal = make_deal()
    text = text_response()
    stubber.add_response("converse", text, expected(base_messages(deal)))
    follow_up = base_messages(deal) + [
        text["output"]["message"],
        {"role": "user", "content": [{"text": prompts.RETRY_NO_TOOL_MESSAGE}]},
    ]
    stubber.add_response("converse", tool_response([change_item()]), expected(follow_up))

    result = run(client, deal, tmp_path)

    stubber.assert_no_pending_responses()
    assert result.outcome == ACCEPTED


def test_max_tokens_retries_from_original_messages_with_doubled_limit(stubbed, tmp_path):
    client, stubber = stubbed
    deal = make_deal()
    stubber.add_response("converse", empty_response("max_tokens"), expected(base_messages(deal), 2048))
    stubber.add_response("converse", tool_response([change_item()]), expected(base_messages(deal), 4096))

    result = run(client, deal, tmp_path)

    stubber.assert_no_pending_responses()
    assert result.outcome == ACCEPTED
    assert [a["maxTokens"] for a in result.attempt_records] == [2048, 4096]


@pytest.mark.parametrize("stop", ["content_filtered", "guardrail_intervened", "model_context_window_exceeded"])
def test_non_retryable_stop_reasons_are_rejected_at_once(stubbed, tmp_path, stop):
    client, stubber = stubbed
    stubber.add_response("converse", empty_response(stop))

    result = run(client, make_deal(), tmp_path)

    stubber.assert_no_pending_responses()
    assert result.outcome == REJECTED and result.reason == stop and result.calls_made == 1
    assert json.loads(raw_file(tmp_path).read_text(encoding="utf-8"))["outcome"] == REJECTED


def test_unknown_stop_reason_is_rejected_with_its_value(stubbed, tmp_path):
    client, stubber = stubbed
    stubber.add_response("converse", empty_response("brand_new_reason"))

    result = run(client, make_deal(), tmp_path)

    assert result.outcome == REJECTED and result.reason == "unknown_stop_reason:brand_new_reason"


def test_always_invalid_output_is_rejected_after_three_calls(stubbed, tmp_path):
    client, stubber = stubbed
    for index in range(3):
        stubber.add_response("converse", tool_response([change_item(change="deleted")], tool_use_id=f"t{index}"))

    result = run(client, make_deal(), tmp_path)

    stubber.assert_no_pending_responses()
    assert result.outcome == REJECTED and result.calls_made == 3 and result.changes == []
    assert result.reason.startswith("invalid_after_3_attempts")


@pytest.mark.parametrize("code", ["AccessDeniedException", "ResourceNotFoundException"])
def test_infrastructure_error_writes_no_cache_and_leaks_nothing(stubbed, tmp_path, code):
    client, stubber = stubbed
    stubber.add_client_error("converse", service_error_code=code,
                             service_message=f"denied for {FAKE_ARN}")

    with pytest.raises(InfrastructureError) as excinfo:
        run(client, make_deal(), tmp_path)

    assert excinfo.value.code == code
    assert FAKE_ID not in str(excinfo.value) and "arn:" not in str(excinfo.value)
    assert excinfo.value.__suppress_context__ is True
    assert not raw_file(tmp_path).exists()
    assert runs_lines(tmp_path) == []


def test_second_run_makes_zero_calls(stubbed, tmp_path):
    client, stubber = stubbed
    deal = make_deal()
    stubber.add_response("converse", tool_response([change_item()]))
    first = run(client, deal, tmp_path)
    assert first.calls_made == 1

    second = run(client, deal, tmp_path)  # nothing is stubbed: any call would raise

    assert second.from_cache and second.calls_made == 0
    assert second.changes == first.changes and second.usage == first.usage
    assert len(runs_lines(tmp_path)) == 1


@pytest.mark.parametrize("name, value", [
    ("TOOL_DESCRIPTION", "a different description"),
    ("USER_TEMPLATE", "{sent}|{signed}"),
    ("SYSTEM_PROMPT", "a different system prompt"),
    ("RETRY_SCHEMA_TEMPLATE", "changed {error}"),
    ("RETRY_NO_TOOL_MESSAGE", "changed text"),
])
def test_cache_key_depends_on_every_input(monkeypatch, name, value):
    deal = make_deal()
    before = extract.compute_cache_key(build_kwargs(MODEL, deal.sent, deal.signed))
    monkeypatch.setattr(prompts, name, value)
    after = extract.compute_cache_key(build_kwargs(MODEL, deal.sent, deal.signed))
    assert before != after


def test_cache_key_changes_with_retry_constants(monkeypatch):
    deal = make_deal()
    before = extract.compute_cache_key(build_kwargs(MODEL, deal.sent, deal.signed))
    monkeypatch.setattr(config, "MAX_APP_RETRIES", 5)
    assert extract.compute_cache_key(build_kwargs(MODEL, deal.sent, deal.signed)) != before


def test_crlf_and_lf_documents_hit_the_same_cache_entry(stubbed, tmp_path):
    client, stubber = stubbed
    lf = make_deal()
    crlf = make_deal(sent=lf.sent.replace("\n", "\r\n"), signed=lf.signed.replace("\n", "\r\n"))
    stubber.add_response("converse", tool_response([change_item()]))
    run(client, lf, tmp_path)

    again = run(client, crlf, tmp_path)

    assert again.from_cache and again.calls_made == 0


def test_rejected_output_is_served_from_cache_and_recalled_on_demand(stubbed, tmp_path):
    client, stubber = stubbed
    deal = make_deal()
    stubber.add_response("converse", empty_response("content_filtered"))
    run(client, deal, tmp_path)

    cached = run(client, deal, tmp_path)
    assert cached.from_cache and cached.outcome == REJECTED

    stubber.add_response("converse", tool_response([change_item()]))
    recalled = run(client, deal, tmp_path, refresh_rejected=True)
    assert not recalled.from_cache and recalled.outcome == ACCEPTED
    assert len(runs_lines(tmp_path)) == 2


def test_refresh_rejected_leaves_accepted_deals_alone_and_refresh_recalls_everything(stubbed, tmp_path):
    client, stubber = stubbed
    deal = make_deal()
    stubber.add_response("converse", tool_response([change_item()]))
    run(client, deal, tmp_path)

    untouched = run(client, deal, tmp_path, refresh_rejected=True)
    assert untouched.from_cache

    stubber.add_response("converse", tool_response([change_item()]))
    forced = run(client, deal, tmp_path, refresh=True)
    assert not forced.from_cache and forced.calls_made == 1


def test_doubled_limit_deal_is_served_from_cache_with_its_stored_usage(stubbed, tmp_path):
    client, stubber = stubbed
    deal = make_deal()
    stubber.add_response("converse", empty_response("max_tokens"))
    stubber.add_response("converse", tool_response([change_item()]))
    first = run(client, deal, tmp_path)

    second = run(client, deal, tmp_path)

    assert second.from_cache and second.calls_made == 0
    assert second.usage == first.usage == {"inputTokens": 200, "outputTokens": 100, "totalTokens": 300}


def test_saved_file_has_only_whitelisted_keys(stubbed, tmp_path):
    client, stubber = stubbed
    response = tool_response([change_item()])
    response["ResponseMetadata"] = {"RequestId": "request-id-must-not-be-saved", "HTTPHeaders": {"x-test": "1"}}
    stubber.add_response("converse", response)
    run(client, make_deal(), tmp_path)

    text = raw_file(tmp_path).read_text(encoding="utf-8")
    saved = json.loads(text)
    assert set(saved) == set(extract._FILE_KEYS)
    assert all(set(attempt) == set(extract._ATTEMPT_KEYS) for attempt in saved["attempts"])
    assert "request-id-must-not-be-saved" not in text and "ResponseMetadata" not in text
    assert saved["cache_key"] and saved["system_prompt_sha256"] == prompts.SYSTEM_PROMPT_SHA256


def test_long_dashes_in_model_text_are_saved_as_escapes(stubbed, tmp_path):
    client, stubber = stubbed
    stubber.add_response("converse", tool_response([change_item(summary="Longer \u2014 period")]))
    run(client, make_deal(), tmp_path)

    raw = raw_file(tmp_path).read_bytes()
    assert "\u2014".encode("utf-8") not in raw and b"\\u2014" in raw


def test_slug_has_no_colon_for_the_haiku_profile_id():
    slug = config.slug("us.anthropic.claude-haiku-4-5-20251001-v1:0")
    assert ":" not in slug and slug == "us.anthropic.claude-haiku-4-5-20251001-v1-0"


def test_runs_log_gains_one_line_per_real_batch_and_none_on_a_hit(stubbed, tmp_path):
    client, stubber = stubbed
    stubber.add_response("converse", tool_response([change_item()]))
    stubber.add_response("converse", tool_response([change_item()]))
    run(client, make_deal("D01"), tmp_path)
    run(client, make_deal("D02"), tmp_path)
    run(client, make_deal("D01"), tmp_path)  # hit

    lines = [json.loads(line) for line in runs_lines(tmp_path)]
    assert [line["deal_id"] for line in lines] == ["D01", "D02"]
    assert set(lines[0]) == {"deal_id", "model", "system_prompt_sha256", "cache_key", "outcome", "attempts"}
    assert len(lines[0]["cache_key"]) == 12


def test_unusable_cache_file_is_ignored_and_recalled(stubbed, tmp_path):
    client, stubber = stubbed
    deal = make_deal()
    path = raw_file(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    stubber.add_response("converse", tool_response([change_item()]))

    result = run(client, deal, tmp_path)

    assert not result.from_cache and result.outcome == ACCEPTED
