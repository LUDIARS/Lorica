"""Mutate-and-compile for one compiler and standard. @implements SPEC-LR-ANALYZE

Round 0 compiles every unit in the copy with a canary (a `_Pragma("message")`) in
the body of each candidate and no `constexpr`: a unit that fails under the strict flags, times
out or reads an original of a copied file is a tool error and is not used. The
canaries say which unit compiled which candidate; a candidate no usable unit
compiled is "inactive", never a result. Then `constexpr` is inserted at every
active candidate at once and the units that compiled them are recompiled. Each
error is attributed to the candidate whose lines hold it (or one of its notes or
instantiation contexts); that candidate is rejected with the error as its first
diagnostic and the units that compiled it are recompiled, until no error is
left (a fixed point: dropping one candidate can reject a caller). A "differs in
'constexpr'" redeclaration error adds the specifier to that declaration too, when
it is in an analysed file. An error no candidate holds is a tool error for the
candidates of that unit.

Results: rejected (first diagnostic), accepted (the compiler tolerates the
specifier: a necessary condition only), witnessed. A user witness for an accepted
candidate is appended to a unit that compiled it (`#include` of the unit, then the
witness); it is witnessed only when that compiles with the converged mutation and
fails to compile on the unmutated copy, so a witness that does not depend on any
`constexpr` added here never verifies anything.
"""
import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, List, NamedTuple, Optional, Set, Tuple

from . import constexpr_compiler as compiler
from .constexpr_locate import Candidate, declaration_offset, probe, render
from .constexpr_overlay import Overlay
from .extract import SourceFile
from .lexer import tokenize

REJECTED, ACCEPTED, WITNESSED, INACTIVE, ERROR = "rejected", "accepted", "witnessed", "inactive", "error"
_REDECLARED = re.compile(r"differs in .constexpr.|follows non-constexpr declaration")


class Configuration(NamedTuple):
    toolchain: compiler.Toolchain
    std: str
    units: List[compiler.Unit]
    skipped: int            # units configured for a newer standard

    @property
    def label(self) -> str:
        return "%s c++%s" % (os.path.basename(self.toolchain.command), self.std)


class Result(NamedTuple):
    state: str
    detail: str


class Trial(NamedTuple):
    configuration: Configuration
    results: Dict[int, Result]
    fixups: Dict[int, List[Tuple[str, int]]]   # extra declarations given the specifier
    errors: List[str]
    command: List[str]                         # first usable unit, original paths
    removed: List[str]                         # flags taken out of the units' commands


def _where(path: str, line: int, message: str) -> str:
    shown = os.path.relpath(path) if not os.path.isabs(path) or path.startswith(os.getcwd()) else path
    return "%s:%d: %s" % (shown, line, message)


def witness_names(code: str) -> Set[str]:
    return {t.text for t in tokenize(code).tokens}


class _Run:
    def __init__(self, configuration, candidates, files, overlay, witnesses, jobs, timeout, execute):
        self.configuration, self.candidates, self.files = configuration, candidates, files
        self.overlay, self.witnesses, self.jobs, self.timeout = overlay, witnesses, jobs, timeout
        self.execute = execute or compiler.execute     # looked up per run: tests replace it
        self.fixups: Dict[int, List[Tuple[str, int]]] = {}
        self.results: Dict[int, Result] = {}
        self.errors: List[str] = []
        self.removed: Dict[str, None] = {}      # in order of appearance
        self.touched = {path for path, _ in candidates}

    def write(self, active: Set[int]) -> None:
        inserts: Dict[str, List[Tuple[int, str]]] = {path: [] for path in self.touched}
        for i, (path, candidate) in enumerate(self.candidates):
            inserts[path].append((candidate.canary, probe(i)))
            if i in active:
                inserts[path].append((candidate.offset, "constexpr "))
                for fixed, offset in self.fixups.get(i, ()):
                    inserts.setdefault(fixed, []).append((offset, "constexpr "))
        for path, items in inserts.items():
            self.overlay.write(path, render(self.files[path][1], items))

    def argv(self, unit: compiler.Unit, source: Optional[str] = None) -> List[str]:
        argv, removed = compiler.strict_command(self.configuration.toolchain, unit, self.configuration.std,
                                                self.overlay.to_copy, source)
        self.removed.update(dict.fromkeys(removed))
        return argv

    def compile(self, jobs: List[Tuple[compiler.Unit, Optional[str]]]):
        def one(job):
            unit, source = job
            cwd = unit.directory if os.path.isdir(unit.directory) else self.overlay.directory
            status, text = self.execute(self.argv(unit, source), cwd, self.timeout)
            output = compiler.parse(text, cwd)
            output = output._replace(
                errors=[self._original(d) for d in output.errors])
            return status, output
        with ThreadPoolExecutor(max_workers=max(1, self.jobs)) as pool:
            return list(pool.map(one, jobs))

    def _original(self, d: compiler.Diagnostic) -> compiler.Diagnostic:
        back = self.overlay.to_original
        return d._replace(file=back(d.file), related=tuple((back(f), n, m) for f, n, m in d.related))

    def _holders(self, path: str, line: int, active: Set[int]) -> List[int]:
        return [i for i in active if self.candidates[i][0] == path
                and self.candidates[i][1].function.start_line <= line <= self.candidates[i][1].function.end_line]

    def _owners(self, d: compiler.Diagnostic, active: Set[int]) -> List[int]:
        for path, line in [(d.file, d.line)] + [(f, n) for f, n, _ in d.related]:
            found = self._holders(path, line, active)
            if found:
                return found
        return []

    def _fixup(self, d: compiler.Diagnostic, active: Set[int]) -> Optional[int]:
        """Give a redeclaration the specifier; the candidate's index, or None."""
        if not _REDECLARED.search(d.message):
            return None
        places = [(d.file, d.line)] + [(f, n) for f, n, _ in d.related]
        owners = [(i, p) for p in places for i in self._holders(p[0], p[1], active)]
        others = [p for p in places if not self._holders(p[0], p[1], set(range(len(self.candidates))))]
        if len(owners) != 1 or len(others) != 1 or others[0][0] not in self.files:
            return None
        index, (path, line) = owners[0][0], others[0]
        source, text = self.files[path]
        offset = declaration_offset(source, text, line, self.candidates[index][1].function.name)
        if offset is None or (path, offset) in self.fixups.get(index, []):
            return None
        self.fixups.setdefault(index, []).append((path, offset))
        self.touched.add(path)
        return index

    @staticmethod
    def unit_path(unit: compiler.Unit) -> str:
        return os.path.relpath(unit.file) if unit.file.startswith(os.getcwd()) else unit.file

    def unit_label(self, unit: compiler.Unit) -> str:
        return "%s (%s)" % (self.unit_path(unit), self.configuration.label)

    def usable(self, unit, status, output, what: str) -> bool:
        bypass = [h for h in output.headers if self.overlay.is_original(h)]
        if status is None:
            self.errors.append("%s: %s: %s" % (self.unit_label(unit), what, output.text.strip()))
        elif bypass:
            self.errors.append("%s: read %s from the analysed tree instead of the copy" % (
                self.unit_label(unit), bypass[0]))
        elif status != 0:
            first = output.errors[0] if output.errors else None
            self.errors.append("%s: %s: %s" % (self.unit_label(unit), what, _where(first.file, first.line, first.message)
                                              if first else (output.text.strip().splitlines() or ["no diagnostic"])[0]))
        else:
            return True
        return False

    def run(self) -> Trial:
        units = self.configuration.units
        self.write(set())
        outputs = self.compile([(u, None) for u in units])
        seen: Dict[int, Set[int]] = {}
        for k, (unit, (status, output)) in enumerate(zip(units, outputs)):
            if self.usable(unit, status, output, "does not compile unchanged under the strict flags"):
                seen[k] = output.probes
        compiled = set().union(*seen.values()) if seen else set()
        for i in range(len(self.candidates)):
            if i not in compiled:
                self.results[i] = Result(INACTIVE, "not compiled by any usable unit in this configuration")
        active = set(compiled)
        todo = [k for k in seen if seen[k] & active]
        while todo:
            self.write(active)
            dropped, refixed = set(), set()
            for k, (status, output) in zip(todo, self.compile([(units[k], None) for k in todo])):
                if status == 0 and not [h for h in output.headers if self.overlay.is_original(h)]:
                    continue
                attributed = False
                for d in output.errors:
                    fixed = self._fixup(d, active)
                    if fixed is not None:
                        refixed.add(fixed)
                        attributed = True
                        continue
                    for i in self._owners(d, active):
                        attributed = True
                        if i not in dropped:
                            self.results[i] = Result(REJECTED, _where(d.file, d.line, d.message))
                            dropped.add(i)
                if not attributed:
                    self.usable(units[k], status, output, "an error no candidate holds")
                    for i in seen[k] & active:
                        self.results[i] = Result(ERROR, "not decided: %s" % self.errors[-1])
                        dropped.add(i)
            active -= dropped
            changed = dropped | refixed
            todo = [k for k in seen if seen[k] & changed]
        for i in active:
            self.results[i] = Result(ACCEPTED, "necessary condition only, not verified: no witness")
        self._witness(active, seen)
        first = next((units[k] for k in sorted(seen)), units[0] if units else None)
        command = [a.replace(self.overlay.tree, self.overlay.root) for a in self.argv(first)] if first else []
        return Trial(self.configuration, self.results, self.fixups, self.errors, command, list(self.removed))

    def _witness(self, active: Set[int], seen: Dict[int, Set[int]]) -> None:
        jobs = []
        for i in sorted(active):
            code = self.witnesses.get(i)
            if code is None:
                continue
            function = self.candidates[i][1].function
            names = witness_names(code)
            short = function.name.split("::")[-1]
            if not names & {"static_assert", "constexpr"}:
                self.results[i] = Result(ACCEPTED, "witness not run: it holds no static_assert and no constexpr")
                continue
            if function.kind in ("function", "constructor") and short not in names:
                self.results[i] = Result(ACCEPTED, "witness not run: it does not name %s" % short)
                continue
            unit = self.configuration.units[next(k for k in sorted(seen) if i in seen[k])]
            wrapper = os.path.join(self.overlay.directory, "witness-%d.cpp" % i)
            with open(wrapper, "w", encoding="utf-8") as stream:
                stream.write('#include "%s"\n#line 1 "lorica-witness"\n%s\n'
                             % (self.overlay.to_copy(unit.file).replace("\\", "/"), code))
            jobs.append((i, unit, wrapper))
        if not jobs:
            return
        self.write(active)
        with_change = self.compile([(unit, wrapper) for _, unit, wrapper in jobs])
        self.write(set())
        without = self.compile([(unit, wrapper) for _, unit, wrapper in jobs])
        for (i, unit, _), (status, output), (control, _) in zip(jobs, with_change, without):
            if status is None or control is None:
                self.results[i] = Result(ERROR, "witness not decided: %s" % (output.text.strip()[:200]))
                self.errors.append("%s: witness for %s timed out or could not run" % (
                    self.unit_label(unit), self.candidates[i][1].function.name))
            elif status != 0:
                first = output.errors[0] if output.errors else None
                self.results[i] = Result(ACCEPTED, "necessary condition only, not verified: the witness does "
                                         "not compile: %s" % (_where(first.file, first.line, first.message)
                                                              if first else "no diagnostic"))
            elif control == 0:
                self.results[i] = Result(ACCEPTED, "necessary condition only, not verified: the witness also "
                                         "compiles without the change, so it does not show constant evaluation")
            else:
                self.results[i] = Result(WITNESSED, "witness compiled in %s and fails without the change"
                                         % self.unit_path(unit))


def run_trial(configuration: Configuration, candidates: List[Tuple[str, Candidate]],
              files: Dict[str, Tuple[SourceFile, str]], overlay: Overlay, witnesses: Dict[int, str],
              jobs: int = 1, timeout: float = 120.0, execute: Optional[Callable] = None) -> Trial:
    """Results for every candidate in one configuration; the overlay is left mutated."""
    return _Run(configuration, candidates, files, overlay, witnesses, jobs, timeout, execute).run()
