"""Website-quality checks locked in by Milestone 13 (multi-page website polish).

CLAUDE.md requires every site page to carry six standard sections, to be
navigable, and to be self-contained (no external assets). These tests turn that
requirement into something the suite enforces, so the polish cannot silently
regress as later milestones edit pages.

CPU-only, offline, dependency-free: the tests read the static HTML in ``site/``.
"""

from __future__ import annotations

import re
from html import unescape
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SITE_DIR = REPO_ROOT / "site"

# The same canonical page set the scaffold-layout test pins.
REQUIRED_PAGES = [
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

# Each page must contain an <h2> whose text includes each of these phrases
# (case-insensitive). This is the six-section contract from CLAUDE.md:
# brief explanation, deeper technical explanation, implementation status,
# relevant files, test/result status, and limitations.
REQUIRED_SECTION_PHRASES = [
    "brief explanation",
    "deeper technical explanation",
    "current implementation status",
    "relevant files",
    "current test/result status",
    "open questions",
]

# Pages that should ship an inline-SVG diagram (added in Milestone 13).
DIAGRAM_PAGES = ["index.html", "architecture.html", "sandboxing.html"]


def _read(page: str) -> str:
    return (SITE_DIR / page).read_text(encoding="utf-8")


def _h2_texts(html: str) -> list[str]:
    """Return the plain text of every <h2> on the page, lower-cased."""
    out: list[str] = []
    for raw in re.findall(r"<h2[^>]*>(.*?)</h2>", html, flags=re.S):
        text = unescape(re.sub(r"<[^>]+>", "", raw)).strip().lower()
        out.append(text)
    return out


@pytest.mark.parametrize("page", REQUIRED_PAGES)
@pytest.mark.parametrize("phrase", REQUIRED_SECTION_PHRASES)
def test_page_has_required_section(page: str, phrase: str) -> None:
    headings = _h2_texts(_read(page))
    assert any(phrase in h for h in headings), (
        f"site/{page} has no <h2> section containing {phrase!r}; "
        f"found headings: {headings}"
    )


@pytest.mark.parametrize("page", REQUIRED_PAGES)
def test_page_is_self_contained(page: str) -> None:
    """No external CSS/JS/font: the site is local-first and offline."""
    html = _read(page)
    assert 'href="style.css"' in html, f"site/{page} does not link the shared stylesheet"
    assert "<title>" in html, f"site/{page} has no <title>"
    assert '<footer class="site"' in html, f"site/{page} has no site footer"
    # Exactly one top-level heading.
    assert html.count("<h1>") == 1, f"site/{page} should have exactly one <h1>"
    # No off-site asset references (http/https or protocol-relative //).
    assert not re.search(r'(?:src|href)="https?://', html), (
        f"site/{page} references an external URL; the site must be self-contained"
    )


@pytest.mark.parametrize("page", REQUIRED_PAGES)
def test_page_navigates_to_every_page(page: str) -> None:
    """Every page's nav must link to all ten canonical pages."""
    html = _read(page)
    for target in REQUIRED_PAGES:
        assert f'href="{target}"' in html, (
            f"site/{page} is missing a navigation link to {target}"
        )


@pytest.mark.parametrize("page", REQUIRED_PAGES)
def test_internal_html_links_resolve(page: str) -> None:
    """Every internal *.html link points at a file that exists in site/."""
    html = _read(page)
    for href in re.findall(r'href="([^"]+)"', html):
        target = href.split("#", 1)[0]  # drop in-page anchors
        if not target or not target.endswith(".html"):
            continue
        assert (SITE_DIR / target).is_file(), (
            f"site/{page} links to {href!r}, which does not exist in site/"
        )


@pytest.mark.parametrize("page", DIAGRAM_PAGES)
def test_diagram_pages_have_accessible_inline_svg(page: str) -> None:
    """Diagram pages carry a self-contained, titled inline SVG figure."""
    html = _read(page)
    assert '<figure class="diagram">' in html, f"site/{page} has no diagram figure"
    assert "<svg" in html, f"site/{page} diagram has no inline <svg>"
    # Accessible: the SVG declares a title (referenced via aria-labelledby).
    assert "<title" in html, f"site/{page} inline SVG has no <title> for accessibility"
    assert "<figcaption>" in html, f"site/{page} diagram has no caption"
