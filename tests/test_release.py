"""Final-hardening / release-readiness checks (Milestone 14).

Two kinds of test:

- **integration**: the real repository passes every *required* release check
  (and the optional lint/tests checks stay skipped by default);
- **teeth**: each check is given a deliberately broken minimal fixture and must
  flip to *fail*. A consistency check that can never fail is worthless, so these
  prove every check actually detects the problem it claims to.

CPU-only, offline, dependency-free.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from code_agent_runtime import cli, hygiene, release

REPO_ROOT = Path(__file__).resolve().parents[1]


# -- integration: the real repo is releasable -------------------------------


def test_real_repo_passes_every_required_check() -> None:
    report = release.run_release_checks(REPO_ROOT)
    failed = [(c.name, c.problems) for c in report.required if not c.ok]
    assert report.ok(), f"required release checks failed: {failed}"


def test_optional_checks_are_skipped_by_default() -> None:
    report = release.run_release_checks(REPO_ROOT)
    optional = {c.name: c for c in report.optional}
    assert set(optional) == {"lint", "tests"}
    for name, check in optional.items():
        assert check.ok, f"{name} should be ok (skipped) by default"
        assert "skip" in check.detail.lower(), f"{name} default detail should say skipped"


def test_cli_release_check_passes_on_repo(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["release-check", "--root", str(REPO_ROOT), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert {c["name"] for c in payload["checks"]} >= {
        "source_compiles",
        "docs_consistency",
        "website_consistency",
        "readme_quality",
        "reproducibility",
    }


def test_cli_info_reports_milestone_14(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["info"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Milestone 14" in out


def test_report_is_json_serialisable_and_consistent() -> None:
    report = release.run_release_checks(REPO_ROOT)
    payload = report.to_dict()
    assert payload["ok"] is True
    names = [c["name"] for c in payload["checks"]]
    assert names[:4] == [
        "source_compiles",
        "hygiene_clean",
        "no_secrets",
        "no_large_artifacts",
    ]
    # Every required check carries a non-empty human detail string.
    assert all(c["detail"] for c in payload["checks"])


# -- teeth: source_compiles -------------------------------------------------


def test_source_compiles_passes_on_valid_module(tmp_path: Path) -> None:
    pkg = tmp_path / "src" / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "mod.py").write_text("x = 1\n", encoding="utf-8")
    check = release.check_source_compiles(tmp_path)
    assert check.ok and check.required


def test_source_compiles_detects_syntax_error(tmp_path: Path) -> None:
    pkg = tmp_path / "src" / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "broken.py").write_text("def f(:\n", encoding="utf-8")
    check = release.check_source_compiles(tmp_path)
    assert not check.ok
    assert any("broken.py" in p for p in check.problems)


# -- teeth: hygiene-derived checks (filesystem-walk on a non-git tmp dir) ----


def test_no_secrets_flags_a_planted_credential(tmp_path: Path) -> None:
    # A well-known public AWS *example* key — not a real secret, but it matches
    # the hygiene access-key pattern, which is exactly what we want to detect.
    # Built split so the literal never appears contiguously in this repo's source
    # (otherwise the repo self-scan would flag this very line).
    aws_body = "AKIA" + "IOSFODNN7EXAMPLE"  # contiguous only at runtime
    (tmp_path / "config.txt").write_text(f"aws_key = {aws_body}\n", encoding="utf-8")
    check = release.check_no_secrets(hygiene.scan_repo(tmp_path))
    assert not check.ok
    assert any("config.txt" in p for p in check.problems)


def test_no_secrets_passes_on_clean_tree(tmp_path: Path) -> None:
    (tmp_path / "readme.txt").write_text("nothing to see here\n", encoding="utf-8")
    report = hygiene.scan_repo(tmp_path)
    assert release.check_no_secrets(report).ok is True


def test_no_large_artifacts_flags_oversized_file(tmp_path: Path) -> None:
    (tmp_path / "big.txt").write_text("x" * 100, encoding="utf-8")
    report = hygiene.scan_repo(tmp_path, max_bytes=10)
    check = release.check_no_large_artifacts(report)
    assert not check.ok
    assert any("big.txt" in p for p in check.problems)


def test_no_large_artifacts_flags_model_weights(tmp_path: Path) -> None:
    (tmp_path / "model.safetensors").write_text("weights", encoding="utf-8")
    report = hygiene.scan_repo(tmp_path)
    assert release.check_no_large_artifacts(report).ok is False


# -- teeth: docs_consistency ------------------------------------------------


def _make_good_docs(root: Path, *, latest: int, cli_milestone: int) -> None:
    """Build a minimal docs/ tree plus a cli.py that passes docs_consistency."""
    docs = root / "docs"
    for sub in ("milestones", "commits", "review_notes"):
        (docs / sub).mkdir(parents=True, exist_ok=True)
    for name in release.REQUIRED_DOCS:
        (docs / name).write_text(f"# {name}\n", encoding="utf-8")
    for n in range(0, latest + 1):
        (docs / "milestones" / f"{n:02d}-m.md").write_text("note\n", encoding="utf-8")
        (docs / "commits" / f"{n:02d}-m.md").write_text("note\n", encoding="utf-8")
        (docs / "review_notes" / f"{n:02d}-m-human-review.md").write_text("note\n", encoding="utf-8")
    cli = root / "src" / "code_agent_runtime" / "cli.py"
    cli.parent.mkdir(parents=True, exist_ok=True)
    cli.write_text(
        f'CURRENT_MILESTONE = "Milestone {cli_milestone} — m"\n', encoding="utf-8"
    )


def test_docs_consistency_passes_on_good_tree(tmp_path: Path) -> None:
    _make_good_docs(tmp_path, latest=2, cli_milestone=2)
    assert release.check_docs_consistency(tmp_path).ok is True


def test_docs_consistency_flags_missing_required_doc(tmp_path: Path) -> None:
    _make_good_docs(tmp_path, latest=2, cli_milestone=2)
    (tmp_path / "docs" / "REPRODUCIBILITY.md").unlink()
    check = release.check_docs_consistency(tmp_path)
    assert not check.ok
    assert any("REPRODUCIBILITY.md" in p for p in check.problems)


def test_docs_consistency_flags_milestone_note_gap(tmp_path: Path) -> None:
    _make_good_docs(tmp_path, latest=2, cli_milestone=2)
    (tmp_path / "docs" / "commits" / "01-m.md").unlink()
    check = release.check_docs_consistency(tmp_path)
    assert not check.ok
    assert any("commit note for milestone 1" in p for p in check.problems)


def test_docs_consistency_flags_cli_milestone_mismatch(tmp_path: Path) -> None:
    _make_good_docs(tmp_path, latest=2, cli_milestone=5)
    check = release.check_docs_consistency(tmp_path)
    assert not check.ok
    assert any("CURRENT_MILESTONE" in p for p in check.problems)


# -- teeth: website_consistency ---------------------------------------------


def _page(nav_targets: list[str], *, extra: str = "") -> str:
    nav = "\n".join(f'<a href="{t}">x</a>' for t in nav_targets)
    return f"<!doctype html><html><body>{nav}{extra}</body></html>"


def _make_good_site(root: Path) -> Path:
    site = root / "site"
    site.mkdir(parents=True, exist_ok=True)
    targets = list(release.REQUIRED_SITE_PAGES)
    for page in release.REQUIRED_SITE_PAGES:
        (site / page).write_text(_page(targets), encoding="utf-8")
    return site


def test_website_consistency_passes_on_good_site(tmp_path: Path) -> None:
    _make_good_site(tmp_path)
    assert release.check_website_consistency(tmp_path).ok is True


def test_website_consistency_flags_external_url(tmp_path: Path) -> None:
    site = _make_good_site(tmp_path)
    targets = list(release.REQUIRED_SITE_PAGES)
    (site / "index.html").write_text(
        _page(targets, extra='<link href="https://cdn.example.com/x.css">'), encoding="utf-8"
    )
    check = release.check_website_consistency(tmp_path)
    assert not check.ok
    assert any("external URL" in p for p in check.problems)


def test_website_consistency_flags_missing_nav_link(tmp_path: Path) -> None:
    site = _make_good_site(tmp_path)
    # Drop one nav target from index.html.
    short = [t for t in release.REQUIRED_SITE_PAGES if t != "roadmap.html"]
    (site / "index.html").write_text(_page(short), encoding="utf-8")
    check = release.check_website_consistency(tmp_path)
    assert not check.ok
    assert any("roadmap.html" in p for p in check.problems)


# -- teeth: readme_quality --------------------------------------------------


def _good_readme_root(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "PLAN.md").write_text("# plan\n", encoding="utf-8")
    body = (
        "# Project\n\n"
        "## Quick start\n\nRun it.\n\n"
        "See [the plan](docs/PLAN.md).\n\n"
        "## License\n\nMIT.\n\n" + ("filler words to pad the length. " * 80)
    )
    (tmp_path / "README.md").write_text(body, encoding="utf-8")
    return tmp_path


def test_readme_quality_passes_on_good_readme(tmp_path: Path) -> None:
    root = _good_readme_root(tmp_path)
    assert release.check_readme_quality(root).ok is True


def test_readme_quality_flags_broken_link(tmp_path: Path) -> None:
    root = _good_readme_root(tmp_path)
    text = (root / "README.md").read_text(encoding="utf-8")
    text += "\nAlso see [missing](docs/DOES_NOT_EXIST.md).\n"
    (root / "README.md").write_text(text, encoding="utf-8")
    check = release.check_readme_quality(root)
    assert not check.ok
    assert any("DOES_NOT_EXIST.md" in p for p in check.problems)


def test_readme_quality_flags_short_readme(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# tiny\n", encoding="utf-8")
    check = release.check_readme_quality(tmp_path)
    assert not check.ok


# -- teeth: reproducibility -------------------------------------------------


def test_reproducibility_passes_on_good_doc(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir(parents=True)
    (tmp_path / "docs" / "REPRODUCIBILITY.md").write_text(
        "# Reproducibility\n\nRun `python3 -m pytest -q`.\n" + ("detail. " * 80),
        encoding="utf-8",
    )
    assert release.check_reproducibility(tmp_path).ok is True


def test_reproducibility_flags_missing_doc(tmp_path: Path) -> None:
    assert release.check_reproducibility(tmp_path).ok is False


def test_reproducibility_flags_doc_without_commands(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir(parents=True)
    (tmp_path / "docs" / "REPRODUCIBILITY.md").write_text(
        "# Reproducibility\n\n" + ("prose without any command. " * 40), encoding="utf-8"
    )
    check = release.check_reproducibility(tmp_path)
    assert not check.ok
    assert any("pytest" in p for p in check.problems)
