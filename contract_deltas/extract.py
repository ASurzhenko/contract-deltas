"""Extraction of one deal: cache key, retry loop, failure table, cache IO, run log."""

import copy
import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

from contract_deltas import config, prompts
from contract_deltas.bedrock import converse_tool, strip_response
from contract_deltas.data import Deal
from contract_deltas.io_utils import append_line, read_text, write_text
from contract_deltas.schema import CHANGES_SCHEMA, Change, SchemaError, validate_changes

logger = logging.getLogger(__name__)

ACCEPTED = "accepted"
REJECTED = "rejected_output"

_ATTEMPT_KEYS = ("maxTokens", "stopReason", "usage", "latencyMs", "message", "validationError")
_FILE_KEYS = ("cache_key", "model_id", "system_prompt_sha256", "outcome", "reason", "changes", "attempts")


@dataclass
class Extraction:
    deal_id: str
    outcome: str
    reason: str
    changes: list[Change]
    attempts: int
    usage: dict
    from_cache: bool
    calls_made: int = 0
    attempt_records: list[dict] = field(default_factory=list)


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def retry_policy_hash() -> str:
    """Derived from the retry templates and constants, so editing any of them changes every cache key."""
    policy = {
        "schema_template": prompts.RETRY_SCHEMA_TEMPLATE,
        "no_tool_message": prompts.RETRY_NO_TOOL_MESSAGE,
        "max_app_retries": config.MAX_APP_RETRIES,
        "max_tokens_factor": config.MAX_TOKENS_FACTOR,
        "retry_from_original": sorted(config.RETRY_FROM_ORIGINAL_STOP_REASONS),
        "not_retryable": sorted(config.NOT_RETRYABLE_STOP_REASONS),
        "text_only": sorted(config.TEXT_ONLY_STOP_REASONS),
    }
    return hashlib.sha256(canonical_json(policy).encode("utf-8")).hexdigest()


def build_kwargs(model_id: str, sent: str, signed: str, max_tokens: int = config.MAX_TOKENS) -> dict:
    """The exact attempt-0 Converse arguments."""
    return {
        "modelId": model_id,
        "system": [{"text": prompts.SYSTEM_PROMPT}],
        "messages": [{"role": "user", "content": [{"text": prompts.build_user_message(sent, signed)}]}],
        "toolConfig": {
            "tools": [{
                "toolSpec": {
                    "name": prompts.TOOL_NAME,
                    "description": prompts.TOOL_DESCRIPTION,
                    "inputSchema": {"json": CHANGES_SCHEMA},
                }
            }],
            "toolChoice": {"tool": {"name": prompts.TOOL_NAME}},
        },
        "inferenceConfig": {"maxTokens": max_tokens, "temperature": config.TEMPERATURE},
    }


def compute_cache_key(kwargs: dict) -> str:
    return hashlib.sha256((canonical_json(kwargs) + retry_policy_hash()).encode("utf-8")).hexdigest()


def raw_path(results_dir: Path, model_id: str, deal_id: str) -> Path:
    return Path(results_dir) / "raw" / config.slug(model_id) / f"{deal_id}.json"


def _lf(text: str) -> str:
    return text.replace("\r\n", "\n")


def _tool_uses(message: dict) -> list[dict]:
    return [block["toolUse"] for block in message.get("content", []) if "toolUse" in block]


def _echo(message: dict) -> dict:
    """The assistant message to send back; Converse rejects an empty content list."""
    echoed = copy.deepcopy(message)
    if not echoed.get("content"):
        echoed["content"] = [{"text": "(no answer)"}]
    return echoed


def _user_text(text: str) -> dict:
    return {"role": "user", "content": [{"text": text}]}


def _sum_usage(records: list[dict]) -> dict:
    total = {"inputTokens": 0, "outputTokens": 0, "totalTokens": 0}
    for record in records:
        for key in total:
            total[key] += record["usage"].get(key, 0)
    return total


def _run_attempts(client, kwargs: dict) -> tuple[str, str, list[Change], list[dict]]:
    """Retry loop over the failure table. Returns (outcome, reason, changes, attempt records)."""
    base_messages = kwargs["messages"]
    messages = base_messages
    max_tokens = kwargs["inferenceConfig"]["maxTokens"]
    records: list[dict] = []
    last_error = ""

    for attempt in range(config.MAX_APP_RETRIES + 1):
        call = {**kwargs, "messages": messages,
                "inferenceConfig": {**kwargs["inferenceConfig"], "maxTokens": max_tokens}}
        stripped = strip_response(converse_tool(client, **call))
        record = {"maxTokens": max_tokens, "stopReason": stripped["stopReason"], "usage": stripped["usage"],
                  "latencyMs": stripped["latencyMs"], "message": stripped["message"], "validationError": None}
        records.append(record)
        stop = stripped["stopReason"]
        message = stripped["message"]

        if stop in config.NOT_RETRYABLE_STOP_REASONS:
            return REJECTED, stop, [], records

        tool_uses = _tool_uses(message)
        if stop == "tool_use" or (stop in config.TEXT_ONLY_STOP_REASONS and tool_uses):
            if len(tool_uses) != 1 or tool_uses[0].get("name") != prompts.TOOL_NAME:
                last_error = "expected exactly one call of the report_changes tool"
                record["validationError"] = last_error
                messages = base_messages
                continue
            try:
                return ACCEPTED, "", validate_changes(tool_uses[0]["input"]), records
            except SchemaError as error:
                last_error = str(error)
                record["validationError"] = last_error
                messages = base_messages + [
                    _echo(message),
                    {"role": "user", "content": [{"toolResult": {
                        "toolUseId": tool_uses[0]["toolUseId"],
                        "content": [{"text": prompts.RETRY_SCHEMA_TEMPLATE.format(error=last_error)}],
                        "status": "error"}}]},
                ]
                continue

        if stop in config.TEXT_ONLY_STOP_REASONS:
            last_error = "no tool call in the answer"
            record["validationError"] = last_error
            messages = base_messages + [_echo(message), _user_text(prompts.RETRY_NO_TOOL_MESSAGE)]
            continue

        if stop == "max_tokens":
            last_error = "output truncated at max_tokens"
            record["validationError"] = last_error
            messages = base_messages
            max_tokens *= config.MAX_TOKENS_FACTOR
            continue

        if stop in config.RETRY_FROM_ORIGINAL_STOP_REASONS:
            last_error = stop
            record["validationError"] = last_error
            messages = base_messages
            continue

        return REJECTED, f"unknown_stop_reason:{stop}", [], records

    return REJECTED, f"invalid_after_{config.MAX_APP_RETRIES + 1}_attempts: {last_error}", [], records


def _save(path: Path, key: str, model_id: str, outcome: str, reason: str, changes: list[Change],
          records: list[dict]) -> None:
    payload = {
        "cache_key": key,
        "model_id": model_id,
        "system_prompt_sha256": prompts.SYSTEM_PROMPT_SHA256,
        "outcome": outcome,
        "reason": reason,
        "changes": [asdict(change) for change in changes],
        "attempts": [{name: record[name] for name in _ATTEMPT_KEYS} for record in records],
    }
    # ensure_ascii keeps model punctuation (long dashes) as escapes, never as literal characters.
    write_text(path, json.dumps(payload, indent=2, ensure_ascii=True) + "\n")


def _load_cached(path: Path, key: str) -> dict | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(read_text(path))
        if set(payload) != set(_FILE_KEYS):
            raise ValueError("unexpected keys")
    except ValueError:
        logger.warning("cache file for %s is unreadable, calling again", path.stem)
        return None
    return payload if payload["cache_key"] == key else None


def extract_deal(client, deal: Deal, model_id: str, results_dir: Path, refresh: bool = False,
                 refresh_rejected: bool = False) -> Extraction:
    """Serve a deal from the raw cache or call the model. Infrastructure failures raise and write nothing."""
    kwargs = build_kwargs(model_id, _lf(deal.sent), _lf(deal.signed))
    key = compute_cache_key(kwargs)
    path = raw_path(results_dir, model_id, deal.deal_id)

    cached = None if refresh else _load_cached(path, key)
    if cached is not None and refresh_rejected and cached["outcome"] == REJECTED:
        cached = None
    if cached is not None:
        return Extraction(
            deal_id=deal.deal_id, outcome=cached["outcome"], reason=cached["reason"],
            changes=[Change(**item) for item in cached["changes"]], attempts=len(cached["attempts"]),
            usage=_sum_usage(cached["attempts"]), from_cache=True, calls_made=0,
            attempt_records=cached["attempts"])

    outcome, reason, changes, records = _run_attempts(client, kwargs)
    _save(path, key, model_id, outcome, reason, changes, records)
    append_line(Path(results_dir) / "runs.jsonl", json.dumps({
        "deal_id": deal.deal_id, "model": config.slug(model_id),
        "system_prompt_sha256": prompts.SYSTEM_PROMPT_SHA256, "cache_key": key[:12],
        "outcome": outcome, "attempts": len(records)}, sort_keys=True))
    return Extraction(
        deal_id=deal.deal_id, outcome=outcome, reason=reason, changes=changes, attempts=len(records),
        usage=_sum_usage(records), from_cache=False, calls_made=len(records), attempt_records=records)
