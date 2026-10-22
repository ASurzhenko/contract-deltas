"""Markdown rendering for eval.md, report.md, report.labels.md and headline.md. No timestamps, so output is
reproducible byte for byte from the same inputs."""

from fractions import Fraction

from contract_deltas import config
from contract_deltas.aggregate import Aggregate
from contract_deltas.evaluate import Counts, Evaluation
from contract_deltas.extract import REJECTED, Extraction
from contract_deltas.schema import CLAUSE_TYPES, DIRECTIONS
from contract_deltas.suggest import WORDING, Suggestion

HEADLINE_START = "<!-- headline:start -->"
HEADLINE_END = "<!-- headline:end -->"


def clean(text: str) -> str:
    """Model text: long dashes become '-', line breaks and pipes are flattened so tables stay intact."""
    text = text.replace("\u2014", "-").replace("\u2013", "-")
    return " ".join(text.replace("|", "/").split())


def frac(value: Fraction | None) -> str:
    if value is None:
        return "n/a"
    return f"{value.numerator}/{value.denominator} ({float(value):.3f})"


def ratio(numerator: int, denominator: int) -> str:
    return f"{numerator}/{denominator}"


def score(numerator: int, denominator: int) -> str:
    """Unreduced counts next to the decimal, so 32/32 is not shown as 1/1."""
    if not denominator:
        return f"{numerator}/{denominator} (n/a)"
    return f"{numerator}/{denominator} ({numerator / denominator:.3f})"


def precision(c: Counts) -> str:
    return score(c.tp, c.tp + c.fp)


def recall(c: Counts) -> str:
    return score(c.tp, c.tp + c.fn)


def f1(c: Counts) -> str:
    return score(2 * c.tp, 2 * c.tp + c.fp + c.fn)


def num(value: Fraction | None) -> str:
    return "n/a" if value is None else f"{float(value):.1f}"


def pp(value: Fraction | None) -> str:
    return "n/a" if value is None else f"{float(value) * 100:+.0f} pp"


def _counts_row(name: str, counts: Counts) -> str:
    return (f"| {name} | {counts.tp} | {counts.fp} | {counts.fn} | {precision(counts)} | "
            f"{recall(counts)} | {f1(counts)} |")


def total_usage(extractions: dict[str, Extraction]) -> dict:
    total = {"inputTokens": 0, "outputTokens": 0, "totalTokens": 0}
    for extraction in extractions.values():
        for key in total:
            total[key] += extraction.usage.get(key, 0)
    return total


def headline_md(model_id: str, evaluation: Evaluation, extractions: dict[str, Extraction]) -> str:
    usage = total_usage(extractions)
    stored_calls = sum(e.attempts for e in extractions.values())
    primary, strict = evaluation.primary, evaluation.strict
    lines = [
        f"- Model: `{model_id}`",
        f"- Deals: {len(evaluation.deals)} (accepted {evaluation.accepted_deals}, "
        f"rejected_output {evaluation.rejected_deals})",
        f"- Change detection, match on deal and clause type: precision {precision(primary)}, "
        f"recall {recall(primary)}, F1 {f1(primary)} "
        f"(TP {primary.tp}, FP {primary.fp}, FN {primary.fn})",
        f"- Strict, change kind must also match: F1 {f1(strict)} "
        f"(TP {strict.tp}, FP {strict.fp}, FN {strict.fn})",
        f"- Direction on matched changes: {ratio(evaluation.direction_correct, evaluation.direction_total)} correct; "
        f"always answering buyer-favorable on the same set: "
        f"{ratio(evaluation.direction_baseline, evaluation.direction_total)}",
        f"- Excerpts found in the documents: {ratio(evaluation.grounded, evaluation.grounding_checked)}",
        f"- Model calls stored in the raw cache: {stored_calls}",
        f"- Tokens: input {usage['inputTokens']}, output {usage['outputTokens']}, total {usage['totalTokens']}",
    ]
    return "\n".join(lines) + "\n"


def eval_md(model_id: str, evaluation: Evaluation, extractions: dict[str, Extraction]) -> str:
    rejected = [d.deal_id for d in evaluation.deals if d.outcome == REJECTED]
    out = ["# Evaluation", ""]
    out.append(f"Deals by outcome: accepted {evaluation.accepted_deals}, rejected_output {evaluation.rejected_deals}"
               + (f" ({', '.join(f'{i}: {clean(extractions[i].reason)}' for i in rejected)})." if rejected else "."))
    out += ["", f"Model: `{model_id}`. Labels come from the dataset spec, not from the model.", ""]

    out += ["## Change detection", "",
            "| Match rule | TP | FP | FN | Precision | Recall | F1 |", "|---|---|---|---|---|---|---|",
            _counts_row("deal + clause type", evaluation.primary),
            _counts_row("deal + clause type + change kind", evaluation.strict), ""]

    out += ["## Per clause type", "", "| Clause type | TP | FP | FN | Precision | Recall | F1 |",
            "|---|---|---|---|---|---|---|"]
    for clause, counts in evaluation.per_type.items():
        if counts.tp + counts.fp + counts.fn:
            out.append(_counts_row(clause, counts))
    out.append("")

    out += ["## Direction", "",
            f"Correct on matched changes: {ratio(evaluation.direction_correct, evaluation.direction_total)}. "
            f"Baseline, always answering buyer-favorable on the same matched set: "
            f"{ratio(evaluation.direction_baseline, evaluation.direction_total)}.", "",
            "| Label \\ predicted | " + " | ".join(DIRECTIONS) + " |", "|---|" + "---|" * len(DIRECTIONS)]
    for label in DIRECTIONS:
        out.append(f"| {label} | " + " | ".join(str(evaluation.confusion[label][p]) for p in DIRECTIONS) + " |")
    out += ["", "## Grounding", "",
            f"Excerpts found in the right document: {ratio(evaluation.grounded, evaluation.grounding_checked)}. "
            "An empty excerpt where one is expected counts as not found.", ""]

    out += ["## False positives", ""]
    fps = [(d.deal_id, c) for d in evaluation.deals for c in d.false_positives]
    if not fps:
        out.append("None.")
    for deal_id, change in fps:
        out.append(f"- {deal_id} `{change.clause_type}` {change.change} {change.direction}: {clean(change.summary)}"
                   f" Sent: \"{clean(change.sent_excerpt)}\" Signed: \"{clean(change.signed_excerpt)}\"")
    out += ["", "## False negatives", ""]
    fns = [(d.deal_id, label) for d in evaluation.deals for label in d.false_negatives]
    if not fns:
        out.append("None.")
    for deal_id, label in fns:
        out.append(f"- {deal_id} `{label.clause_type}` {label.change} {label.direction}")
    return "\n".join(out) + "\n"


def _rule_keys(suggestions: list[Suggestion]) -> set[tuple[str, str]]:
    return {(s.rule, s.clause_type) for s in suggestions}


def report_md(title: str, aggregated: Aggregate, suggestions: list[Suggestion],
              other_source: tuple[str, list[Suggestion]] | None = None) -> str:
    out = [f"# {title}", ""]
    out.append(f"n = {aggregated.n_used} of {aggregated.n_total} deals"
               + (f" (excluded, rejected_output: {', '.join(aggregated.excluded)})" if aggregated.excluded else "")
               + ".")
    out += ["", "Win rates are counts of won deals. Rule thresholds: "
            f"R1 more than half of deals changed and at least {config.R1_MIN_BUYER_SHARE} buyer-favorable; "
            f"R2 changed in at least {config.R2_MIN_DEALS_WITH} deals, unchanged in at least "
            f"{config.R2_MIN_DEALS_WITHOUT}, win-rate gap at least {pp(config.R2_MIN_WIN_RATE_GAP)}; "
            f"R3 same counts and gap at most {pp(config.R3_MAX_WIN_RATE_GAP)} or mean days at least "
            f"+{config.R3_MIN_EXTRA_DAYS}; R4 clause added in at least {config.R4_MIN_DEALS_ADDED} deals.", ""]

    out += [f"## Per clause type (n = {aggregated.n_used} of {aggregated.n_total} deals)", "",
            "| Clause type | Changed | Kinds | Directions | Won with change | Won without | Mean days with | "
            "Mean days without | Mean amount with (USD) |", "|---|---|---|---|---|---|---|---|---|"]
    for clause in CLAUSE_TYPES:
        s = aggregated.stats[clause]
        kinds = ", ".join(f"{k} {v}" for k, v in sorted(s.kinds.items())) or "-"
        directions = ", ".join(f"{k} {v}" for k, v in sorted(s.directions.items())) or "-"
        out.append(f"| {clause} | {ratio(len(s.changed), aggregated.n_used)} | {kinds} | {directions} | "
                   f"{ratio(s.won_with, s.n_with)} | {ratio(s.won_without, s.n_without)} | "
                   f"{num(s.mean_days_with)} | {num(s.mean_days_without)} | {num(s.mean_amount_with)} |")

    out += ["", "## Suggested template edits", "", WORDING, ""]
    if not suggestions:
        out.append("No rule fired.")
    for s in suggestions:
        out.append(f"- **{s.rule} {s.clause_type}** (deals: {', '.join(s.deal_ids)}): {s.text}")

    if other_source is not None:
        other_name, other_suggestions = other_source
        mine, theirs = _rule_keys(suggestions), _rule_keys(other_suggestions)
        out += ["", f"## Rules on this source versus {other_name}", "",
                "| Rule | Clause type | This source | " + other_name + " |", "|---|---|---|---|"]
        for rule, clause in sorted(mine | theirs):
            out.append(f"| {rule} | {clause} | {'fires' if (rule, clause) in mine else '-'} | "
                       f"{'fires' if (rule, clause) in theirs else '-'} |")
        if mine == theirs:
            out.append("")
            out.append("The same rules fire on both sources.")
    return "\n".join(out) + "\n"


def labels_report(deals, labels) -> str:
    """report.labels.md: aggregation and suggestions straight from the hand labels, no model involved."""
    from contract_deltas.aggregate import aggregate
    from contract_deltas.suggest import suggest

    aggregated = aggregate(deals, labels)
    return report_md("Report from hand labels", aggregated, suggest(aggregated))
