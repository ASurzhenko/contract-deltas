import pytest

from contract_deltas.schema import CHANGES_SCHEMA, SchemaError, validate_changes
from tests.conftest import change_item


def test_top_level_is_an_object_without_schema_keys():
    assert CHANGES_SCHEMA["type"] == "object"
    assert "$schema" not in CHANGES_SCHEMA and "$id" not in CHANGES_SCHEMA


def test_valid_payload_is_accepted_and_values_survive():
    changes = validate_changes({"changes": [change_item(), change_item("liability_cap", "modified")]})
    assert [c.clause_type for c in changes] == ["payment_terms", "liability_cap"]
    assert changes[0].signed_excerpt == "within 60 days"


def test_empty_changes_list_is_valid():
    assert validate_changes({"changes": []}) == []


@pytest.mark.parametrize("bad", [
    {"changes": [change_item(clause_type="not_a_type")]},
    {"changes": [change_item(change="deleted")]},
    {"changes": [change_item(direction="good")]},
    {"changes": [{k: v for k, v in change_item().items() if k != "summary"}]},
    {"changes": [{**change_item(), "summary": 5}]},
    {"changes": [{**change_item(), "extra": "x"}]},
    {"changes": "none"},
    {},
    [],
])
def test_invalid_payloads_are_rejected(bad):
    with pytest.raises(SchemaError):
        validate_changes(bad)


def test_two_items_with_the_same_real_clause_type_are_rejected():
    with pytest.raises(SchemaError, match="more than once"):
        validate_changes({"changes": [change_item(), change_item()]})


def test_two_other_items_are_accepted():
    changes = validate_changes({"changes": [change_item("other"), change_item("other")]})
    assert len(changes) == 2
