"""Aggregation of changes per clause type against deal outcomes. Pure functions."""

from collections import Counter
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Iterable, Mapping, Protocol

from contract_deltas.data import Deal
from contract_deltas.schema import CLAUSE_TYPES


class ChangeLike(Protocol):
    clause_type: str
    change: str
    direction: str


@dataclass
class TypeStats:
    clause_type: str
    changed: list[str] = field(default_factory=list)  # deal ids with a change of this type
    kinds: Counter = field(default_factory=Counter)
    directions: Counter = field(default_factory=Counter)
    added_in: list[str] = field(default_factory=list)
    signed_excerpts: list[tuple[str, str]] = field(default_factory=list)
    won_with: int = 0
    won_without: int = 0
    n_with: int = 0
    n_without: int = 0
    mean_days_with: Fraction | None = None
    mean_days_without: Fraction | None = None
    mean_amount_with: Fraction | None = None

    @property
    def win_rate_with(self) -> Fraction | None:
        return Fraction(self.won_with, self.n_with) if self.n_with else None

    @property
    def win_rate_without(self) -> Fraction | None:
        return Fraction(self.won_without, self.n_without) if self.n_without else None


@dataclass
class Aggregate:
    n_used: int
    n_total: int
    excluded: list[str]
    stats: dict[str, TypeStats]


def _mean(values: list[int]) -> Fraction | None:
    return Fraction(sum(values), len(values)) if values else None


def aggregate(deals: Iterable[Deal], changes_by_deal: Mapping[str, Iterable[ChangeLike]],
              excluded: Iterable[str] = ()) -> Aggregate:
    """`other` items never count. Excluded deals (rejected_output) are out of every denominator."""
    deals = list(deals)
    excluded_ids = set(excluded)
    used = [deal for deal in deals if deal.deal_id not in excluded_ids]
    stats = {clause: TypeStats(clause) for clause in CLAUSE_TYPES}

    per_deal = {}
    for deal in used:
        per_deal[deal.deal_id] = {c.clause_type: c for c in changes_by_deal.get(deal.deal_id, [])
                                  if c.clause_type in stats}

    for clause, entry in stats.items():
        with_deals = [d for d in used if clause in per_deal[d.deal_id]]
        without_deals = [d for d in used if clause not in per_deal[d.deal_id]]
        entry.changed = [d.deal_id for d in with_deals]
        for deal in with_deals:
            change = per_deal[deal.deal_id][clause]
            entry.kinds[change.change] += 1
            entry.directions[change.direction] += 1
            if change.change == "added":
                entry.added_in.append(deal.deal_id)
            excerpt = getattr(change, "signed_excerpt", "")
            if excerpt:
                entry.signed_excerpts.append((deal.deal_id, excerpt))
        entry.n_with, entry.n_without = len(with_deals), len(without_deals)
        entry.won_with = sum(d.outcome == "won" for d in with_deals)
        entry.won_without = sum(d.outcome == "won" for d in without_deals)
        entry.mean_days_with = _mean([d.days_to_close for d in with_deals])
        entry.mean_days_without = _mean([d.days_to_close for d in without_deals])
        entry.mean_amount_with = _mean([d.amount_usd for d in with_deals])

    return Aggregate(n_used=len(used), n_total=len(deals), excluded=sorted(excluded_ids), stats=stats)
