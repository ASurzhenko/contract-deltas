"""Generate the synthetic deal dataset from one spec.

The SPEC table below is the single authority for documents, labels and deals.csv.
Run `python scripts/generate_dataset.py` to rewrite data/ in place.

All parties, people and amounts are fictional. Patterns across deals are planted on
purpose; the README says so.
"""

import csv
import io
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from contract_deltas.io_utils import write_text  # noqa: E402

PROVIDER = "Lumen Data Ltd."

# Clause order in every sent.md. data_processing is absent from every sent.md.
CLAUSE_ORDER = [
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

HEADINGS = {
    "payment_terms": "Payment Terms",
    "price_discount": "Price Discount",
    "liability_cap": "Liability Cap",
    "auto_renewal": "Auto Renewal",
    "termination": "Termination",
    "sla": "Service Levels",
    "data_processing": "Data Processing",
    "confidentiality": "Confidentiality",
    "governing_law": "Governing Law",
    "warranty": "Warranty",
}

BASE = {
    "pt_days": 30,
    "pd_pct": 5,
    "lc_mult": "1x",
    "ar": True,
    "tm_convenience": False,
    "sl_uptime": "99.9",
    "sl_credits": False,
    "dp": False,
    "gl": "Delaware",
}

NUMBER_WORDS = {30: "thirty", 45: "forty-five", 60: "sixty"}

# deal_id, customer, outcome, amount_usd, days_to_close, overrides, labels, reorder
# labels: clause_type -> (change, direction). Direction is from the seller's side
# (the author of sent.md).
SPEC = [
    ("D01", "Harbor Logistics", "won", 42000, 38, {"pt_days": 60, "pd_pct": 10},
     {"payment_terms": ("modified", "buyer-favorable"), "price_discount": ("modified", "buyer-favorable")}, False),
    ("D02", "Pine Street Retail", "won", 96000, 71, {"pt_days": 60, "lc_mult": "2x", "dp": True},
     {"payment_terms": ("modified", "buyer-favorable"), "liability_cap": ("modified", "buyer-favorable"),
      "data_processing": ("added", "buyer-favorable")}, False),
    ("D03", "Atlas Dental Group", "lost", 58000, 83, {"pt_days": 60, "ar": False, "sl_credits": True},
     {"payment_terms": ("modified", "buyer-favorable"), "auto_renewal": ("removed", "buyer-favorable"),
      "sla": ("modified", "buyer-favorable")}, False),
    ("D04", "Cobalt Foods", "won", 120000, 66, {"pt_days": 45, "lc_mult": "2x", "dp": True},
     {"payment_terms": ("modified", "buyer-favorable"), "liability_cap": ("modified", "buyer-favorable"),
      "data_processing": ("added", "buyer-favorable")}, True),
    ("D05", "Maple Tool & Die", "lost", 35000, 91, {"pt_days": 60, "pd_pct": 12, "ar": False},
     {"payment_terms": ("modified", "buyer-favorable"), "price_discount": ("modified", "buyer-favorable"),
      "auto_renewal": ("removed", "buyer-favorable")}, False),
    ("D06", "Riverbend Clinics", "won", 64000, 44, {"lc_mult": "2x", "tm_convenience": True},
     {"liability_cap": ("modified", "buyer-favorable"), "termination": ("modified", "buyer-favorable")}, False),
    ("D07", "Summit Auto Parts", "won", 28000, 35, {"pt_days": 60},
     {"payment_terms": ("modified", "buyer-favorable")}, False),
    ("D08", "Ironwood Energy", "won", 138000, 79,
     {"pd_pct": 8, "lc_mult": "2x", "ar": False, "dp": True},
     {"price_discount": ("modified", "buyer-favorable"), "liability_cap": ("modified", "buyer-favorable"),
      "auto_renewal": ("removed", "buyer-favorable"), "data_processing": ("added", "buyer-favorable")}, False),
    ("D09", "Bluewater Shipping", "lost", 47000, 77, {"pt_days": 60, "ar": False, "gl": "England and Wales"},
     {"payment_terms": ("modified", "buyer-favorable"), "auto_renewal": ("removed", "buyer-favorable"),
      "governing_law": ("modified", "neutral")}, True),
    ("D10", "Granite Peak Mining", "lost", 73000, 88,
     {"pt_days": 60, "lc_mult": "2x", "ar": False, "tm_convenience": True},
     {"payment_terms": ("modified", "buyer-favorable"), "liability_cap": ("modified", "buyer-favorable"),
      "auto_renewal": ("removed", "buyer-favorable"), "termination": ("modified", "buyer-favorable")}, False),
    ("D11", "Oakfield Schools", "lost", 31000, 52, {"pd_pct": 10},
     {"price_discount": ("modified", "buyer-favorable")}, False),
    ("D12", "Silverline Telecom", "won", 110000, 62, {"lc_mult": "1.5x", "dp": True, "sl_uptime": "99.5"},
     {"liability_cap": ("modified", "buyer-favorable"), "data_processing": ("added", "buyer-favorable"),
      "sla": ("modified", "seller-favorable")}, False),
]

SIGNATORIES = [
    ("Dana Reyes", "Regional Sales Director", "Tomas Weber", "Head of Procurement"),
    ("Dana Reyes", "Regional Sales Director", "Priya Nair", "Chief Financial Officer"),
    ("Marcus Hale", "Senior Account Executive", "Elena Rossi", "Operations Director"),
    ("Marcus Hale", "Senior Account Executive", "Jonas Berg", "Managing Director"),
    ("Dana Reyes", "Regional Sales Director", "Aisha Karim", "Finance Manager"),
    ("Marcus Hale", "Senior Account Executive", "Liam O'Connor", "Chief Operating Officer"),
    ("Dana Reyes", "Regional Sales Director", "Mei Tanaka", "Procurement Lead"),
    ("Marcus Hale", "Senior Account Executive", "Carlos Duarte", "Chief Executive Officer"),
    ("Dana Reyes", "Regional Sales Director", "Hannah Frost", "General Counsel"),
    ("Marcus Hale", "Senior Account Executive", "Ivan Petrov", "Director of IT"),
    ("Dana Reyes", "Regional Sales Director", "Sofia Marin", "Business Manager"),
    ("Marcus Hale", "Senior Account Executive", "Noah Fischer", "Chief Technology Officer"),
]


def words(days: int) -> str:
    return f"{NUMBER_WORDS[days]} ({days})"


def clause_text(clause: str, p: dict, variant: int) -> str:
    """Body text of one clause. `variant` varies the wording of untouched clauses across deals."""
    if clause == "payment_terms":
        anchor = ["the invoice date", "receipt of the invoice", "the date printed on the invoice"][variant]
        return (f"Customer shall pay each invoice within {words(p['pt_days'])} days of {anchor}. "
                "Overdue amounts accrue interest at 1% per month.")
    if clause == "price_discount":
        return f"Provider shall apply a volume discount of {p['pd_pct']}% to the list price for all committed seats."
    if clause == "liability_cap":
        return (f"The total liability of each party under this Agreement shall not exceed {p['lc_mult']} the fees "
                "paid by Customer in the twelve (12) months preceding the claim.")
    if clause == "auto_renewal":
        return ("This Agreement shall renew automatically for successive twelve (12) month terms unless either "
                "party gives sixty (60) days written notice of non-renewal.")
    if clause == "termination":
        text = ("Either party may terminate this Agreement for a material breach that remains uncured thirty (30) "
                "days after written notice.")
        if p["tm_convenience"]:
            return text + " Customer may also terminate this Agreement for convenience on ninety (90) days written notice."
        return text + " Neither party may terminate this Agreement for convenience."
    if clause == "sla":
        text = f"Provider shall maintain monthly uptime of {p['sl_uptime']}%."
        if p["sl_credits"]:
            return text + (" If uptime falls below that level, Customer shall receive service credits of 5% of the "
                           "monthly fee for each 0.1% of shortfall.")
        return text + " No service credits are payable for downtime."
    if clause == "data_processing":
        return ("Provider shall process personal data only on documented instructions from Customer and shall "
                "sign the data processing addendum attached as Exhibit B.")
    if clause == "confidentiality":
        if variant == 1:
            return ("Each party shall protect the other party's confidential information as confidential for "
                    "three (3) years after disclosure.")
        return "Each party shall keep the other party's confidential information secret for three (3) years after disclosure."
    if clause == "governing_law":
        verb = "is governed by and construed under" if variant == 2 else "shall be governed by"
        place = "the State of Delaware" if p["gl"] == "Delaware" else "England and Wales"
        return f"This Agreement {verb} the laws of {place}."
    if clause == "warranty":
        if variant == 1:
            return ("Provider warrants that the services will conform to the documentation and shall correct any "
                    "non-conformity within ninety (90) days of notice.")
        return ("Provider warrants that the services will conform to the documentation and shall remedy any "
                "non-conformity within ninety (90) days of notice.")
    raise ValueError(clause)


def clause_present(clause: str, p: dict) -> bool:
    if clause == "auto_renewal":
        return p["ar"]
    if clause == "data_processing":
        return p["dp"]
    return True


def cosmetics(text: str) -> str:
    """Edits that change wording but not substance; applied to every clause of signed.md."""
    text = text.replace(" shall ", " will ")
    return re.sub(r"\b([A-Za-z-]+) \((\d+)\)", r"\2", text)


def render_document(index: int, customer: str, amount: int, days: int, p: dict, variant: int,
                    signed: bool, reorder: bool) -> str:
    sent_date = date(2026, 1, 5) + timedelta(days=17 * index)
    effective = sent_date + timedelta(days=days) if signed else sent_date
    order = list(CLAUSE_ORDER)
    if signed and reorder:
        i, j = order.index("confidentiality"), order.index("warranty")
        order[i], order[j] = order[j], order[i]
    lines = [
        "# Master Services Agreement",
        "",
        f'This agreement is made between {PROVIDER} ("Provider") and {customer} ("Customer").',
        "",
        f"Effective date: {effective.isoformat()}",
        f"Order value: USD {amount:,}",
        "",
    ]
    for clause in order:
        if not clause_present(clause, p):
            continue
        text = clause_text(clause, p, variant)
        if signed:
            text = cosmetics(text)
        lines += [f"## {HEADINGS[clause]}", "", text, ""]
    lines += ["---", ""]
    if signed:
        seller, seller_title, buyer, buyer_title = SIGNATORIES[index]
        lines += [f"Signed for Provider: {seller}, {seller_title}",
                  f"Signed for Customer: {buyer}, {buyer_title}"]
    else:
        lines += ["Signed for Provider: ____________________", "Signed for Customer: ____________________"]
    return "\n".join(lines) + "\n"


def generate(out_dir: Path) -> None:
    out_dir = Path(out_dir)
    rows = []
    for index, (deal_id, customer, outcome, amount, days, overrides, labels, reorder) in enumerate(SPEC):
        variant = index % 3
        sent_params = dict(BASE)
        signed_params = {**BASE, **overrides}
        write_text(out_dir / "deals" / deal_id / "sent.md",
                   render_document(index, customer, amount, days, sent_params, variant, False, False))
        write_text(out_dir / "deals" / deal_id / "signed.md",
                   render_document(index, customer, amount, days, signed_params, variant, True, reorder))
        changes = [{"clause_type": clause, "change": labels[clause][0], "direction": labels[clause][1]}
                   for clause in CLAUSE_ORDER if clause in labels]
        write_text(out_dir / "labels" / f"{deal_id}.json",
                   json.dumps({"deal_id": deal_id, "changes": changes}, indent=2, ensure_ascii=False) + "\n")
        rows.append([deal_id, customer, outcome, amount, days])
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["deal_id", "customer", "outcome", "amount_usd", "days_to_close"])
    writer.writerows(rows)
    write_text(out_dir / "deals.csv", buffer.getvalue())


if __name__ == "__main__":
    generate(REPO_ROOT / "data")
