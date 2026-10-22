from dataclasses import replace

from contract_deltas import config
from contract_deltas.aggregate import aggregate
from contract_deltas.data import Label, load_deals, load_labels
from contract_deltas.suggest import suggest
from tests.conftest import make_deal


def fired(suggestions):
    return {(s.rule, s.clause_type) for s in suggestions}


def synthetic(n_with, won_with, n_without, won_without, days_with=50, days_without=50,
              clause="payment_terms", direction="buyer-favorable", kind="modified"):
    """n_with deals carry a change of `clause`; the rest do not. Outcomes and days are set per group."""
    deals, changes = [], {}
    for i in range(n_with):
        deal = replace(make_deal(f"W{i:02d}"), outcome="won" if i < won_with else "lost", days_to_close=days_with)
        deals.append(deal)
        changes[deal.deal_id] = [Label(clause, kind, direction)]
    for i in range(n_without):
        deal = replace(make_deal(f"N{i:02d}"), outcome="won" if i < won_without else "lost",
                       days_to_close=days_without)
        deals.append(deal)
        changes[deal.deal_id] = []
    return aggregate(deals, changes)


def test_over_labels_exactly_the_planted_rules_fire_and_each_cites_deals():
    result = suggest(aggregate(load_deals(config.DATA_DIR), load_labels(config.DATA_DIR)))

    assert fired(result) == {("R1", "payment_terms"), ("R2", "liability_cap"), ("R2", "data_processing"),
                             ("R3", "auto_renewal"), ("R4", "data_processing")}
    assert all(s.deal_ids for s in result)
    r4 = next(s for s in result if s.rule == "R4")
    assert len(r4.deal_ids) == 4


def test_r1_needs_strictly_more_than_half_of_the_deals():
    assert ("R1", "payment_terms") not in fired(suggest(synthetic(6, 3, 6, 3)))  # exactly half
    assert ("R1", "payment_terms") in fired(suggest(synthetic(7, 3, 5, 3)))


def test_r1_direction_mix_below_three_quarters_buyer_favorable_keeps_it_off():
    deals = [replace(make_deal(f"D{i}"), outcome="won") for i in range(8)]
    directions = ["buyer-favorable"] * 5 + ["neutral"] * 3  # 5/8 is below 3/4
    below = aggregate(deals, {d.deal_id: [Label("payment_terms", "modified", directions[i])]
                              for i, d in enumerate(deals)})
    assert ("R1", "payment_terms") not in fired(suggest(below))

    directions = ["buyer-favorable"] * 6 + ["neutral"] * 2  # exactly 3/4 fires
    exact = aggregate(deals, {d.deal_id: [Label("payment_terms", "modified", directions[i])]
                              for i, d in enumerate(deals)})
    assert ("R1", "payment_terms") in fired(suggest(exact))


def test_r2_fires_at_a_gap_of_exactly_thirty_points_where_floats_would_miss_it():
    # 7/10 vs 4/10: the float difference lands just below 0.3; the Fraction gap is exactly 3/10.
    assert 0.7 - 0.4 < 0.3
    assert ("R2", "liability_cap") in fired(suggest(synthetic(10, 7, 10, 4, clause="liability_cap")))
    assert ("R2", "liability_cap") not in fired(suggest(synthetic(10, 6, 10, 4, clause="liability_cap")))


def test_r2_needs_at_least_three_deals_on_each_side():
    assert ("R2", "liability_cap") not in fired(suggest(synthetic(2, 2, 10, 0, clause="liability_cap")))
    assert ("R2", "liability_cap") not in fired(suggest(synthetic(10, 10, 2, 0, clause="liability_cap")))


def test_r3_fires_at_minus_thirty_points_and_not_just_above_it():
    assert ("R3", "auto_renewal") in fired(suggest(synthetic(10, 4, 10, 7, clause="auto_renewal")))
    assert ("R3", "auto_renewal") not in fired(suggest(synthetic(10, 5, 10, 7, clause="auto_renewal")))


def test_r3_days_gap_boundary_at_twenty_days():
    assert ("R3", "sla") in fired(suggest(synthetic(5, 3, 5, 3, days_with=80, days_without=60, clause="sla")))
    assert ("R3", "sla") not in fired(suggest(synthetic(5, 3, 5, 3, days_with=79, days_without=60, clause="sla")))


def test_r4_needs_three_added_clauses():
    assert ("R4", "data_processing") in fired(
        suggest(synthetic(3, 3, 5, 3, clause="data_processing", kind="added")))
    assert ("R4", "data_processing") not in fired(
        suggest(synthetic(2, 2, 6, 3, clause="data_processing", kind="added")))


def test_no_rule_fires_on_an_empty_dataset_of_changes():
    assert suggest(synthetic(0, 0, 8, 4)) == []
