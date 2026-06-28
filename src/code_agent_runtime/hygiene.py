"""Repository hygiene scanner for Code Agent Runtime (Milestone 1).

The scanner is a guardrail for the project's "do not commit junk or secrets"
operating principle. It inspects the files that are actually under version
control and reports anything that should not be there:

- **secrets** — credential-shaped strings (API keys, private-key blocks, ...);
- **virtualenvs** — committed ``.venv`` / ``pyvenv.cfg`` trees;
- **caches** — ``__pycache__``, ``*.pyc``, pytest/mypy/ruff caches;
- **node_modules** — committed JS dependency trees;
- **large files** — files over a size threshold;
- **result blobs** — binary or oversized artifacts under ``results/``;
- **local Claude settings** — a committed ``.claude/settings.local.json``;
- **model weights** — ``*.safetensors`` / ``*.gguf`` / ``*.pt`` and friends.

Scope and honesty: by default the scanner inspects **git-tracked files only**
(``git ls-files``), because that is what hygiene is actually about — what is in
version control. Files that exist on disk but are gitignored (a local ``.venv``,
caches) are intentionally *not* flagged. Outside a git work tree it falls back to
a filesystem walk. Secret detection is heuristic and pattern-based: it catches
common credential shapes but is neither a guarantee nor a substitute for not
handling real secrets in the repo. False positives can be silenced with an
inline ``# hygiene: ignore`` comment on the offending line.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

#: Files larger than this are flagged as "large_file" (bytes).
DEFAULT_MAX_BYTES = 5 * 1024 * 1024
#: Files larger than this are not scanned for secrets (bytes); they are still
#: subject to the size/binary rules. Keeps the scan fast and bounded.
SECRET_SCAN_CAP = 1_500_000
#: Binary-or-oversized files under ``results/`` above this size are "result_blob".
RESULT_BLOB_MIN_BYTES = 256 * 1024
#: Inline marker that suppresses secret findings on a single line.
ALLOW_MARKER = "hygiene: ignore"

# Directory names that should never be committed, mapped to (category, severity).
DIR_RULES: dict[str, tuple[str, str, str]] = {
    "node_modules": ("node_modules", "warning", "committed node_modules directory"),
    "__pycache__": ("cache", "warning", "committed Python bytecode cache"),
    ".pytest_cache": ("cache", "warning", "committed pytest cache"),
    ".mypy_cache": ("cache", "warning", "committed mypy cache"),
    ".ruff_cache": ("cache", "warning", "committed ruff cache"),
    ".cache": ("cache", "warning", "committed cache directory"),
    ".venv": ("virtualenv", "error", "committed virtual environment"),
    "venv": ("virtualenv", "error", "committed virtual environment"),
}

#: Model-weight / large-artifact extensions (lowercase, with dot).
WEIGHT_EXT = {".pt", ".pth", ".onnx", ".gguf", ".safetensors", ".h5", ".ckpt", ".bin", ".pb"}
#: Archive / serialized-blob extensions.
BLOB_EXT = {
    ".zip", ".tar", ".tgz", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".npz", ".parquet", ".pkl", ".joblib",
}
#: Bytecode extensions handled at the file level (not just via __pycache__).
BYTECODE_EXT = {".pyc", ".pyo", ".pyd"}

# Secret patterns. Kept high-precision to limit false positives on a repo that
# legitimately *discusses* secrets. Each entry is (name, compiled regex).
_SECRET_SPECS: list[tuple[str, str]] = [
    ("aws_access_key_id", r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA)[0-9A-Z]{16}\b"),
    ("private_key_block", r"-----BEGIN[ A-Z0-9]*PRIVATE KEY-----"),
    ("anthropic_api_key", r"\bsk-ant-[A-Za-z0-9]{2,}-[A-Za-z0-9_-]{24,}"),
    ("openai_api_key", r"\bsk-(?:proj-)?[A-Za-z0-9]{32,}\b"),
    ("github_token", r"\bgh[posru]_[A-Za-z0-9]{36,}\b"),
    ("slack_token", r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    ("google_api_key", r"\bAIza[0-9A-Za-z_-]{35}\b"),
    (
        "generic_credential_assignment",
        r"(?i)(?:password|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token)"
        r"\s*[:=]\s*['\"]?(?P<value>[^\s'\"]{16,})['\"]?",
    ),
]
SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (name, re.compile(pattern)) for name, pattern in _SECRET_SPECS
]

# Values that look like placeholders rather than real credentials. Used to
# suppress the heuristic "generic_credential_assignment" rule.
_PLACEHOLDER = re.compile(
    r"(?i)^(?:x{3,}|y{3,}|your[-_ ]|example|changeme|placeholder|dummy|redacted|"
    r"none|null|true|false|test|fake|todo|sample|insert|\.\.\.|<.*>|\$\{?.*}?|"
    r"\*{3,}|0{6,}|abc123|secret|password)"
)


@dataclass(frozen=True)
class HygieneFinding:
    """A single hygiene problem discovered in a file or directory."""

    category: str
    severity: str  # "error" | "warning"
    path: str  # repo-relative, POSIX-style
    message: str
    line: int | None = None

    def render(self) -> str:
        loc = f"{self.path}:{self.line}" if self.line else self.path
        return f"[{self.severity:<7}] {self.category:<22} {loc}\n              {self.message}"


@dataclass(frozen=True)
class HygieneReport:
    """Result of scanning a repository."""

    root: str
    mode: str  # "git-tracked" | "filesystem-walk"
    scanned: int
    findings: list[HygieneFinding]

    @property
    def errors(self) -> list[HygieneFinding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> list[HygieneFinding]:
        return [f for f in self.findings if f.severity == "warning"]

    def ok(self, *, strict: bool = False) -> bool:
        """Clean enough to pass. ``strict`` also fails on warnings."""
        if self.errors:
            return False
        return not (strict and self.warnings)

    def to_dict(self) -> dict:
        return {
            "root": self.root,
            "mode": self.mode,
            "scanned": self.scanned,
            "errors": len(self.errors),
            "warnings": len(self.warnings),
            "findings": [asdict(f) for f in self.findings],
        }


def _git_tracked_files(root: Path, *, include_untracked: bool) -> list[str] | None:
    """Return repo-relative tracked file paths, or ``None`` if not a git repo."""
    args = ["git", "-C", str(root), "ls-files", "-z"]
    if include_untracked:
        # Also include files that are present but not yet committed and not ignored.
        args += ["--others", "--exclude-standard", "--cached"]
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return [p for p in result.stdout.split("\0") if p]


def _walk_files(root: Path) -> list[str]:
    """Filesystem fallback: every file under ``root`` except the ``.git`` dir."""
    import os

    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        if ".git" in dirnames:
            dirnames.remove(".git")
        rel_dir = Path(dirpath).relative_to(root)
        for name in filenames:
            rel = (rel_dir / name) if str(rel_dir) != "." else Path(name)
            out.append(rel.as_posix())
    return out


def _read_text(path: Path) -> str | None:
    """Read a file as text, or ``None`` if it is binary or too large to scan."""
    try:
        if path.stat().st_size > SECRET_SCAN_CAP:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data[:8192]:
        return None  # treat NUL-containing files as binary
    return data.decode("utf-8", errors="replace")


def _is_binary(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            return b"\x00" in fh.read(8192)
    except OSError:
        return False


def _scan_secrets(relpath: str, abspath: Path) -> Iterable[HygieneFinding]:
    text = _read_text(abspath)
    if text is None:
        return []
    findings: list[HygieneFinding] = []
    seen: set[str] = set()  # one finding per pattern per file
    for lineno, line in enumerate(text.splitlines(), start=1):
        if ALLOW_MARKER in line:
            continue
        for name, pattern in SECRET_PATTERNS:
            if name in seen:
                continue
            match = pattern.search(line)
            if not match:
                continue
            if name == "generic_credential_assignment":
                value = match.group("value")
                if _PLACEHOLDER.match(value) or "/" in value or value.count(".") >= 2:
                    continue  # path / version / placeholder, not a credential
            seen.add(name)
            findings.append(
                HygieneFinding(
                    category="secret",
                    severity="error",
                    path=relpath,
                    message=f"possible {name.replace('_', ' ')} detected",
                    line=lineno,
                )
            )
    return findings


def _classify(
    relpath: str,
    root: Path,
    *,
    max_bytes: int,
    seen_dirs: set[tuple[str, str]],
) -> list[HygieneFinding]:
    """Classify one repo-relative path into zero or more findings."""
    findings: list[HygieneFinding] = []
    parts = relpath.split("/")

    # 1) Directory-level junk (node_modules / caches / venvs). Reported once per
    #    offending directory, even when many files live inside it.
    for idx, part in enumerate(parts[:-1]):
        rule = DIR_RULES.get(part)
        if rule is None:
            continue
        category, severity, message = rule
        prefix = "/".join(parts[: idx + 1])
        key = (category, prefix)
        if key not in seen_dirs:
            seen_dirs.add(key)
            findings.append(
                HygieneFinding(category=category, severity=severity, path=prefix, message=message)
            )
        # Anything inside a junk directory needs no further per-file checks.
        return findings

    abspath = root / relpath
    name = parts[-1]
    suffix = Path(name).suffix.lower()
    try:
        size = abspath.stat().st_size
    except OSError:
        size = 0

    flagged: set[str] = set()

    def add(category: str, severity: str, message: str) -> None:
        flagged.add(category)
        findings.append(
            HygieneFinding(category=category, severity=severity, path=relpath, message=message)
        )

    # 2) Special filenames.
    if name == "pyvenv.cfg":
        add("virtualenv", "error", "committed virtual-environment marker (pyvenv.cfg)")
    if name == "settings.local.json" and ".claude" in parts[:-1]:
        add("local_claude_settings", "error", "committed local Claude settings (must stay local)")

    # 3) Extension-based rules.
    if suffix in BYTECODE_EXT:
        add("cache", "warning", "committed compiled Python bytecode")
    if suffix in WEIGHT_EXT:
        add("model_weights", "error", "committed model weights / large binary artifact")
    if suffix in BLOB_EXT:
        add("result_blob", "warning", "committed archive / serialized blob")

    # 4) Binary or oversized artifacts committed under results/.
    if parts[0] == "results" and "result_blob" not in flagged:
        if size > RESULT_BLOB_MIN_BYTES or _is_binary(abspath):
            add("result_blob", "warning", "binary or oversized artifact under results/")

    # 5) Generic large file (skip if already flagged as a heavy artifact).
    if size > max_bytes and not flagged & {"model_weights", "result_blob"}:
        add("large_file", "warning", f"large committed file ({size / 1_048_576:.1f} MiB)")

    # 6) Secret content scan (text files only).
    findings.extend(_scan_secrets(relpath, abspath))
    return findings


def scan_repo(
    root: str | Path = ".",
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    include_untracked: bool = False,
) -> HygieneReport:
    """Scan ``root`` for hygiene problems and return a structured report.

    Prefers git-tracked files; falls back to a filesystem walk when ``root`` is
    not a git work tree (or git is unavailable).
    """
    root = Path(root).resolve()
    tracked = _git_tracked_files(root, include_untracked=include_untracked)
    if tracked is not None:
        files, mode = tracked, "git-tracked"
    else:
        files, mode = _walk_files(root), "filesystem-walk"

    findings: list[HygieneFinding] = []
    seen_dirs: set[tuple[str, str]] = set()
    for relpath in files:
        findings.extend(_classify(relpath, root, max_bytes=max_bytes, seen_dirs=seen_dirs))

    # Stable ordering: errors before warnings, then by category and path.
    severity_rank = {"error": 0, "warning": 1}
    findings.sort(key=lambda f: (severity_rank.get(f.severity, 9), f.category, f.path, f.line or 0))
    return HygieneReport(root=str(root), mode=mode, scanned=len(files), findings=findings)


def format_report(report: HygieneReport) -> str:
    """Render a hygiene report as human-readable text."""
    lines = [
        "Repository hygiene scan — Code Agent Runtime",
        f"  root    : {report.root}",
        f"  mode    : {report.mode}",
        f"  scanned : {report.scanned} files",
        "",
    ]
    if not report.findings:
        lines.append("No hygiene problems found. Repository is clean.")
        return "\n".join(lines)
    for finding in report.findings:
        lines.append(finding.render())
    lines.append("")
    lines.append(f"Summary: {len(report.errors)} error(s), {len(report.warnings)} warning(s).")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the CLI subcommand and the ``scripts/`` wrapper.

    Returns ``0`` when the repository is clean (``1`` on errors, or on warnings
    when ``--strict`` is given).
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="code-agent-runtime hygiene",
        description="Scan tracked files for secrets, junk, and large/binary artifacts.",
    )
    parser.add_argument("--root", default=".", help="Repository root to scan (default: cwd).")
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_BYTES,
        help=f"Large-file threshold in bytes (default: {DEFAULT_MAX_BYTES}).",
    )
    parser.add_argument(
        "--include-untracked",
        action="store_true",
        help="Also scan untracked, non-gitignored files.",
    )
    parser.add_argument(
        "--strict", action="store_true", help="Treat warnings as failures too."
    )
    parser.add_argument("--json", action="store_true", help="Emit the report as JSON.")
    args = parser.parse_args(argv)

    report = scan_repo(
        args.root, max_bytes=args.max_bytes, include_untracked=args.include_untracked
    )
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(format_report(report))
    return 0 if report.ok(strict=args.strict) else 1


if __name__ == "__main__":  # pragma: no cover - exercised via scripts/ and __main__
    raise SystemExit(main())
