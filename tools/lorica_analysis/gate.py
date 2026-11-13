"""Assertion-style gate: thresholds, baseline and suppressions. @implements SPEC-LR-ANALYZE

The gated metrics are those given a threshold, or all metrics when only a
baseline is given. A gated value v of a function fails when
  - the function is in the baseline with value b: v > b and (no threshold or v > threshold);
  - otherwise: a threshold t is given and v > t.
So an existing code base passes with its baseline and fails only when a function
gets worse in a gated metric, or a function absent from the baseline exceeds a
threshold.

Baseline keys are `path::qualified-name(parameter count)`, with `#2`, `#3` for
further overloads of the same arity in source order, and paths relative to the
baseline file's directory, so line edits and the working directory do not matter.

Suppression, in a comment on a line of the declaration head (from its first line to
the name): `// lorica-analyze: ignore(<check>[, <check>...]) <reason>`, where a check
is a metric name or the subcommand name. A suppression without a reason does not
suppress; it is reported as a finding of its own.
"""
import json
import os
import re
from typing import Dict, Iterable, List, NamedTuple, Optional, Tuple

from .extract import Function, SourceFile
from .sources import InputError

SCHEMA_VERSION = 1
_SUPPRESSION = re.compile(r"lorica-analyze:\s*ignore\(([^)]*)\)[ \t]*(.*?)\s*(?:\*/)?\s*$")


class Entry(NamedTuple):
    source: SourceFile
    function: Function
    metrics: Dict[str, int]
    notes: Tuple = ()       # per-increment notes for the report (complexity.Contribution)
    label: str = ""         # e.g. complexity.ALL_BRANCHES


class Finding(NamedTuple):
    file: str
    line: int
    function: str
    metric: str             # a metric name, or "suppression" for one without a reason
    value: int
    limit: Optional[int]    # threshold or baseline value that was exceeded
    baseline: Optional[int]
    suppressed: str         # the reason when suppressed, else ""


def suppressions(source: SourceFile, function: Function) -> Dict[str, str]:
    """{check: reason} from comments on the function's declaration head lines."""
    found = {}
    for comment in source.comments:
        if function.start_line <= comment.line <= function.line:
            match = _SUPPRESSION.search(comment.text)
            if match:
                for check in match.group(1).split(","):
                    found[check.strip()] = match.group(2)
    return found


def keys(entries: Iterable[Entry], root: str) -> List[str]:
    out, seen = [], {}
    for entry in entries:
        path = os.path.relpath(os.path.abspath(entry.function.file), root).replace(os.sep, "/")
        key = "%s::%s(%d)" % (path, entry.function.name, entry.function.parameters)
        seen[key] = seen.get(key, 0) + 1
        out.append(key if seen[key] == 1 else "%s#%d" % (key, seen[key]))
    return out


def load_baseline(path: str) -> Dict[str, Dict[str, int]]:
    try:
        with open(path, encoding="utf-8") as stream:
            data = json.load(stream)
        if data.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("schema_version %r is not %d" % (data.get("schema_version"), SCHEMA_VERSION))
        functions = data["functions"]
        if not all(isinstance(v, dict) and all(isinstance(n, int) for n in v.values())
                   for v in functions.values()):
            raise ValueError("functions must map keys to {metric: integer}")
        return functions
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        raise InputError("%s: not a usable baseline (%s)" % (path, error))


def write_baseline(path: str, command: str, entries: List[Entry]) -> None:
    root = os.path.dirname(os.path.abspath(path))
    functions = dict(zip(keys(entries, root), (e.metrics for e in entries)))
    with open(path, "w", encoding="utf-8") as stream:
        json.dump({"schema_version": SCHEMA_VERSION, "command": command, "functions": functions},
                  stream, indent=1, sort_keys=True)
        stream.write("\n")


def evaluate(command: str, entries: List[Entry], thresholds: Dict[str, int],
             baseline: Optional[Dict[str, Dict[str, int]]], baseline_root: str
             ) -> Tuple[List[Finding], int]:
    """(findings, number of baseline values that improved)."""
    findings, improved = [], 0
    names = keys(entries, baseline_root) if baseline is not None else [None] * len(entries)
    for entry, key in zip(entries, names):
        function, recorded = entry.function, (baseline or {}).get(key)
        ignored = suppressions(entry.source, function)
        if "" in ignored.values():
            findings.append(Finding(function.file, function.line, function.name, "suppression",
                                    0, None, None, ""))
        for metric, value in entry.metrics.items():
            if thresholds and metric not in thresholds:
                continue
            limit = thresholds.get(metric)
            before = recorded.get(metric) if recorded else None
            if before is not None:
                improved += value < before
                if value <= before or (limit is not None and value <= limit):
                    continue
                limit = before if limit is None else max(before, limit)
            elif limit is None or value <= limit:
                continue
            reason = ignored.get(metric, ignored.get(command))
            findings.append(Finding(function.file, function.line, function.name, metric, value,
                                    limit, before, reason or ""))
    return findings, improved
