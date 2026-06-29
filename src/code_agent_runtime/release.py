"""Final-hardening / release-readiness checks for Code Agent Runtime (Milestone 14).

The runtime already ships single-purpose guardrails — the environment check
(Milestone 1), the hygiene scanner (Milestone 1), and the website-quality and
scaffold-layout tests (Milestone 13). This module is the *final hardening*
milestone's deliverable: one runnable gate that aggregates the project's "is this
repository in a releasable state" checks and reports them as a single structured
report, so the claim "the repo is consistent and clean" is enforced rather than
asserted.

The checks, mirroring the Milestone 14 plan, are:

- **source compiles** — every module under ``src/`` parses (a free, stdlib lint);
- **hygiene clean / no secrets / no large artifacts** — derived from a single
  :func:`code_agent_runtime.hygiene.scan_repo` pass;
- **docs consistency** — required docs exist, every milestone ``N`` has a
  milestone/commit/review note, and the CLI's reported milestone matches the
  latest note;
- **website consistency** — the ten required pages exist, each links the full
  navigation, references only existing internal pages, and is self-contained
  (no external assets);
- **README quality** — the README is substantial, has the expected sections, and
  its relative links resolve;
- **reproducibility** — ``docs/REPRODUCIBILITY.md`` exists and names the commands
  needed to reproduce a run.

Two further checks are *optional* (advisory): ``lint`` runs ``ruff`` when it is
installed, and ``tests`` runs the suite — both are off by default so the gate
stays fast, free, and offline, and neither fails the gate when its tool is
absent. Required checks gate the overall result; ``strict`` also fails on any
optional check that ran and failed.

Usable three ways, like the other operational checks:

- as a library: :func:`run_release_checks` returns a structured report;
- via the CLI: ``code-agent-runtime release-check``;
- as a script: ``python3 scripts/08_final_checks.py``.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from . import hygiene as _hygiene

#: The canonical documentation set (mirrors ``tests/test_scaffold_layout.py``).
REQUIRED_DOCS = (
    "PLAN.md",
    "ARCHITECTURE.md",
    "METHODOLOGY.md",
    "SECURITY_MODEL.md",
    "LIMITATIONS.md",
    "RESULTS.md",
    "REPRODUCIBILITY.md",
    "RESEARCH_QUESTIONS.md",
)

#: The canonical website pages (mirrors the scaffold-layout / site-quality tests).
REQUIRED_SITE_PAGES = (
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
)

#: Hygiene categories that count as a "large artifact" the repo must not commit.
LARGE_ARTIFACT_CATEGORIES = frozenset({"model_weights", "large_file", "result_blob"})


@dataclass(frozen=True)
class ReleaseCheck:
    """A single release-readiness check result.

    ``required`` checks gate the overall verdict; optional checks are advisory.
    ``problems`` carries the individual reasons a check failed (empty when ok).
    """

    name: str
    ok: bool
    required: bool
    detail: str
    problems: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "ok": self.ok,
            "required": self.required,
            "detail": self.detail,
            "problems": list(self.problems),
        }


@dataclass(frozen=True)
class ReleaseReport:
    """Aggregate of every release-readiness check."""

    root: str
    checks: list[ReleaseCheck] = field(default_factory=list)

    @property
    def required(self) -> list[ReleaseCheck]:
        return [c for c in self.checks if c.required]

    @property
    def optional(self) -> list[ReleaseCheck]:
        return [c for c in self.checks if not c.required]

    def ok(self, *, strict: bool = False) -> bool:
        """Releasable when every *required* check passed.

        ``strict`` additionally fails on any optional check that ran and failed
        (a skipped optional check reports ``ok=True`` and never gates).
        """
        if not all(c.ok for c in self.required):
            return False
        return not (strict and not all(c.ok for c in self.optional))

    def to_dict(self) -> dict:
        return {
            "root": self.root,
            "ok": self.ok(),
            "ok_strict": self.ok(strict=True),
            "checks": [c.to_dict() for c in self.checks],
        }


# -- individual checks ------------------------------------------------------


def check_source_compiles(root: Path) -> ReleaseCheck:
    """Every ``*.py`` under ``src/`` parses and byte-compiles.

    A free, dependency-free stand-in for "lint": it catches syntax errors
    without writing any ``.pyc`` to disk (it compiles in memory).
    """
    src = root / "src"
    problems: list[str] = []
    count = 0
    for path in sorted(src.rglob("*.py")):
        count += 1
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except (SyntaxError, ValueError) as exc:
            rel = path.relative_to(root).as_posix()
            problems.append(f"{rel}: {exc}")
    ok = not problems
    detail = (
        f"{count} module(s) under src/ compile"
        if ok
        else f"{len(problems)} of {count} module(s) failed to compile"
    )
    return ReleaseCheck("source_compiles", ok, True, detail, tuple(problems))


def check_hygiene_clean(report: _hygiene.HygieneReport) -> ReleaseCheck:
    """No error-severity hygiene findings (the overall commit-cleanliness gate)."""
    errors = report.errors
    ok = not errors
    detail = (
        f"{report.scanned} file(s) scanned; clean "
        f"({len(report.warnings)} warning(s))"
        if ok
        else f"{len(errors)} hygiene error(s) in {report.scanned} scanned file(s)"
    )
    problems = tuple(f"{f.category}: {f.path}" for f in errors)
    return ReleaseCheck("hygiene_clean", ok, True, detail, problems)


def check_no_secrets(report: _hygiene.HygieneReport) -> ReleaseCheck:
    """No credential-shaped strings in tracked files."""
    secrets = [f for f in report.findings if f.category == "secret"]
    ok = not secrets
    detail = "no secrets detected" if ok else f"{len(secrets)} possible secret(s) detected"
    problems = tuple(
        f"{f.path}:{f.line} {f.message}" if f.line else f"{f.path} {f.message}" for f in secrets
    )
    return ReleaseCheck("no_secrets", ok, True, detail, problems)


def check_no_large_artifacts(report: _hygiene.HygieneReport) -> ReleaseCheck:
    """No committed model weights, oversized files, or result blobs."""
    heavy = [f for f in report.findings if f.category in LARGE_ARTIFACT_CATEGORIES]
    ok = not heavy
    detail = "no large/binary artifacts committed" if ok else f"{len(heavy)} large artifact(s)"
    problems = tuple(f"{f.category}: {f.path}" for f in heavy)
    return ReleaseCheck("no_large_artifacts", ok, True, detail, problems)


def _milestone_indices(docs: Path) -> list[int]:
    """Milestone numbers discovered from ``docs/milestones/NN-*.md`` filenames."""
    out: list[int] = []
    milestones = docs / "milestones"
    if not milestones.is_dir():
        return out
    for path in milestones.glob("*.md"):
        m = re.match(r"(\d+)-", path.name)
        if m:
            out.append(int(m.group(1)))
    return sorted(set(out))


def _cli_milestone_number(root: Path) -> int | None:
    """The integer in the CLI's ``CURRENT_MILESTONE`` string, or ``None``."""
    cli = root / "src" / "code_agent_runtime" / "cli.py"
    try:
        text = cli.read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r'CURRENT_MILESTONE\s*=\s*"Milestone\s+(\d+)', text)
    return int(m.group(1)) if m else None


def check_docs_consistency(root: Path) -> ReleaseCheck:
    """Required docs exist; every milestone has its three notes; CLI status matches.

    For each milestone ``N`` from 0 to the latest, there must be a
    ``docs/milestones/NN-*.md``, a ``docs/commits/NN-*.md`` and a
    ``docs/review_notes/NN-*-human-review.md``. The CLI's reported milestone
    number must equal the latest milestone with notes.
    """
    docs = root / "docs"
    problems: list[str] = []

    for name in REQUIRED_DOCS:
        if not (docs / name).is_file():
            problems.append(f"missing required doc: docs/{name}")

    indices = _milestone_indices(docs)
    if not indices:
        problems.append("no milestone notes found under docs/milestones/")
        return ReleaseCheck("docs_consistency", False, True, "no milestone notes", tuple(problems))

    latest = indices[-1]
    for n in range(0, latest + 1):
        prefix = f"{n:02d}-"
        if not any((docs / "milestones").glob(f"{prefix}*.md")):
            problems.append(f"missing milestone note for milestone {n} (docs/milestones/{prefix}*.md)")
        if not any((docs / "commits").glob(f"{prefix}*.md")):
            problems.append(f"missing commit note for milestone {n} (docs/commits/{prefix}*.md)")
        if not any((docs / "review_notes").glob(f"{prefix}*-human-review.md")):
            problems.append(
                f"missing review note for milestone {n} "
                f"(docs/review_notes/{prefix}*-human-review.md)"
            )

    cli_n = _cli_milestone_number(root)
    if cli_n is None:
        problems.append("could not read CURRENT_MILESTONE from src/code_agent_runtime/cli.py")
    elif cli_n != latest:
        problems.append(
            f"CLI CURRENT_MILESTONE is {cli_n} but the latest milestone note is {latest}"
        )

    ok = not problems
    detail = (
        f"docs consistent through milestone {latest} ({len(REQUIRED_DOCS)} core docs)"
        if ok
        else f"{len(problems)} docs-consistency problem(s)"
    )
    return ReleaseCheck("docs_consistency", ok, True, detail, tuple(problems))


def check_website_consistency(root: Path) -> ReleaseCheck:
    """The ten pages exist, link the full nav, resolve internal links, are offline."""
    site = root / "site"
    problems: list[str] = []
    pages = set(REQUIRED_SITE_PAGES)
    for page in REQUIRED_SITE_PAGES:
        path = site / page
        if not path.is_file() or path.stat().st_size == 0:
            problems.append(f"missing or empty page: site/{page}")
            continue
        html = path.read_text(encoding="utf-8")
        for target in REQUIRED_SITE_PAGES:
            if f'href="{target}"' not in html:
                problems.append(f"site/{page} is missing a nav link to {target}")
        if re.search(r'(?:src|href)="https?://', html):
            problems.append(f"site/{page} references an external URL (not self-contained)")
        for href in re.findall(r'href="([^"]+)"', html):
            target = href.split("#", 1)[0]
            if target.endswith(".html") and target not in pages:
                if not (site / target).is_file():
                    problems.append(f"site/{page} links to missing page {target}")
    ok = not problems
    detail = (
        f"{len(REQUIRED_SITE_PAGES)} pages consistent (nav, links, self-contained)"
        if ok
        else f"{len(problems)} website-consistency problem(s)"
    )
    return ReleaseCheck("website_consistency", ok, True, detail, tuple(problems))


def check_readme_quality(root: Path) -> ReleaseCheck:
    """The README is substantial, has the expected sections, and its links resolve."""
    readme = root / "README.md"
    problems: list[str] = []
    if not readme.is_file():
        return ReleaseCheck("readme_quality", False, True, "no README.md", ("missing README.md",))
    text = readme.read_text(encoding="utf-8")

    if len(text) < 1500:
        problems.append(f"README is short ({len(text)} chars; expected >= 1500)")
    if not re.search(r"^#\s+\S", text, flags=re.M):
        problems.append("README has no top-level '# ' heading")
    lower = text.lower()
    if "quick start" not in lower and "quickstart" not in lower:
        problems.append("README has no 'Quick start' section")
    if "license" not in lower:
        problems.append("README does not mention a license")
    if "docs/plan.md" not in lower:
        problems.append("README does not link to docs/PLAN.md")

    for target in re.findall(r"\]\(([^)]+)\)", text):
        target = target.strip()
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        rel = target.split("#", 1)[0]
        if not rel:
            continue
        if not (root / rel).exists():
            problems.append(f"README links to missing path: {rel}")

    ok = not problems
    detail = f"README ok ({len(text)} chars)" if ok else f"{len(problems)} README problem(s)"
    return ReleaseCheck("readme_quality", ok, True, detail, tuple(problems))


def check_reproducibility(root: Path) -> ReleaseCheck:
    """``docs/REPRODUCIBILITY.md`` exists and names the commands to reproduce a run."""
    doc = root / "docs" / "REPRODUCIBILITY.md"
    problems: list[str] = []
    if not doc.is_file():
        return ReleaseCheck(
            "reproducibility", False, True, "no docs/REPRODUCIBILITY.md",
            ("missing docs/REPRODUCIBILITY.md",),
        )
    text = doc.read_text(encoding="utf-8")
    if len(text) < 500:
        problems.append(f"REPRODUCIBILITY.md is short ({len(text)} chars; expected >= 500)")
    lower = text.lower()
    if "pytest" not in lower:
        problems.append("REPRODUCIBILITY.md does not mention the test command (pytest)")
    if "python3" not in lower:
        problems.append("REPRODUCIBILITY.md does not mention python3")
    ok = not problems
    detail = "reproducibility instructions present" if ok else f"{len(problems)} problem(s)"
    return ReleaseCheck("reproducibility", ok, True, detail, tuple(problems))


def check_lint(root: Path, *, run: bool = False) -> ReleaseCheck:
    """Optional: run ``ruff check`` when requested and available (advisory)."""
    if not run:
        return ReleaseCheck("lint", True, False, "skipped (pass --with-lint to run ruff)")
    ruff = shutil.which("ruff")
    if ruff is None:
        return ReleaseCheck("lint", True, False, "ruff not installed; skipped (optional)")
    try:
        result = subprocess.run(
            [ruff, "check", str(root / "src")],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover - defensive
        return ReleaseCheck("lint", False, False, f"ruff failed to run: {exc}")
    ok = result.returncode == 0
    detail = "ruff check passed" if ok else "ruff reported findings"
    problems = () if ok else tuple(result.stdout.strip().splitlines()[:20])
    return ReleaseCheck("lint", ok, False, detail, problems)


def check_tests(root: Path, *, run: bool = False) -> ReleaseCheck:
    """Optional: run the CPU-only test suite when requested (advisory).

    Off by default so the gate stays fast; running the suite inside the gate is
    a convenience for ``scripts/08_final_checks.py --with-tests``, not something
    the library does implicitly (it would recurse if called from a test).
    """
    if not run:
        return ReleaseCheck(
            "tests", True, False, "skipped (run `python3 -m pytest -q`, or pass --with-tests)"
        )
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=600,
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover - defensive
        return ReleaseCheck("tests", False, False, f"pytest failed to run: {exc}")
    ok = result.returncode == 0
    tail = (result.stdout.strip().splitlines() or ["(no output)"])[-1]
    detail = f"pytest passed ({tail})" if ok else f"pytest failed ({tail})"
    problems = () if ok else tuple(result.stdout.strip().splitlines()[-10:])
    return ReleaseCheck("tests", ok, False, detail, problems)


def run_release_checks(
    root: str | Path = ".",
    *,
    run_tests: bool = False,
    run_lint: bool = False,
    max_bytes: int = _hygiene.DEFAULT_MAX_BYTES,
) -> ReleaseReport:
    """Run every release-readiness check and return a structured report.

    The hygiene scan runs once; its three derived checks (clean / no secrets /
    no large artifacts) share that single pass. ``run_tests`` / ``run_lint``
    enable the optional, slower checks (both off by default).
    """
    root = Path(root).resolve()
    hygiene_report = _hygiene.scan_repo(root, max_bytes=max_bytes)
    checks = [
        check_source_compiles(root),
        check_hygiene_clean(hygiene_report),
        check_no_secrets(hygiene_report),
        check_no_large_artifacts(hygiene_report),
        check_docs_consistency(root),
        check_website_consistency(root),
        check_readme_quality(root),
        check_reproducibility(root),
        check_lint(root, run=run_lint),
        check_tests(root, run=run_tests),
    ]
    return ReleaseReport(root=str(root), checks=checks)


def _marker(check: ReleaseCheck) -> str:
    if check.ok:
        return "ok"
    return "FAIL" if check.required else "warn"


def format_report(report: ReleaseReport) -> str:
    """Render a release report as aligned, human-readable text."""
    width = max((len(c.name) for c in report.checks), default=0)
    lines = ["Final-hardening checks — Code Agent Runtime", f"  root : {report.root}", ""]
    for check in report.checks:
        tag = "required" if check.required else "optional"
        lines.append(f"  [{_marker(check):>4}] {check.name:<{width}}  {check.detail}  ({tag})")
        for problem in check.problems:
            lines.append(f"           - {problem}")
    lines.append("")
    if report.ok():
        extra = "" if report.ok(strict=True) else " (an optional check failed; see warnings)"
        lines.append(f"Result: PASS — repository is in a releasable state.{extra}")
    else:
        failed = [c.name for c in report.required if not c.ok]
        lines.append(f"Result: FAIL — required check(s) did not pass: {', '.join(failed)}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the CLI subcommand and the ``scripts/`` wrapper.

    Returns ``0`` when every required check passes (``1`` otherwise, or when
    ``--strict`` is given and an optional check that ran failed).
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="code-agent-runtime release-check",
        description="Run the Milestone 14 final-hardening checks over the repository.",
    )
    parser.add_argument("--root", default=".", help="Repository root to check (default: cwd).")
    parser.add_argument(
        "--with-tests", action="store_true", help="Also run the CPU-only test suite (slow)."
    )
    parser.add_argument(
        "--with-lint", action="store_true", help="Also run `ruff check` if ruff is installed."
    )
    parser.add_argument(
        "--strict", action="store_true", help="Also fail if an optional check ran and failed."
    )
    parser.add_argument("--json", action="store_true", help="Emit the report as JSON.")
    args = parser.parse_args(argv)

    report = run_release_checks(args.root, run_tests=args.with_tests, run_lint=args.with_lint)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(format_report(report))
    return 0 if report.ok(strict=args.strict) else 1


if __name__ == "__main__":  # pragma: no cover - exercised via scripts/ and __main__
    raise SystemExit(main())
