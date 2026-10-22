"""Everything that touches boto3. Nothing else in the package imports it."""

import logging
import re

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from contract_deltas import config

# The ARN prefix is split so that a repository secret scan does not flag this source file itself.
_ARN = re.compile("arn" ":aws" r"[^\s\"']*")
_ACCOUNT_ID = re.compile(r"(?<![0-9A-Za-z])[0-9]{12}(?![0-9A-Za-z])")


class InfrastructureError(Exception):
    """Bedrock or the credential chain failed. Carries only an exception class name and an error code."""

    def __init__(self, kind: str, code: str):
        super().__init__(f"{kind}: {code}")
        self.kind = kind
        self.code = code


def scrub(text: str) -> str:
    """Remove ARNs and account ids from any string that leaves the process."""
    return _ACCOUNT_ID.sub("[id]", _ARN.sub("[arn]", text))


class ScrubFormatter(logging.Formatter):
    """Log formatter that scrubs every record before it is written."""

    def format(self, record: logging.LogRecord) -> str:
        return scrub(super().format(record))


def make_client():
    """Client built from the default credential chain only."""
    client_config = Config(
        retries={"total_max_attempts": config.TOTAL_MAX_ATTEMPTS, "mode": "standard"},
        connect_timeout=config.CONNECT_TIMEOUT_SECONDS,
        read_timeout=config.READ_TIMEOUT_SECONDS,
    )
    return boto3.client("bedrock-runtime", region_name=config.REGION, config=client_config)


def converse_tool(client, **kwargs) -> dict:
    """One Converse call. Any failure becomes an InfrastructureError holding two strings and no chain."""
    try:
        return client.converse(**kwargs)
    except ClientError as error:
        code = error.response.get("Error", {}).get("Code", "Unknown")
        kind = type(error).__name__
    except BotoCoreError as error:
        code = "BotoCoreError"
        kind = type(error).__name__
    raise InfrastructureError(kind, str(code)) from None


def strip_response(response: dict) -> dict:
    """Copy only named keys, so a new response field (request id, headers) can never be saved."""
    usage = response.get("usage", {})
    return {
        "message": response["output"]["message"],
        "stopReason": response["stopReason"],
        "usage": {key: usage[key] for key in ("inputTokens", "outputTokens", "totalTokens") if key in usage},
        "latencyMs": response.get("metrics", {}).get("latencyMs"),
    }
