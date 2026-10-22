from fractions import Fraction

from contract_deltas.data import Label
from contract_deltas.evaluate import evaluate, grounding, normalise_text
from contract_deltas.extract import ACCEPTED, REJECTED, Extraction
from contract_deltas.schema import Change
from tests.conftest import make_deal


def label(clause, change="modified", direction="buyer-favorable"):
    return Label(clause, change, direction)


def pred(clause, change="modified", direction="buyer-favorable", sent="", signed=""):
    return Change(clause, change, direction, "summary", sent, signed)


def extraction(deal_id, changes, outcome=ACCEPTED):
    return Extraction(deal_id=deal_id, outcome=outcome, reason="", changes=changes, attempts=1,
                      usage={}, from_cache=False)


def scenario():
    """Seven deals, each exercising one case. Expected values below are worked out by hand."""
    ids = ["A", "B", "C", "D", "E", "F", "G"]
    deals = [make_deal(i) for i in ids]
    labels = {
        "A": [label("payment_terms")],
        "B": [label("liability_cap"), label("auto_renewal", "removed")],
        "C": [label("data_processing", "added")],
        "D": [label("governing_law", direction="neutral")],
        "E": [],
        "F": [label("price_discount"), label("sla", direction="seller-favorable")],
        "G": [label("termination")],
    }
    extractions = {
        "A": extraction("A", [pred("payment_terms")]),
        "B": extraction("B", [pred("liability_cap")]),
        "C": extraction("C", [pred("data_processing", "modified")]),
        "D": extraction("D", [pred("governing_law", direction="buyer-favorable")]),
        "E": extraction("E", [pred("warranty", direction="neutral"), pred("other", direction="neutral")]),
        "F": extraction("F", [], outcome=REJECTED),
        "G": extraction("G", []),
    }
    return deals, labels, extractions


def test_primary_and_strict_counts_and_scores_match_hand_computation():
    result = evaluate(*scenario())

    # TP: A payment_terms, B liability_cap, C data_processing, D governing_law
    # FP: E warranty, E other.  FN: B auto_renewal, F price_discount, F sla, G termination
    assert (result.primary.tp, result.primary.fp, result.primary.fn) == (4, 2, 4)
    assert result.primary.precision == Fraction(2, 3)
    assert result.primary.recall == Fraction(1, 2)
    assert result.primary.f1 == Fraction(4, 7)

    # strict: C has the wrong change kind, so TP = A, B, D
    assert (result.strict.tp, result.strict.fp, result.strict.fn) == (3, 3, 5)
    assert result.strict.f1 == Fraction(3, 7)


def test_direction_accuracy_baseline_and_confusion_on_the_same_tp_set():
    result = evaluate(*scenario())

    assert result.direction_total == 4
    assert result.direction_correct == 3  # D's direction is wrong
    # Labelled buyer-favorable among the four TPs: A, B, C. The missed seller label (F) is not in the TP set.
    assert result.direction_baseline == 3
    assert result.confusion["buyer-favorable"] == {"buyer-favorable": 3, "seller-favorable": 0, "neutral": 0}
    assert result.confusion["neutral"] == {"buyer-favorable": 1, "seller-favorable": 0, "neutral": 0}
    assert sum(sum(row.values()) for row in result.confusion.values()) == 4


def test_baseline_differs_from_the_overall_label_skew_when_a_seller_label_is_matched():
    deals = [make_deal("A"), make_deal("B")]
    labels = {"A": [label("sla", direction="seller-favorable")], "B": [label("payment_terms")]}
    extractions = {"A": extraction("A", [pred("sla", direction="seller-favorable")]),
                   "B": extraction("B", [pred("payment_terms")])}

    result = evaluate(deals, labels, extractions)

    assert (result.direction_correct, result.direction_total, result.direction_baseline) == (2, 2, 1)


def test_rejected_deal_contributes_all_labels_as_misses_and_is_counted():
    result = evaluate(*scenario())

    rejected = next(d for d in result.deals if d.deal_id == "F")
    assert [l.clause_type for l in rejected.false_negatives] == ["price_discount", "sla"]
    assert (result.accepted_deals, result.rejected_deals) == (6, 1)


def test_predicted_other_is_always_a_false_positive_and_listed():
    result = evaluate(*scenario())

    e = next(d for d in result.deals if d.deal_id == "E")
    assert sorted(c.clause_type for c in e.false_positives) == ["other", "warranty"]
    assert result.per_type["other"].fp == 1 and result.per_type["warranty"].fp == 1


def test_per_clause_counts():
    result = evaluate(*scenario())

    assert (result.per_type["auto_renewal"].tp, result.per_type["auto_renewal"].fn) == (0, 1)
    assert result.per_type["payment_terms"].f1 == Fraction(1)
    assert result.per_type["sla"].fn == 1


def test_perfect_and_all_missed_cases():
    deals = [make_deal("A")]
    labels = {"A": [label("payment_terms"), label("liability_cap")]}

    perfect = evaluate(deals, labels, {"A": extraction("A", [pred("payment_terms"), pred("liability_cap")])})
    assert perfect.primary.f1 == 1 and perfect.strict.f1 == 1

    missed = evaluate(deals, labels, {"A": extraction("A", [])})
    assert (missed.primary.tp, missed.primary.fn) == (0, 2)
    assert missed.primary.f1 == 0 and missed.primary.precision == 0


def test_grounding_normalises_emphasis_quotes_and_whitespace():
    deal = make_deal(sent="Customer\u2019s duty:  pay within thirty (30) days.\n", signed="Pay within 60 days.\n")
    change = pred("payment_terms", sent="**Customer's duty:** pay within thirty (30) days", signed="pay  within 60 days")

    assert grounding(change, deal) == (2, 2)
    assert normalise_text("  A\u201cB\u201d_c_ ") == 'a"b"c'


def test_grounding_empty_expected_side_is_ungrounded_not_a_trivial_match():
    deal = make_deal(sent="alpha", signed="beta")

    assert grounding(pred("payment_terms", sent="", signed="beta"), deal) == (1, 2)
    assert grounding(pred("payment_terms", sent="alpha", signed=""), deal) == (1, 2)


def test_grounding_checks_only_the_expected_side_per_change_kind():
    deal = make_deal(sent="alpha", signed="beta")

    added = pred("data_processing", "added", sent="not in the document", signed="beta")
    removed = pred("auto_renewal", "removed", sent="alpha", signed="not in the document")
    fabricated = pred("payment_terms", sent="alpha", signed="invented text")

    assert grounding(added, deal) == (1, 1)
    assert grounding(removed, deal) == (1, 1)
    assert grounding(fabricated, deal) == (1, 2)


def test_grounding_totals_are_aggregated_over_all_predictions():
    deals = [make_deal("A", sent="alpha", signed="beta")]
    labels = {"A": [label("payment_terms")]}
    result = evaluate(deals, labels, {"A": extraction("A", [pred("payment_terms", sent="alpha", signed="gamma")])})

    assert (result.grounded, result.grounding_checked) == (1, 2)
