# Milestone 13 — Multi-page website polish

## Summary

The website existed and was detailed at every milestone, but it had drifted: two
pages still claimed "Milestone 11" / "Six tasks" after the case study expanded the
suite to 13, the architecture page's narrative skipped Milestones 9 and 12 and its
"test/result status" was frozen at the Milestone 4 runtime tests, and one page
(`results.html`) was missing the standard "Deeper technical explanation" section.
This milestone makes the site **serious, navigable, technically useful, and
internally consistent** — and locks that in with a test so it cannot silently
regress again.

No runtime, scoring, sandbox, tracing, or importer behaviour changed. The only
non-website code touched is the `info` CLI's milestone constants (12→13, 13→14)
and a new website-quality test.

## Plan requirements → where they live

The plan asks that **every page** carry six things — brief explanation, deeper
technical explanation, implementation status, relevant files, test/result status,
limitations — plus "diagrams where helpful."

| Requirement | Implementation |
| --- | --- |
| Brief explanation (every page) | present on all 10 pages (was already) |
| Deeper technical explanation (every page) | added to `results.html` (the only page lacking it); present elsewhere |
| Implementation status (every page) | present; refreshed on `architecture` / `limitations` |
| Relevant files (every page) | present; `architecture` updated (adds `csv.py`, case-study tasks, new tests) |
| Test/result status (every page) | present; `architecture` rewritten from the stale M4-only text to the full suite |
| Limitations (every page) | present; `architecture` M9 tense fixed; `limitations` staleness fixed |
| Diagrams where helpful | three self-contained inline-SVG diagrams (pipeline on `index` + `architecture`; sandbox gate on `sandboxing`) |
| Navigable | full 10-link nav on every page (was already) + an "On this page" TOC on the long `architecture` page |

## Deliverables

- **`site/style.css`** — additive only: `figure.diagram` / `figcaption`, a set of
  `.d-*` SVG primitive classes (themed via the existing CSS custom properties so
  diagrams match the palette), and a `nav.toc` "on this page" block. No existing
  rule changed.
- **Diagrams (inline SVG, no external assets):**
  - the **runtime pipeline** (Task → Workspace → Agent loop ⇄ Tools → Tests →
    Scoring → Report, with the opt-in trace recorder spanning underneath) on
    `index.html` and `architecture.html`, replacing the prior ASCII `<pre>`;
  - the **sandbox gate** (check_call *before* dispatch → allow/deny; redact_result
    *after*) on `sandboxing.html`.
  Each SVG is `role="img"` with a `<title>`/`<desc>` referenced by
  `aria-labelledby`, and a visible `<figcaption>`.
- **Consistency / currency fixes:**
  - `architecture.html`: status badge (M11 → M2–12); new **Regression &
    flakiness (M9)** and **Reproducible case study (M12)** sections to close the
    narrative gaps; implementation-status list extended (M12 done, M13 in
    progress); test/result status rewritten to describe the full suite; an "On
    this page" TOC with `id`-anchored headings.
  - `limitations.html`: badge and brief-explanation "Milestone 11" → 12; **"Six
    tasks" → 13 across five categories**; "nothing beyond Milestone 11 is claimed"
    → 12; case study added to the enumerated capability list.
  - `results.html`: new "Deeper technical explanation" section (deterministic
    verdicts vs machine-dependent runtime; the committed-CSV drift guard).
  - `index.html` / `roadmap.html`: M13 marked **in progress**, "next" advanced to
    M14.
  - `docs/LIMITATIONS.md`: the one mirrored "as of Milestone 11" status line → 12.
- **`src/code_agent_runtime/cli.py`** — `CURRENT_MILESTONE` 12→13,
  `NEXT_MILESTONE` 13→14 (the `info` command's honest status line).
- **Tests:**
  - `tests/test_site_quality.py` (new) — for every required page: all six
    standard `<h2>` sections, the shared stylesheet link, exactly one `<h1>`, a
    site footer, **no external URL**, a nav link to all ten pages, and every
    internal `*.html` link resolving to a real file; plus the three diagram pages
    carry a titled, captioned inline `<svg>`.
  - `tests/test_scaffold_layout.py` — extended for the Milestone 13 notes.

## Design notes / decisions

- **Diagrams are themed CSS, not baked color.** The SVGs reference `.d-*` classes
  defined in `style.css`, which resolve the site's CSS custom properties. So a
  future palette change flows into the diagrams, and the SVG markup stays compact.
  No raster assets, no web fonts, no JS — the site remains fully offline and
  self-contained (a test forbids `http(s)://` asset references).
- **Polish is enforced, not asserted.** The point of `test_site_quality.py` is that
  "every page has the six sections and is navigable" becomes a property the suite
  checks on every run, so later milestones editing pages can't quietly drop a
  section or break a link. It reads the static HTML only — no browser, no network.
- **The six-section contract drove one real content change.** `results.html`
  genuinely lacked a "Deeper technical explanation" heading; rather than rename an
  existing section to satisfy the test, a real one was written (how the numbers are
  produced; what is deterministic vs machine-dependent). Uniform structure, honest
  content.
- **Honesty preserved.** Per-feature status badges still name the milestone a
  feature *landed* in (task-format M2, sandboxing M7, …) — that is intentional and
  was left alone. Only genuinely stale claims were corrected, and nothing beyond
  Milestone 12 is claimed as implemented.

## Honest limitations (carried into docs)

- The website is static HTML/CSS with inline SVG; there is no build step, search,
  or client-side navigation, by design.
- `test_site_quality.py` checks **structure** (sections present, links resolve,
  self-contained, diagrams titled) — it does not validate prose accuracy or render
  the SVG. Content correctness still relies on review.
- The diagrams are schematic, not exhaustive: the pipeline elides the
  per-step gate/redact detail (shown instead on the sandbox page), and the sandbox
  gate diagram shows the common rule names, not the full policy.

## Validation

- `python3 -m pytest -q` — full CPU-only suite passes, including the new
  `tests/test_site_quality.py`. No model, no network, no key.
- `python3 -m pytest tests/test_site_quality.py tests/test_scaffold_layout.py -q`
  — website-structure and layout tests pass.
- `python3 scripts/04_check_repo_hygiene.py` — clean repository.

## Status

Complete. Next: Milestone 14 — Final hardening.
