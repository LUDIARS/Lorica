"""Text and JSON reports. @implements SPEC-LR-ANALYZE

Every report states the coverage: files, functions analysed, unparsed regions and
lines not analysed, so that a clean result on code the tool could not read is not
taken for a pass. Text lists findings (with the lines that contributed), suppressed
findings, unparsed regions and dropped preprocessor branches; --all adds a table of
every function. JSON (SCHEMA_VERSION) always holds everything.
"""
import json
from typing import List, NamedTuple, Optional

from .extract import Region
from .gate import Entry, Finding

SCHEMA_VERSION = 1


class Run(NamedTuple):
    command: str
    metrics: tuple              # metric names, in column order
    files: List[str]
    entries: List[Entry]
    unparsed: List[Region]
    not_analysed: List[Region]
    findings: List[Finding]
    improved: int
    errors: List[str]           # unreadable inputs
    result: str                 # "pass", "fail" or "incomplete"


def _lines(regions: List[Region]) -> int:
    return sum(r.end_line - r.line + 1 for r in regions)


def summary(run: Run) -> dict:
    return {"files": len(run.files), "functions": len(run.entries),
            "unparsed_regions": len(run.unparsed), "lines_not_analysed": _lines(run.not_analysed),
            "findings": sum(1 for f in run.findings if not f.suppressed),
            "suppressed": sum(1 for f in run.findings if f.suppressed),
            "improved": run.improved, "result": run.result}


def _describe(finding: Finding) -> str:
    where = "%s:%d %s" % (finding.file, finding.line, finding.function)
    if finding.metric == "suppression":
        return "%s: suppression without a reason" % where
    limit = "" if finding.limit is None else " > %d" % finding.limit
    if finding.baseline is not None:
        limit += " (baseline %d)" % finding.baseline
    return "%s: %s %d%s" % (where, finding.metric, finding.value, limit)


def _notes(entry: Optional[Entry], metric: str) -> List[str]:
    if entry is None:
        return []
    shown = {"cyclomatic": "cyclomatic", "cognitive": "cognitive", "nesting": "cognitive"}.get(metric)
    out = ["    line %d: +%d %s" % (n.line, n.amount, n.reason) for n in entry.notes if n.metric == shown]
    return out + (["    (%s)" % entry.label] if entry.label else [])


def text(run: Run, show_all: bool = False) -> str:
    s = summary(run)
    out = ["lorica-analyze %s: files %d, functions analysed %d, unparsed regions %d, "
           "lines not analysed %d" % (run.command, s["files"], s["functions"],
                                      s["unparsed_regions"], s["lines_not_analysed"])]
    out += ["error: " + e for e in run.errors]
    by_place = {(e.function.file, e.function.line, e.function.name): e for e in run.entries}
    for finding in run.findings:
        entry = by_place.get((finding.file, finding.line, finding.function))
        if finding.suppressed:
            out.append("suppressed %s: %s" % (_describe(finding), finding.suppressed))
        else:
            out.append("FAIL " + _describe(finding))
            out += _notes(entry, finding.metric)
    out += ["unparsed %s:%d-%d: %s" % (r.file, r.line, r.end_line, r.reason) for r in run.unparsed]
    out += ["not analysed %s:%d-%d: %s" % (r.file, r.line, r.end_line, r.reason) for r in run.not_analysed]
    if show_all:
        out.append("  ".join(run.metrics) + "  function")
        for e in run.entries:
            out.append("  ".join("%*d" % (len(m), e.metrics[m]) for m in run.metrics)
                       + "  %s:%d %s%s" % (e.function.file, e.function.line, e.function.name,
                                           " (%s)" % e.label if e.label else ""))
    if run.improved:
        out.append("improved on the baseline: %d values; --write-baseline records them" % run.improved)
    out.append("result: %s, findings %d, suppressed %d" % (run.result, s["findings"], s["suppressed"]))
    return "\n".join(out) + "\n"


def to_json(run: Run) -> str:
    def region(r: Region) -> dict:
        return {"file": r.file, "line": r.line, "end_line": r.end_line, "reason": r.reason}
    functions = [{
        "file": e.function.file, "name": e.function.name, "kind": e.function.kind,
        "line": e.function.line, "start_line": e.function.start_line,
        "end_line": e.function.end_line, "metrics": e.metrics, "label": e.label,
        "contributions": [{"line": n.line, "metric": n.metric, "amount": n.amount, "reason": n.reason}
                          for n in e.notes]} for e in run.entries]
    return json.dumps({
        "schema_version": SCHEMA_VERSION, "command": run.command, "summary": summary(run),
        "functions": functions, "findings": [f._asdict() for f in run.findings],
        "unparsed": [region(r) for r in run.unparsed],
        "not_analysed": [region(r) for r in run.not_analysed], "errors": run.errors,
    }, indent=1) + "\n"
