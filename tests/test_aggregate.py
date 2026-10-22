from fractions import Fraction

from contract_deltas import config
from contract_deltas.aggregate import aggregate
from contract_deltas.data import load_deals, load_labels
from contract_deltas.io_utils import read_text
from contract_deltas.report import labels_report
from contract_deltas.schema import Change
from tests.conftest import make_deal


def labelled():
    deals = load_deals(config.DATA_DIR)
    return deals, load_labels(config.DATA_DIR)


def test_aggregation_over_labels_reproduces_every_number_in_the_pattern_table():
    deals, labels = labelled()
    result = aggregate(deals, labels)
    s = result.stats

    assert (result.n_used, result.n_total, result.excluded) == (12, 12, [])

    pt = s["payment_terms"]
    assert (len(pt.changed), pt.won_with, pt.n_with, pt.won_without, pt.n_without) == (8, 4, 8, 3, 4)
    assert pt.mean_days_with == Fraction(549, 8) and pt.mean_days_without == Fraction(237, 4)

    lc = s["liability_cap"]
    assert (len(lc.changed), lc.won_with, lc.won_without, lc.n_without) == (6, 5, 2, 6)

    ar = s["auto_renewal"]
    assert (len(ar.changed), ar.won_with, ar.won_without, ar.n_without) == (5, 1, 6, 7)
    assert ar.mean_days_with == Fraction(418, 5) and ar.mean_days_without == Fraction(368, 7)
    assert ar.kinds == {"removed": 5}

    dp = s["data_processing"]
    assert (len(dp.changed), dp.won_with, dp.won_without, dp.n_without) == (4, 4, 3, 8)
    assert dp.kinds == {"added": 4} and len(dp.added_in) == 4

    assert [len(s[c].changed) for c in ("price_discount", "termination", "sla", "governing_law")] == [4, 2, 2, 1]
    assert len(s["confidentiality"].changed) == 0 and len(s["warranty"].changed) == 0


def test_other_items_and_rejected_deals_are_excluded_and_denominator_shrinks():
    deals = [make_deal("A"), make_deal("B"), make_deal("C")]
    changes = {
        "A": [Change("payment_terms", "modified", "buyer-favorable", "", "", ""),
              Change("other", "modified", "neutral", "", "", "")],
        "B": [Change("payment_terms", "modified", "buyer-favorable", "", "", "")],
        "C": [],
    }

    result = aggregate(deals, changes, excluded=["B"])

    assert (result.n_used, result.n_total, result.excluded) == (2, 3, ["B"])
    assert result.stats["payment_terms"].changed == ["A"]
    assert "other" not in result.stats


def test_labels_report_regenerated_from_committed_labels_equals_the_committed_file():
    deals, labels = labelled()
    committed = read_text(config.RESULTS_DIR / "report.labels.md")
    assert labels_report(deals, labels) == committed
    assert "n = 12 of 12 deals" in committed
