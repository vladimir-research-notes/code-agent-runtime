Human review: Milestone 13 — Multi-page website polish

TL;DR
Makes the ten-page static website serious, navigable, and internally consistent,
and locks that in with a new test. Adds three self-contained inline-SVG diagrams
(runtime pipeline on index + architecture; sandbox gate on sandboxing), an "On this
page" TOC for the long architecture page, and the standard "Deeper technical
explanation" section to results.html (the only page missing it). Corrects genuinely
stale claims (architecture badge M11→M2–12 with new M9/M12 sections and a rewritten
test/result paragraph; limitations "Six tasks"→13 and "Milestone 11"→12). No
runtime/scoring/sandbox/tracing behaviour changed; the only non-website code change
is the `info` CLI's two milestone-status strings (12→13, 13→14). New
`tests/test_site_quality.py` plus the extended layout test; full suite passes.

What changed
- `site/style.css`: additive `figure.diagram`/`figcaption`, `.d-*` SVG primitive
  classes (themed via existing CSS variables), `nav.toc`. No existing rule changed.
- Inline-SVG diagrams: pipeline on `index.html` + `architecture.html` (replacing the
  ASCII `<pre>`); sandbox gate on `sandboxing.html`. Each is `role="img"` with
  `<title>`/`<desc>` (aria-labelledby) and a `<figcaption>`.
- `architecture.html`: status badge fixed; on-this-page TOC + `id` anchors; new
  "Regression & flakiness (M9)" and "Reproducible case study (M12)" sections;
  implementation-status list extended; relevant-files refreshed; test/result status
  rewritten from the stale Milestone-4 text to the full suite; M9 tense fixed.
- `limitations.html`: badge + brief-explanation M11→12; "Six tasks"→"13 across five
  categories"; "beyond Milestone 11"→12; case study added to the capability list.
- `results.html`: new "Deeper technical explanation" section.
- `index.html` / `roadmap.html`: M13 → in progress; next → Milestone 14.
- `docs/LIMITATIONS.md`: status line M11→12.
- `src/code_agent_runtime/cli.py`: `CURRENT_MILESTONE`/`NEXT_MILESTONE` bumped.
- Tests: `tests/test_site_quality.py` (new); `tests/test_scaffold_layout.py` extended.

What should be checked later
- Render the site in a browser. The diagrams are hand-laid SVG with absolute
  coordinates inside a `viewBox`; tests assert presence/accessibility but cannot
  confirm the boxes/arrows/labels look right or that long labels don't overflow
  their boxes at narrow widths. Spot-check `index`, `architecture`, `sandboxing` and
  the architecture TOC anchors (clicking each jumps to the right heading).
- The six-section contract. `test_site_quality.py` requires every required page to
  have an `<h2>` containing each of: brief explanation, deeper technical
  explanation, current implementation status, relevant files, current test/result
  status, open questions. Confirm that phrase set is the right encoding of CLAUDE.md's
  six required sections and that matching on `<h2>` text (not the TOC links) is the
  intended strictness.
- Self-contained guarantee. `test_page_is_self_contained` forbids `src=`/`href=`
  pointing at `http(s)://`. Confirm the site should stay fully offline (no CDN
  fonts/analytics) — this test will fail the moment an external URL is added.
- Stale-claim corrections. Confirm the factual fixes are right: the suite is 13
  tasks (not 6); architecture now claims Milestones 2–12 implemented; nothing beyond
  Milestone 12 is claimed anywhere. Grep suggestion below.
- Per-feature badges left as-is. task-format says "Milestone 2", sandboxing
  "Milestone 7", etc. — these name when a feature landed and were intentionally not
  homogenised. Confirm that's the desired convention rather than a single global
  "current milestone" badge on every page.
- CLI milestone constants. `info` now reports "Milestone 13 — Multi-page website
  polish" / next "Milestone 14 — Final hardening". Confirm bumping these as part of
  a website milestone matches the established pattern (M12's commit bumped 12/13).

Technical risks
- Very low. Changes are static HTML/CSS plus one new read-only test and two CLI
  string constants. No behavioural code path changed. The realistic failure modes
  are cosmetic (an SVG that looks off in some browser) or a future broken internal
  link / dropped section — the latter two are now caught by the test. The
  `test_internal_html_links_resolve` check only validates `*.html` targets and
  ignores `#anchors`, so a typo'd in-page anchor (e.g. a TOC `#id` with no matching
  heading) would not be caught — verify the architecture TOC anchors by hand.

Commands to verify
- `python3 -m pytest -q`
- `python3 -m pytest tests/test_site_quality.py tests/test_scaffold_layout.py -q`
- `PYTHONPATH=src python3 -m code_agent_runtime info`   (expect Milestone 13 status)
- `grep -rn "Milestone 11\|Six tasks\|six tasks" site/ docs/`   (expect no stale hits)
- Open `site/index.html`, `site/architecture.html`, `site/sandboxing.html` in a browser.
- `python3 scripts/04_check_repo_hygiene.py`

Human feedback
<!-- Human will fill this later. -->
