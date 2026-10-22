import logging
import re

import pytest

from contract_deltas import __main__ as cli
from contract_deltas import config
from contract_deltas.data import load_labels
from tests.conftest import FAKE_ARN, FAKE_ID, change_item, empty_response, tool_response

REPORT_FILES = ("eval.md", "report.md", "headline.md")
ARN_PREFIX = "arn" + ":aws"
ACCOUNT_ID = re.compile("(?<![0-9A-Za-z])[0-9]{" + "12" + "}(?![0-9A-Za-z])")


def argv(results_dir, *extra):
    return ["run", "--data-dir", str(config.DATA_DIR), "--results-dir", str(results_dir), *extra]


def perfect_response(deal_id):
    items = [change_item(l.clause_type, l.change, l.direction, sent_excerpt="", signed_excerpt="")
             for l in load_labels(config.DATA_DIR)[deal_id]]
    return tool_response(items)


def queue_perfect(stubber, deal_ids):
    for deal_id in deal_ids:
        stubber.add_response("converse", perfect_response(deal_id))


def snapshot(directory):
    return {p.relative_to(directory).as_posix(): p.read_bytes() for p in sorted(directory.rglob("*")) if p.is_file()}


def deal_ids():
    return [f"D{i:02d}" for i in range(1, 13)]


def test_full_run_writes_reports_and_prints_calls_made(stubbed, tmp_path, capsys):
    client, stubber = stubbed
    queue_perfect(stubber, deal_ids())

    code = cli.main(argv(tmp_path), client=client)

    out = capsys.readouterr().out
    assert code == 0
    assert "calls made: 12" in out and out.count("called, 1 attempts") == 12
    assert all((tmp_path / name).exists() for name in REPORT_FILES)
    headline = (tmp_path / "headline.md").read_text(encoding="utf-8")
    assert "F1 64/64 (1.000)" in headline and "rejected_output 0" in headline
    assert "Rules on this source versus hand labels" in (tmp_path / "report.md").read_text(encoding="utf-8")


def test_second_run_is_all_cache_hits_with_identical_bytes(stubbed, tmp_path, capsys):
    client, stubber = stubbed
    queue_perfect(stubber, deal_ids())
    cli.main(argv(tmp_path), client=client)
    capsys.readouterr()
    before = snapshot(tmp_path)

    code = cli.main(argv(tmp_path), client=client)

    out = capsys.readouterr().out
    assert code == 0 and out.count("cache hit") == 12 and "calls made: 0" in out
    assert snapshot(tmp_path) == before


def test_access_denied_on_deal_five_keeps_cache_and_old_reports_untouched(stubbed, tmp_path, capsys):
    client, stubber = stubbed
    old = {name: f"previous {name}\n".encode("utf-8") for name in REPORT_FILES}
    for name, content in old.items():
        (tmp_path / name).write_bytes(content)
    queue_perfect(stubber, deal_ids()[:4])
    stubber.add_client_error("converse", service_error_code="AccessDeniedException",
                             service_message=f"not allowed for {FAKE_ARN} in account {FAKE_ID}")

    code = cli.main(argv(tmp_path), client=client)

    captured = capsys.readouterr()
    assert code != 0
    for name, content in old.items():
        assert (tmp_path / name).read_bytes() == content
    raw = tmp_path / "raw" / config.slug(config.DEFAULT_MODEL_ID)
    assert sorted(p.stem for p in raw.glob("*.json")) == deal_ids()[:4]
    assert "no new report was produced" in captured.err
    assert "AccessDeniedException" in captured.err
    for stream in (captured.out, captured.err):
        assert ARN_PREFIX not in stream and not ACCOUNT_ID.search(stream)


def test_unexpected_exception_prints_only_its_class_name(tmp_path, capsys):
    class Broken:
        def converse(self, **kwargs):
            raise RuntimeError(f"boom {FAKE_ARN}")

    code = cli.main(argv(tmp_path), client=Broken())

    captured = capsys.readouterr()
    assert code != 0 and "RuntimeError" in captured.err
    for stream in (captured.out, captured.err):
        assert ARN_PREFIX not in stream and FAKE_ID not in stream
    assert not any((tmp_path / name).exists() for name in REPORT_FILES)


def test_labels_source_never_builds_a_client_and_writes_only_its_report(tmp_path, monkeypatch, capsys):
    class MustNotBeCalled:
        def converse(self, **kwargs):
            raise AssertionError("a model call was made")

    def no_client():
        raise AssertionError("a client was built")

    monkeypatch.setattr(cli, "make_client", no_client)

    code = cli.main(argv(tmp_path, "--source", "labels"), client=MustNotBeCalled())

    assert code == 0
    assert sorted(snapshot(tmp_path)) == ["report.labels.md"]
    assert (tmp_path / "report.labels.md").read_bytes() == (config.RESULTS_DIR / "report.labels.md").read_bytes()


def test_rejected_deal_is_counted_and_excluded_from_the_denominator(stubbed, tmp_path):
    client, stubber = stubbed
    stubber.add_response("converse", empty_response("content_filtered"))
    queue_perfect(stubber, deal_ids()[1:])

    code = cli.main(argv(tmp_path), client=client)

    assert code == 0
    assert "rejected_output 1" in (tmp_path / "headline.md").read_text(encoding="utf-8")
    assert "n = 11 of 12 deals" in (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "rejected_output 1" in (tmp_path / "eval.md").read_text(encoding="utf-8").splitlines()[2]


def test_logs_and_output_carry_no_credential_field_names(stubbed, tmp_path, caplog, capsys):
    client, stubber = stubbed
    queue_perfect(stubber, deal_ids())

    with caplog.at_level(logging.INFO):
        cli.main(argv(tmp_path), client=client)

    captured = capsys.readouterr()
    text = (caplog.text + captured.out + captured.err).lower()
    for fragment in ("aws_" + "access", "aws_" + "secret", "session" + "_token", "credential"):
        assert fragment not in text


@pytest.mark.parametrize("flag", ["--refresh", "--refresh-rejected"])
def test_refresh_flags_are_accepted(stubbed, tmp_path, flag):
    client, stubber = stubbed
    queue_perfect(stubber, deal_ids())
    cli.main(argv(tmp_path), client=client)
    if flag == "--refresh":
        queue_perfect(stubber, deal_ids())

    assert cli.main(argv(tmp_path, flag), client=client) == 0
