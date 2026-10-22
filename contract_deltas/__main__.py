"""Command line entry point: `python -m contract_deltas run | check`."""

import argparse
import logging
import sys
from pathlib import Path

from contract_deltas import config, report
from contract_deltas.aggregate import aggregate
from contract_deltas.bedrock import InfrastructureError, ScrubFormatter, converse_tool, make_client, scrub
from contract_deltas.data import load_deals, load_labels
from contract_deltas.evaluate import evaluate
from contract_deltas.extract import REJECTED, extract_deal
from contract_deltas.io_utils import write_text
from contract_deltas.suggest import suggest


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="contract_deltas")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="extract, evaluate, aggregate, suggest, write reports")
    run.add_argument("--model-id", default=config.DEFAULT_MODEL_ID)
    run.add_argument("--refresh", action="store_true", help="call the model again for every deal")
    run.add_argument("--refresh-rejected", action="store_true",
                     help="call the model again only for deals whose cached outcome is rejected_output")
    run.add_argument("--source", choices=["predicted", "labels"], default="predicted",
                     help="labels: aggregate the hand labels only, no model call")
    run.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    run.add_argument("--results-dir", type=Path, default=config.RESULTS_DIR)

    check = commands.add_parser("check", help="one tiny Converse call to test access to the model")
    check.add_argument("--model-id", default=config.DEFAULT_MODEL_ID)
    return parser


def _say(text: str, stream=None) -> None:
    print(scrub(text), file=stream or sys.stdout)


def _check(client, model_id: str) -> int:
    response = converse_tool(
        client,
        modelId=model_id,
        messages=[{"role": "user", "content": [{"text": "Reply with the single word: ok"}]}],
        inferenceConfig={"maxTokens": 20, "temperature": config.TEMPERATURE},
    )
    usage = response.get("usage", {})
    _say(f"model: {model_id}")
    _say(f"stopReason: {response['stopReason']}")
    _say(f"tokens: input={usage.get('inputTokens')} output={usage.get('outputTokens')}")
    return 0


def _run_labels(args) -> int:
    deals = load_deals(args.data_dir)
    labels = load_labels(args.data_dir)
    write_text(args.results_dir / "report.labels.md", report.labels_report(deals, labels))
    _say("wrote report.labels.md from the hand labels (no model call)")
    return 0


def _run_predicted(args, client) -> int:
    deals = load_deals(args.data_dir)
    labels = load_labels(args.data_dir)
    client = client or make_client()

    extractions = {}
    calls_made = 0
    for deal in deals:
        extraction = extract_deal(client, deal, args.model_id, args.results_dir,
                                  refresh=args.refresh, refresh_rejected=args.refresh_rejected)
        extractions[deal.deal_id] = extraction
        calls_made += extraction.calls_made
        if extraction.outcome == REJECTED:
            _say(f"{deal.deal_id}: rejected_output: {extraction.reason}")
        elif extraction.from_cache:
            _say(f"{deal.deal_id}: cache hit")
        else:
            _say(f"{deal.deal_id}: called, {extraction.attempts} attempts")

    # Reports are rendered and written only after every deal finished.
    evaluation = evaluate(deals, labels, extractions)
    rejected = [d for d, e in extractions.items() if e.outcome == REJECTED]
    predicted_changes = {d: e.changes for d, e in extractions.items()}
    from_predictions = aggregate(deals, predicted_changes, excluded=rejected)
    from_labels = aggregate(deals, labels)
    predicted_rules, label_rules = suggest(from_predictions), suggest(from_labels)

    write_text(args.results_dir / "eval.md", report.eval_md(args.model_id, evaluation, extractions))
    write_text(args.results_dir / "report.md", report.report_md(
        "Report from model predictions", from_predictions, predicted_rules, ("hand labels", label_rules)))
    write_text(args.results_dir / "headline.md", report.headline_md(args.model_id, evaluation, extractions))

    usage = report.total_usage(extractions)
    _say(f"tokens: input={usage['inputTokens']} output={usage['outputTokens']}")
    _say(f"calls made: {calls_made}")
    return 0


_log_handler: logging.Handler | None = None


def _configure_logging() -> None:
    """INFO to stderr through the scrubbing formatter; one handler even if main() runs several times."""
    global _log_handler
    root = logging.getLogger()
    if _log_handler is not None:
        root.removeHandler(_log_handler)
    _log_handler = logging.StreamHandler(sys.stderr)
    _log_handler.setFormatter(ScrubFormatter("%(message)s"))
    root.addHandler(_log_handler)
    root.setLevel(logging.INFO)
    for noisy in ("botocore", "boto3", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def main(argv: list[str], client=None) -> int:
    _configure_logging()
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "check":
            return _check(client or make_client(), args.model_id)
        if args.source == "labels":
            return _run_labels(args)
        return _run_predicted(args, client)
    except InfrastructureError as error:
        _say(f"{error.kind}: {error.code}", sys.stderr)
    except Exception as error:  # noqa: BLE001 - one top-level handler, prints the class name only
        _say(f"{type(error).__name__}: unexpected error", sys.stderr)
    if args.command == "run":
        _say("no new report was produced; rerun to resume from the cache", sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
