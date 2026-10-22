"""The extraction contract. One schema is both the Bedrock tool input schema and the validator input."""

from dataclasses import dataclass

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match

CLAUSE_TYPES = [
    "payment_terms",
    "price_discount",
    "liability_cap",
    "auto_renewal",
    "termination",
    "sla",
    "data_processing",
    "confidentiality",
    "governing_law",
    "warranty",
]
OTHER = "other"
CHANGE_KINDS = ["modified", "added", "removed"]
DIRECTIONS = ["buyer-favorable", "seller-favorable", "neutral"]

CHANGES_SCHEMA = {
    "type": "object",
    "properties": {
        "changes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "clause_type": {"type": "string", "enum": CLAUSE_TYPES + [OTHER]},
                    "change": {"type": "string", "enum": CHANGE_KINDS},
                    "direction": {"type": "string", "enum": DIRECTIONS},
                    "summary": {"type": "string"},
                    "sent_excerpt": {"type": "string"},
                    "signed_excerpt": {"type": "string"},
                },
                "required": ["clause_type", "change", "direction", "summary", "sent_excerpt", "signed_excerpt"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["changes"],
    "additionalProperties": False,
}

_VALIDATOR = Draft202012Validator(CHANGES_SCHEMA)
_MAX_ERROR_CHARS = 300


class SchemaError(ValueError):
    """The model output does not satisfy the contract; the message is safe to echo back to the model."""


@dataclass(frozen=True)
class Change:
    clause_type: str
    change: str
    direction: str
    summary: str
    sent_excerpt: str
    signed_excerpt: str


def validate_changes(payload: object) -> list[Change]:
    error = best_match(_VALIDATOR.iter_errors(payload))
    if error is not None:
        where = "/".join(str(part) for part in error.absolute_path) or "(top level)"
        raise SchemaError(f"{where}: {error.message}"[:_MAX_ERROR_CHARS])
    seen = set()
    for item in payload["changes"]:
        clause_type = item["clause_type"]
        if clause_type == OTHER:
            continue
        if clause_type in seen:
            raise SchemaError(f"clause_type '{clause_type}' appears more than once; report one item per clause")
        seen.add(clause_type)
    return [Change(**item) for item in payload["changes"]]
