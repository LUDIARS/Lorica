"""Shared paths and helpers for the analyser tests (standard library only)."""
import contextlib
import io
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(ROOT / "tools"))

import lorica_analyze  # noqa: E402,F401  (also makes lorica_analysis importable)
from lorica_analysis.complexity import analyse  # noqa: E402
from lorica_analysis.extract import analyse_text  # noqa: E402


def extract(name_or_text, path="snippet.cpp"):
    """SourceFile of a fixture name or of literal text."""
    fixture = FIXTURES / name_or_text
    if "\n" not in name_or_text and fixture.is_file():
        return analyse_text(name_or_text, fixture.read_text(encoding="utf-8"))
    return analyse_text(path, name_or_text)


def measured(source):
    """{function name: Metrics} (later definitions of a name win) and refused regions."""
    results, refused = analyse(source)
    return {f.name: m for f, m in results}, refused


def run_cli(*argv):
    """(exit status, standard output, standard error) of an in-process CLI run."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            status = lorica_analyze.main([str(a) for a in argv])
        except SystemExit as exit_:
            status = exit_.code
    return status, out.getvalue(), err.getvalue()
