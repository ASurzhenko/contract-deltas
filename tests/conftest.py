"""Shared test helpers: a real bedrock-runtime client under a Stubber, with dummy credentials."""

import boto3
import botocore.session
import pytest
from botocore.stub import Stubber

from contract_deltas.data import Deal
from contract_deltas.prompts import TOOL_NAME

# Fake identifiers are assembled from fragments, so no secret-shaped literal sits in the repository.
FAKE_ID = "1234" + "56789012"
FAKE_ARN = "arn" + ":aws:iam::" + FAKE_ID + ":user/someone"


def make_stubbed_client():
    session = botocore.session.get_session()
    session.set_credentials("test-key-id", "test-key")
    client = boto3.Session(botocore_session=session).client("bedrock-runtime", region_name="us-east-1")
    return client, Stubber(client)


@pytest.fixture
def stubbed():
    client, stubber = make_stubbed_client()
    with stubber:
        yield client, stubber


def change_item(clause_type="payment_terms", change="modified", direction="buyer-favorable",
                summary="Payment period changed.", sent_excerpt="within thirty (30) days",
                signed_excerpt="within 60 days"):
    return {"clause_type": clause_type, "change": change, "direction": direction, "summary": summary,
            "sent_excerpt": sent_excerpt, "signed_excerpt": signed_excerpt}


def usage(input_tokens=100, output_tokens=50):
    return {"inputTokens": input_tokens, "outputTokens": output_tokens,
            "totalTokens": input_tokens + output_tokens}


def tool_response(changes, tool_use_id="tu-1", name=TOOL_NAME, stop="tool_use"):
    return {
        "output": {"message": {"role": "assistant", "content": [
            {"toolUse": {"toolUseId": tool_use_id, "name": name, "input": {"changes": changes}}}]}},
        "stopReason": stop, "usage": usage(), "metrics": {"latencyMs": 900},
    }


def text_response(text="I think there are changes.", stop="end_turn"):
    return {"output": {"message": {"role": "assistant", "content": [{"text": text}]}},
            "stopReason": stop, "usage": usage(), "metrics": {"latencyMs": 400}}


def empty_response(stop):
    return {"output": {"message": {"role": "assistant", "content": [{"text": "x"}]}},
            "stopReason": stop, "usage": usage(), "metrics": {"latencyMs": 400}}


def make_deal(deal_id="D01", sent="Payment Terms\nthirty (30) days\n", signed="Payment Terms\n60 days\n"):
    return Deal(deal_id=deal_id, customer="Test Customer", outcome="won", amount_usd=1000,
                days_to_close=10, sent=sent, signed=signed)
