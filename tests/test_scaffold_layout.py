"""Verify the documented project skeleton exists.

This locks in the Milestone 0 deliverables: the multi-page website and the
documentation skeleton required by CLAUDE.md. If a required page or doc is
removed or renamed, these tests fail loudly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SITE_DIR = REPO_ROOT / "site"
DOCS_DIR = REPO_ROOT / "docs"

REQUIRED_SITE_PAGES = [
    "index.html",
    "architecture.html",
    "task-format.html",
    "sandboxing.html",
    "tracing-replay.html",
    "evals.html",
    "results.html",
    "security.html",
    "limitations.html",
    "roadmap.html",
]

REQUIRED_DOCS = [
    "PLAN.md",
    "ARCHITECTURE.md",
    "METHODOLOGY.md",
    "SECURITY_MODEL.md",
    "LIMITATIONS.md",
    "RESULTS.md",
    "REPRODUCIBILITY.md",
    "RESEARCH_QUESTIONS.md",
]


@pytest.mark.parametrize("page", REQUIRED_SITE_PAGES)
def test_required_site_page_exists_and_nonempty(page: str) -> None:
    path = SITE_DIR / page
    assert path.is_file(), f"missing required website page: site/{page}"
    assert path.stat().st_size > 0, f"empty website page: site/{page}"


@pytest.mark.parametrize("page", REQUIRED_SITE_PAGES)
def test_site_page_is_html_with_nav(page: str) -> None:
    text = (SITE_DIR / page).read_text(encoding="utf-8")
    assert "<!doctype html>" in text.lower(), f"site/{page} lacks a doctype"
    # Every page links back to the index so the site is navigable.
    assert "index.html" in text, f"site/{page} has no navigation to index.html"


@pytest.mark.parametrize("doc", REQUIRED_DOCS)
def test_required_doc_exists_and_nonempty(doc: str) -> None:
    path = DOCS_DIR / doc
    assert path.is_file(), f"missing required doc: docs/{doc}"
    assert path.stat().st_size > 0, f"empty doc: docs/{doc}"


def test_milestone_notes_present() -> None:
    for sub in ("milestones", "review_notes", "commits"):
        assert (DOCS_DIR / sub).is_dir(), f"missing docs/{sub}/ directory"
    # Milestone 0 artifacts specifically.
    assert (DOCS_DIR / "milestones" / "00-scaffold.md").is_file()
    assert (DOCS_DIR / "commits" / "00-scaffold.md").is_file()
    assert (DOCS_DIR / "review_notes" / "00-scaffold-human-review.md").is_file()
    # Milestone 1 artifacts.
    assert (DOCS_DIR / "milestones" / "01-environment-hygiene.md").is_file()
    assert (DOCS_DIR / "commits" / "01-environment-hygiene.md").is_file()
    assert (DOCS_DIR / "review_notes" / "01-environment-hygiene-human-review.md").is_file()
    # Milestone 2 artifacts.
    assert (DOCS_DIR / "milestones" / "02-task-format.md").is_file()
    assert (DOCS_DIR / "commits" / "02-task-format.md").is_file()
    assert (DOCS_DIR / "review_notes" / "02-task-format-human-review.md").is_file()
    # Milestone 3 artifacts.
    assert (DOCS_DIR / "milestones" / "03-tool-registry.md").is_file()
    assert (DOCS_DIR / "commits" / "03-tool-registry.md").is_file()
    assert (DOCS_DIR / "review_notes" / "03-tool-registry-human-review.md").is_file()
    # Milestone 4 artifacts.
    assert (DOCS_DIR / "milestones" / "04-runtime-loop.md").is_file()
    assert (DOCS_DIR / "commits" / "04-runtime-loop.md").is_file()
    assert (DOCS_DIR / "review_notes" / "04-runtime-loop-human-review.md").is_file()
