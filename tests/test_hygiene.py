"""Repository hygiene: no secret-shaped strings, no long dashes, no absolute paths, README numbers pinned.

Every pattern is assembled from fragments, so this file does not contain the literals it scans for.
"""

import json
import re
from pathlib import Path

import pytest

from contract_deltas import extract
from contract_deltas.bedrock import scrub
from contract_deltas.report import HEADLINE_END, HEADLINE_START
from tests.conftest import FAKE_ARN, FAKE_ID

REPO = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache"}

SECRET_PATTERNS = {
    "access-key-id": re.compile(r"\b(AKIA|ASIA)" + r"[0-9A-Z]{16}\b"),
    "arn": re.compile("arn" + ":aws"),
    "secret-word": re.compile("(?i)aws_?" + "secret"),
    "account-id": re.compile(r"(?<![0-9A-Za-z])[0-9]{" + "12" + r"}(?![0-9A-Za-z])"),
}
LONG_DASHES = (chr(0x2014), chr(0x2013))
ABSOLUTE_PATHS = {
    "drive-letter": re.compile(r"\b[A-Za-z]:" + "[\\\\]"),
    "users-dir": re.compile("/" + "Users/"),
    "home-dir": re.compile("/" + "home/"),
}
GENERIC_PARENT_NAMES = {"tmp", "temp", "src", "repos", "code", "projects", "work", "dev", "home", "users"}


def text_files(root: Path):
    for path in sorted(root.rglob("*")):
        if path.is_file() and not (set(path.relative_to(root).parts) & SKIP_DIRS):
            try:
                yield path, path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue


def scan(text: str, patterns=SECRET_PATTERNS) -> list[str]:
    return [name for name, pattern in patterns.items() if pattern.search(text)]


def scanned_paths():
    for name in ("data", "results", "tests"):
        folder = REPO / name
        if folder.exists():
            yield from (p for p, _ in text_files(folder))
    for name in ("README.md", "DECISIONS.md"):
        if (REPO / name).exists():
            yield REPO / name


# ---- the scanner itself, driven in the refusing direction ------------------------------------------------

def test_scanner_catches_planted_values(tmp_path):
    planted = tmp_path / "planted.txt"
    planted.write_text(f"id {FAKE_ID} here", encoding="utf-8")
    assert scan(planted.read_text(encoding="utf-8")) == ["account-id"]
    assert "arn" in scan(FAKE_ARN)
    assert scan("AKIA" + "A" * 16) == ["access-key-id"]
    assert scan("aws_" + "secret" + "_access_key") == ["secret-word"]
    assert scan("AWS_" + "SECRET") == ["secret-word"]


def test_scanner_ignores_lookalikes():
    digest = "a" * 10 + FAKE_ID + "b" * 42  # 64 hex-like characters containing a 12-digit run
    assert len(digest) == 64 and scan(digest) == []
    assert scan("the plain word ASIA") == []
    assert scan("0.30000000000000004") == []


def test_scrub_removes_an_arn_and_an_account_id():
    cleaned = scrub(f"denied for {FAKE_ARN} in account {FAKE_ID}.")
    assert scan(cleaned) == [] and "[arn]" in cleaned and "[id]" in cleaned


# ---- the repository ---------------------------------------------------------------------------------------

def test_no_secret_shaped_strings_in_committed_artifacts():
    for path in scanned_paths():
        hits = scan(path.read_text(encoding="utf-8"))
        assert hits == [], (path.relative_to(REPO).as_posix(), hits)


def test_no_long_dashes_anywhere_in_the_repository():
    for path, text in text_files(REPO):
        assert not any(dash in text for dash in LONG_DASHES), path.relative_to(REPO).as_posix()


def test_no_absolute_paths_anywhere_in_the_repository():
    for path, text in text_files(REPO):
        assert scan(text, ABSOLUTE_PATHS) == [], path.relative_to(REPO).as_posix()


def test_parent_folder_name_does_not_appear_in_any_file():
    parent = REPO.parent.name
    if len(parent) < 5 or parent.lower() in GENERIC_PARENT_NAMES:
        pytest.skip("parent folder name is generic")
    for path, text in text_files(REPO):
        assert parent.lower() not in text.lower(), path.relative_to(REPO).as_posix()


def test_raw_files_contain_only_whitelisted_keys():
    for path in sorted((REPO / "results" / "raw").rglob("*.json")):
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert set(saved) == set(extract._FILE_KEYS), path.name
        for attempt in saved["attempts"]:
            assert set(attempt) == set(extract._ATTEMPT_KEYS), path.name
        assert "ResponseMetadata" not in path.read_text(encoding="utf-8")


def test_readme_headline_block_equals_results_headline():
    headline = REPO / "results" / "headline.md"
    readme = REPO / "README.md"
    if not headline.exists() or not readme.exists():
        pytest.skip("no headline.md or README.md yet")
    text = readme.read_text(encoding="utf-8")
    assert text.count(HEADLINE_START) == 1 and text.count(HEADLINE_END) == 1
    block = text.split(HEADLINE_START + "\n", 1)[1].split(HEADLINE_END, 1)[0]
    assert block == headline.read_text(encoding="utf-8")
