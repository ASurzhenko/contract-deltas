"""Evaluation of predicted changes against hand labels. Pure functions over plain dataclasses."""

import re
from dataclasses import dataclass, field
from fractions import Fraction

from contract_deltas.data import Deal, Label
from contract_deltas.extract import REJECTED, Extraction
from contract_deltas.schema import CLAUSE_TYPES, DIRECTIONS, Change


@dataclass
class Counts:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> Fraction:
        return Fraction(self.tp, self.tp + self.fp) if self.tp + self.fp else Fraction(0)

    @property
    def recall(self) -> Fraction:
        return Fraction(self.tp, self.tp + self.fn) if self.tp + self.fn else Fraction(0)

    @property
    def f1(self) -> Fraction:
        total = 2 * self.tp + self.fp + self.fn
        return Fraction(2 * self.tp, total) if total else Fraction(0)


@dataclass
class DealEval:
    deal_id: str
    outcome: str
    matched: list[tuple[Label, Change]] = field(default_factory=list)
    false_positives: list[Change] = field(default_factory=list)
    false_negatives: list[Label] = field(default_factory=list)


@dataclass
class Evaluation:
    deals: list[DealEval]
    primary: Counts
    strict: Counts
    per_type: dict[str, Counts]
    direction_correct: int
    direction_total: int
    direction_baseline: int
    confusion: dict[str, dict[str, int]]
    grounded: int
    grounding_checked: int
    accepted_deals: int
    rejected_deals: int


def normalise_text(text: str) -> str:
    """Whitespace, case, markdown emphasis markers and curly quotes are ignored when matching excerpts."""
    text = text.replace("\u2018", "'").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    text = re.sub(r"[*_`]", "", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def _expected_excerpts(change: Change) -> list[tuple[str, str]]:
    """(side, excerpt) pairs that must be non-empty and found in the document for this change kind."""
    if change.change == "modified":
        return [("sent", change.sent_excerpt), ("signed", change.signed_excerpt)]
    if change.change == "added":
        return [("signed", change.signed_excerpt)]
    return [("sent", change.sent_excerpt)]


def grounding(change: Change, deal: Deal) -> tuple[int, int]:
    """(grounded, checked) over the excerpts expected for this change. An empty expected excerpt is ungrounded."""
    documents = {"sent": normalise_text(deal.sent), "signed": normalise_text(deal.signed)}
    grounded = checked = 0
    for side, excerpt in _expected_excerpts(change):
        checked += 1
        needle = normalise_text(excerpt)
        if needle and needle in documents[side]:
            grounded += 1
    return grounded, checked


def evaluate(deals: list[Deal], labels: dict[str, list[Label]], extractions: dict[str, Extraction]) -> Evaluation:
    primary, strict = Counts(), Counts()
    per_type = {clause: Counts() for clause in CLAUSE_TYPES + ["other"]}
    confusion = {label: {pred: 0 for pred in DIRECTIONS} for label in DIRECTIONS}
    direction_correct = direction_total = direction_baseline = 0
    grounded = checked = accepted = rejected = 0
    results = []

    for deal in deals:
        extraction = extractions[deal.deal_id]
        result = DealEval(deal.deal_id, extraction.outcome)
        results.append(result)
        if extraction.outcome == REJECTED:
            rejected += 1
        else:
            accepted += 1

        predicted = {}
        for change in extraction.changes:
            g, c = grounding(change, deal)
            grounded, checked = grounded + g, checked + c
            if change.clause_type in CLAUSE_TYPES and change.clause_type not in predicted:
                predicted[change.clause_type] = change
            else:
                result.false_positives.append(change)

        labelled = {label.clause_type: label for label in labels[deal.deal_id]}
        for clause, label in labelled.items():
            change = predicted.pop(clause, None)
            if change is None:
                result.false_negatives.append(label)
                continue
            result.matched.append((label, change))
            primary.tp += 1
            per_type[clause].tp += 1
            if label.change == change.change:
                strict.tp += 1
            direction_total += 1
            direction_correct += label.direction == change.direction
            direction_baseline += label.direction == "buyer-favorable"
            confusion[label.direction][change.direction] += 1
        result.false_positives.extend(predicted.values())

        primary.fp += len(result.false_positives)
        primary.fn += len(result.false_negatives)
        for change in result.false_positives:
            per_type[change.clause_type if change.clause_type in per_type else "other"].fp += 1
        for label in result.false_negatives:
            per_type[label.clause_type].fn += 1

    total_predicted = primary.tp + primary.fp
    total_labelled = primary.tp + primary.fn
    strict.fp = total_predicted - strict.tp
    strict.fn = total_labelled - strict.tp
    return Evaluation(
        deals=results, primary=primary, strict=strict, per_type=per_type,
        direction_correct=direction_correct, direction_total=direction_total,
        direction_baseline=direction_baseline, confusion=confusion, grounded=grounded,
        grounding_checked=checked, accepted_deals=accepted, rejected_deals=rejected)
