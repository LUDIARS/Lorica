"""Lexical C/C++ source analysis, used like an assertion; never edits or runs the code.

Python standard library only; no compiler, build or macro expansion. The limits are
in spec/feature/source-analysis.md (SPEC-LR-ANALYZE). Exit status: 0 analysed and
within limits; 1 a threshold or the baseline is exceeded; 2 usage error, unreadable
input, or (with --strict) any unparsed region. Nothing fails without a threshold
or a baseline.
"""
import argparse
import os
import sys
from typing import Callable, List, NamedTuple, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lorica_analysis import complexity, gate, report, shared_state, sources  # noqa: E402
from lorica_analysis.extract import Region, SourceFile, analyse_text  # noqa: E402


class Command(NamedTuple):
    help: str
    metrics: tuple                      # each gets a --max-<metric> option
    analyse: Callable[[SourceFile], Tuple[List[gate.Entry], List[Region]]]
    finish: Optional[Callable[[], Tuple[List[gate.Entry], List[Region]]]] = None  # after every file


def _complexity(source: SourceFile):
    results, refused = complexity.analyse(source)
    return [gate.Entry(source, f, {m: getattr(x, m) for m in complexity.METRICS},
                       x.contributions, x.label) for f, x in results], refused


# A subcommand is one entry here: a function from an extracted file to gate entries.
COMMANDS = {
    "complexity": Command("cyclomatic and cognitive complexity, nesting, parameters, NLOC",
                          complexity.METRICS, _complexity),
}
_SHARED_STATE = shared_state.Collector()
COMMANDS["shared-state"] = Command(
    "shared data and its locks, atomics and their memory orders, per datum and function",
    shared_state.FINDINGS, _SHARED_STATE.add, _SHARED_STATE.finish)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lorica_analyze.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    for name, command in COMMANDS.items():
        sub = commands.add_parser(name, help=command.help)
        sub.add_argument("paths", nargs="*", help="files and directories (recursive)")
        sub.add_argument("--exclude", action="append", default=[], metavar="GLOB")
        sub.add_argument("--compile-commands", metavar="FILE", help="take the files of this database")
        for metric in command.metrics:
            sub.add_argument("--max-" + metric, type=int, metavar="N", dest="max_" + metric)
        sub.add_argument("--baseline", metavar="FILE", help="fail only on functions worse than this")
        sub.add_argument("--write-baseline", metavar="FILE", help="record the current values")
        sub.add_argument("--strict", action="store_true", help="exit 2 on any unparsed region")
        sub.add_argument("--json", action="store_true", help="JSON report on standard output")
        sub.add_argument("--all", action="store_true", help="list every function in the text report")
    return parser


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    command = COMMANDS[args.command]
    if not args.paths and not args.compile_commands:
        print("error: no input: name files or directories, or --compile-commands", file=sys.stderr)
        return 2
    try:
        files = sources.select(args.paths, args.exclude, args.compile_commands)
        baseline = gate.load_baseline(args.baseline) if args.baseline else None
    except sources.InputError as error:
        print("error: %s" % error, file=sys.stderr)
        return 2
    entries, unparsed, not_analysed = [], [], []
    errors = [] if files else ["no C or C++ file selected"]
    for path in files:
        try:
            source = analyse_text(path, sources.read(path))
        except sources.InputError as error:
            errors.append(str(error))
            continue
        found, refused = command.analyse(source)
        entries += found
        unparsed += source.unparsed + refused
        not_analysed += source.not_analysed
    if command.finish:
        found, refused = command.finish()
        entries += found
        unparsed += refused
    thresholds = {m: getattr(args, "max_" + m) for m in command.metrics
                  if getattr(args, "max_" + m) is not None}
    root = os.path.dirname(os.path.abspath(args.baseline)) if args.baseline else ""
    findings, improved = gate.evaluate(args.command, entries, thresholds, baseline, root)
    failed = (thresholds or baseline is not None) and any(not f.suppressed for f in findings)
    incomplete = errors or (args.strict and unparsed)
    run = report.Run(args.command, command.metrics, files, entries, unparsed, not_analysed,
                     findings, improved, errors,
                     "incomplete" if incomplete else "fail" if failed else "pass")
    if args.write_baseline:
        try:
            gate.write_baseline(args.write_baseline, args.command, entries)
        except OSError as error:
            print("error: %s: %s" % (args.write_baseline, error.strerror), file=sys.stderr)
            return 2
    sys.stdout.write(report.to_json(run) if args.json else report.text(run, args.all))
    return 2 if incomplete else 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
