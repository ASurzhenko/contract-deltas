"""Rule-based template suggestions. No model call; every suggestion cites deal ids."""

from dataclasses import dataclass
from fractions import Fraction

from contract_deltas import config
from contract_deltas.aggregate import Aggregate, TypeStats

WORDING = "Coincides with the outcomes below; this is a prototype signal on a handful of deals, not a causal claim."


@dataclass(frozen=True)
class Suggestion:
    rule: str
    clause_type: str
    deal_ids: tuple[str, ...]
    text: str


def _label(clause_type: str) -> str:
    return clause_type.replace("_", " ")


def _gap(stats: TypeStats) -> Fraction | None:
    if stats.win_rate_with is None or stats.win_rate_without is None:
        return None
    return stats.win_rate_with - stats.win_rate_without


def _enough_deals(stats: TypeStats) -> bool:
    return stats.n_with >= config.R2_MIN_DEALS_WITH and stats.n_without >= config.R2_MIN_DEALS_WITHOUT


def _days_gap(stats: TypeStats) -> Fraction | None:
    if stats.mean_days_with is None or stats.mean_days_without is None:
        return None
    return stats.mean_days_with - stats.mean_days_without


def _quotes(stats: TypeStats) -> str:
    if not stats.signed_excerpts:
        return ""
    shown = "; ".join(f'{deal_id}: "{text}"' for deal_id, text in stats.signed_excerpts[:3])
    return f" Signed wording: {shown}."


def suggest(aggregated: Aggregate) -> list[Suggestion]:
    suggestions: list[Suggestion] = []
    total = aggregated.n_used
    for clause, stats in aggregated.stats.items():
        changed = len(stats.changed)
        ids = tuple(stats.changed)
        name = _label(clause)

        buyer = stats.directions.get("buyer-favorable", 0)
        if changed * 2 > total and Fraction(buyer, changed) >= config.R1_MIN_BUYER_SHARE:
            suggestions.append(Suggestion(
                "R1", clause, ids,
                f"Common pushback: {name} was changed in {changed} of {total} deals, {buyer} of them in the "
                f"buyer's favor. Consider moving the template default toward the signed value.{_quotes(stats)}"))

        gap = _gap(stats)
        if _enough_deals(stats) and gap is not None and gap >= config.R2_MIN_WIN_RATE_GAP:
            suggestions.append(Suggestion(
                "R2", clause, ids,
                f"A change to {name} coincides with more wins: won {stats.won_with}/{stats.n_with} with it, "
                f"{stats.won_without}/{stats.n_without} without. Consider pre-approving this concession "
                "for the sales team."))

        days_gap = _days_gap(stats)
        if _enough_deals(stats) and gap is not None and (
                gap <= config.R3_MAX_WIN_RATE_GAP or (days_gap is not None and days_gap >= config.R3_MIN_EXTRA_DAYS)):
            suggestions.append(Suggestion(
                "R3", clause, ids,
                f"A change to {name} coincides with slower or lost deals: won {stats.won_with}/{stats.n_with} "
                f"with it, {stats.won_without}/{stats.n_without} without. Review this clause before it reaches "
                "the buyer; this flags a question, it is not a fix."))

        if len(stats.added_in) >= config.R4_MIN_DEALS_ADDED:
            suggestions.append(Suggestion(
                "R4", clause, tuple(stats.added_in),
                f"Buyers added a {name} clause in {len(stats.added_in)} deals. Consider adding it to the template."))
    return suggestions
