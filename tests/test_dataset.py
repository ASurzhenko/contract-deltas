import csv
import importlib.util
import json
import re
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"

HEADING_TO_TYPE = {
    "payment terms": "payment_terms",
    "price discount": "price_discount",
    "liability cap": "liability_cap",
    "auto renewal": "auto_renewal",
    "termination": "termination",
    "service levels": "sla",
    "data processing": "data_processing",
    "confidentiality": "confidentiality",
    "governing law": "governing_law",
    "warranty": "warranty",
}


def _load_generator():
    spec = importlib.util.spec_from_file_location("generate_dataset", REPO / "scripts" / "generate_dataset.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _files(root: Path):
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def _normalise(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\b[a-z-]+ \((\d+)\)", r"\1", text)
    text = text.replace(" shall ", " will ")
    return re.sub(r"\s+", " ", text).strip()


def _clauses(path: Path) -> dict:
    body = path.read_text(encoding="utf-8").split("\n---\n")[0]
    parts = re.split(r"^## (.+)$", body, flags=re.MULTILINE)
    return {HEADING_TO_TYPE[parts[i].strip().lower()]: _normalise(parts[i + 1]) for i in range(1, len(parts), 2)}


def _labels(deal_id: str) -> list:
    return json.loads((DATA / "labels" / f"{deal_id}.json").read_text(encoding="utf-8"))["changes"]


def _deal_ids():
    with open(DATA / "deals.csv", encoding="utf-8", newline="") as handle:
        return [row["deal_id"] for row in csv.DictReader(handle)]


def test_regeneration_is_byte_identical(tmp_path):
    _load_generator().generate(tmp_path)
    assert _files(tmp_path) == _files(DATA)
    for rel in _files(tmp_path):
        assert (tmp_path / rel).read_bytes() == (DATA / rel).read_bytes(), rel


def test_labelled_clauses_differ_exactly_and_headings_match_added_removed():
    for deal_id in _deal_ids():
        sent = _clauses(DATA / "deals" / deal_id / "sent.md")
        signed = _clauses(DATA / "deals" / deal_id / "signed.md")
        labels = {c["clause_type"]: c["change"] for c in _labels(deal_id)}

        added = set(signed) - set(sent)
        removed = set(sent) - set(signed)
        assert added == {t for t, k in labels.items() if k == "added"}, deal_id
        assert removed == {t for t, k in labels.items() if k == "removed"}, deal_id

        differing = {t for t in set(sent) & set(signed) if sent[t] != signed[t]}
        assert differing == {t for t, k in labels.items() if k == "modified"}, deal_id

        for control in ("confidentiality", "warranty"):
            assert sent[control] == signed[control], (deal_id, control)
            assert control not in labels


def test_dataset_totals_match_the_pattern_table():
    with open(DATA / "deals.csv", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 12
    assert Counter(r["outcome"] for r in rows) == {"won": 7, "lost": 5}
    changes = [c for r in rows for c in _labels(r["deal_id"])]
    assert len(changes) == 32
    assert Counter(c["change"] for c in changes) == {"modified": 23, "added": 4, "removed": 5}
    assert Counter(c["direction"] for c in changes) == {
        "buyer-favorable": 30, "seller-favorable": 1, "neutral": 1}
    assert Counter(c["clause_type"] for c in changes) == {
        "payment_terms": 8, "price_discount": 4, "liability_cap": 6, "auto_renewal": 5,
        "termination": 2, "sla": 2, "data_processing": 4, "governing_law": 1}


def test_deals_csv_columns_and_values_valid():
    with open(DATA / "deals.csv", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == ["deal_id", "customer", "outcome", "amount_usd", "days_to_close"]
        rows = list(reader)
    assert [r["deal_id"] for r in rows] == [f"D{i:02d}" for i in range(1, 13)]
    for row in rows:
        assert row["outcome"] in ("won", "lost")
        assert int(row["amount_usd"]) > 0
        assert int(row["days_to_close"]) > 0
        assert row["customer"]


def test_files_have_no_carriage_return_or_long_dashes():
    for rel in _files(DATA):
        raw = (DATA / rel).read_bytes()
        assert b"\r" not in raw, rel
        text = raw.decode("utf-8")
        assert "\u2014" not in text and "\u2013" not in text, rel


def test_cosmetic_edits_are_present_in_signed_documents():
    sent = (DATA / "deals" / "D07" / "sent.md").read_text(encoding="utf-8")
    signed = (DATA / "deals" / "D07" / "signed.md").read_text(encoding="utf-8")
    assert "thirty (30)" in sent and "thirty (30)" not in signed
    assert " shall " in sent and " shall " not in signed
    assert re.search(r"^Effective date: (.+)$", sent, re.M).group(1) != re.search(
        r"^Effective date: (.+)$", signed, re.M).group(1)
