# Commit note — Milestone 13

**Commit message:** `Polish multi-page project website`

## What this commit adds

- **`site/style.css`** (additive): `figure.diagram` + `figcaption`; `.d-*` SVG
  primitive classes (boxes, edges, fills, arrowheads) themed via the existing CSS
  custom properties; a `nav.toc` "on this page" block (two-column, collapses to one
  on narrow screens). No existing rule modified.
- **Inline-SVG diagrams** (self-contained, `role="img"` + `<title>`/`<desc>` +
  `<figcaption>`):
  - runtime **pipeline** diagram on `site/index.html` and `site/architecture.html`
    (replaces the ASCII `<pre>`);
  - **sandbox gate** diagram on `site/sandboxing.html`.
- **`site/architecture.html`**: status badge corrected (M11 → M2–12); an "On this
  page" TOC with `id`-anchored headings; new **Regression & flakiness (M9)** and
  **Reproducible case study (M12)** sections; implementation-status list extended
  (M12 done, M13 in progress); relevant-files list updated (`reports/csv.py`,
  `tasks/`+`examples/`, `test_case_study.py`, `test_site_quality.py`,
  `scripts/07_case_study.py`); **test/result status rewritten** from the stale
  M4-only paragraph to the full suite; M9 limitation tense fixed.
- **`site/limitations.html`**: badge + brief-explanation "Milestone 11" → 12;
  **"Six tasks" → 13 across five categories**; "nothing beyond Milestone 11 is
  claimed" → 12; case study added to the capability list.
- **`site/results.html`**: new "Deeper technical explanation" section (the six-
  section contract; deterministic verdicts vs machine-dependent runtime; the
  committed-CSV drift guard).
- **`site/index.html` / `site/roadmap.html`**: M13 marked **in progress**, "next"
  advanced to Milestone 14.
- **`docs/LIMITATIONS.md`**: the one mirrored "as of Milestone 11" status line → 12.
- **`src/code_agent_runtime/cli.py`**: `CURRENT_MILESTONE` 12→13, `NEXT_MILESTONE`
  13→14 (the `info` status line).
- **Tests**: `tests/test_site_quality.py` (new); `tests/test_scaffold_layout.py`
  extended for the Milestone 13 notes.
- **Docs**: Milestone 13 milestone/commit/review notes.

## Excluded (per operating principles)

No secrets, API keys, virtualenvs, caches, `node_modules`, weights, or large
artifacts. The website remains fully **self-contained and offline**: no external
CSS/JS/fonts, no raster images — diagrams are inline SVG styled by the shared
stylesheet. A test (`test_page_is_self_contained`) forbids any `http(s)://` asset
reference, so the offline guarantee is enforced.

## Honesty notes

This milestone is presentation and consistency only — **no runtime/scoring/
sandbox/tracing/importer behaviour changed**. The only non-website code change is
the `info` command's two milestone-status strings. Per-feature status badges still
name the milestone each feature *landed* in (intentional); only genuinely stale
claims were corrected, and nothing beyond Milestone 12 is claimed as implemented.
The new test checks page **structure** (sections, links, self-containment, titled
diagrams), not prose accuracy or SVG rendering — content correctness still relies
on review.

## Verification at commit time

- `python3 -m pytest -q` passes (full CPU-only suite; `tests/test_site_quality.py`
  added). No model, key, or network.
- `python3 -m pytest tests/test_site_quality.py tests/test_scaffold_layout.py -q`
  passes.
- `PYTHONPATH=src python3 -m code_agent_runtime info` prints the Milestone 13 status.
- `python3 scripts/04_check_repo_hygiene.py` reports a clean repository.
