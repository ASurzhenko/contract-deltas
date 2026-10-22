"""Loading the dataset: deals and hand labels."""

import csv
import io
import json
from dataclasses import dataclass
from pathlib import Path

from contract_deltas.io_utils import read_text


@dataclass(frozen=True)
class Deal:
    deal_id: str
    customer: str
    outcome: str  # "won" | "lost"
    amount_usd: int
    days_to_close: int
    sent: str
    signed: str


@dataclass(frozen=True)
class Label:
    clause_type: str
    change: str
    direction: str


def _normalise(text: str) -> str:
    return text.replace("\r\n", "\n")


def load_deals(data_dir: Path) -> list[Deal]:
    data_dir = Path(data_dir)
    rows = csv.DictReader(io.StringIO(read_text(data_dir / "deals.csv")))
    deals = []
    for row in rows:
        folder = data_dir / "deals" / row["deal_id"]
        deals.append(Deal(
            deal_id=row["deal_id"],
            customer=row["customer"],
            outcome=row["outcome"],
            amount_usd=int(row["amount_usd"]),
            days_to_close=int(row["days_to_close"]),
            sent=_normalise(read_text(folder / "sent.md")),
            signed=_normalise(read_text(folder / "signed.md")),
        ))
    return deals


def load_labels(data_dir: Path) -> dict[str, list[Label]]:
    labels = {}
    for path in sorted((Path(data_dir) / "labels").glob("*.json")):
        payload = json.loads(read_text(path))
        labels[payload["deal_id"]] = [Label(**item) for item in payload["changes"]]
    return labels
