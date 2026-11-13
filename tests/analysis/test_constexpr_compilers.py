"""constexpr subcommand against real compilers: the design review's 65-case matrix (opt-in).

fixtures/constexpr/cases/*.cpp are the review's cases: `CX` marks the functions to
convert, the `#ifdef WITNESS` block constant-evaluates them. Each case becomes a
header (CX removed; any other function suppressed with ignore(constexpr), so the
case keeps its non-constexpr helpers) and a unit including it; the witness block
becomes the witness of every CX function. The tool runs once per compiler at
C++17, C++20 and C++23. A case's state is the worst state of its CX functions.

fixtures/constexpr/oracle.json holds the review's recorded result for GCC 13.3 and
Clang 18.1.3 with libstdc++ 13. The tool must agree on every case and standard
except the reviewed differences in DIFFERENCES, and must never report `witnessed`
where the review's witness did not compile. Exit 77 (skipped, never passed) on a
host without g++ 13 or clang++ 18, or not on Linux (other libraries and versions
give other, legitimate results).
"""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from support import FIXTURES, run_cli
from lorica_analysis import constexpr_compiler as compiler, gate
from lorica_analysis.constexpr_locate import locate
from lorica_analysis.extract import analyse_text

CASES = FIXTURES / "constexpr" / "cases"
ORACLE = json.loads((FIXTURES / "constexpr" / "oracle.json").read_text(encoding="utf-8"))
RECORDED = {"g++": "13", "clang++": "18"}
STANDARDS = ("17", "20", "23")
CODES = {"rejected": "R", "accepted": "A", "witnessed": "W"}
# The tool gives the specifier to every declaration of the function, as the review
# requires; the review's case added it to the definition only.
DIFFERENCES = {("27_decl_mismatch", compiler_, std): "W" for compiler_ in RECORDED for std in STANDARDS}


def available():
    found, notes = [], []
    if not sys.platform.startswith("linux"):
        return found, ["not Linux: the matrix was recorded with libstdc++ 13 on Linux"]
    for name, major in RECORDED.items():
        if not shutil.which(name):
            notes.append("%s not found" % name)
            continue
        try:
            toolchain = compiler.detect(name, 60)
        except compiler.ToolError as error:
            notes.append(str(error))
            continue
        if toolchain.version.split(".")[0] != major:
            notes.append("%s is %s, the matrix was recorded with %s" % (name, toolchain.version, major))
        else:
            found.append(name)
    return found, notes


def build(work: Path):
    """Write the converted cases; returns {case: [witness keys of its CX functions]}."""
    witnesses, keys = {}, {}
    for path in sorted(CASES.glob("*.cpp")):
        case = path.stem
        text = path.read_text(encoding="utf-8")
        body, _, witness = text.partition("#ifdef WITNESS\n")
        witness = witness.rsplit("#endif", 1)[0]
        marked = {n for n, line in enumerate(body.split("\n"), 1) if "CX " in line}
        body = body.replace("CX ", "")
        lines = body.split("\n")
        for function in analyse_text(case + ".hpp", body).functions:
            if not marked & set(range(function.start_line, function.line + 1)):
                lines[function.line - 1] += "  // lorica-analyze: ignore(constexpr) kept as the case wrote it"
        header = "\n".join(lines)
        (work / (case + ".hpp")).write_text(header, encoding="utf-8")
        (work / (case + ".cpp")).write_text('#include "%s.hpp"\n' % case, encoding="utf-8")
        source = analyse_text(str(work / (case + ".hpp")), header)
        found = locate(source, header)
        entries = [gate.Entry(source, c.function, {}) for c in found.candidates]
        keys[case] = gate.keys(entries, str(work))
        for key in keys[case]:
            witnesses[key] = witness
    (work / "witnesses.json").write_text(json.dumps({"schema_version": 1, "witnesses": witnesses}), encoding="utf-8")
    return keys


class CaseMatrix(unittest.TestCase):
    def test_matrix_agrees_with_the_review(self):
        work = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, work)
        keys = build(work)
        argv = ["constexpr", work, "--witnesses", work / "witnesses.json", "--json", "--show-hidden",
                "--jobs", "2"] + [a for c in COMPILERS for a in ("--compiler", c)] + \
            [a for s in STANDARDS for a in ("--std", s)]
        status, out, err = run_cli(*argv)
        data = json.loads(out)
        self.assertEqual(data["errors"], [])
        self.assertEqual(status, 0, err)
        by_key = {c["key"]: {r["configuration"]: r["state"] for r in c["results"]} for c in data["constexpr"]["candidates"]}
        rank = {"R": 0, "A": 1, "W": 2}
        agree, by_design, differ, unsound, rows = 0, 0, [], [], []
        for case, case_keys in sorted(keys.items()):
            row = []
            for name in COMPILERS:
                got = ""
                for std in STANDARDS:
                    states = [CODES.get(by_key[k]["%s c++%s" % (name, std)], "?") for k in case_keys]
                    got += min(states, key=lambda s: rank.get(s, -1))
                expected = ORACLE["states"][case][name]
                for k, std in enumerate(STANDARDS):
                    want = DIFFERENCES.get((case, name, std), expected[k])
                    if got[k] == want:
                        agree += got[k] == expected[k]
                        by_design += got[k] != expected[k]
                    else:
                        differ.append((case, name, std, expected[k], got[k]))
                    if got[k] == "W" and ORACLE["witness_compiles"][case][name][k] != "Y" \
                            and (case, name, std) not in DIFFERENCES:
                        unsound.append((case, name, std))
                row.append("%s %s/%s" % (name, got, expected))
            rows.append("%-40s %s" % (case, "  ".join(row)))
        print("\ncase                                     tool/review per C++17 C++20 C++23 (R rejected, "
              "A accepted, W witnessed)")
        print("\n".join(rows))
        print("same state as the review: %d of %d; differences by design (DIFFERENCES): %d; others: %s"
              % (agree, agree + by_design + len(differ), by_design, differ or "none"))
        self.assertEqual(unsound, [], "witnessed where the review's witness does not compile")
        self.assertEqual(differ, [])


TREE = {
    "include/lib/a.hpp": '#pragma once\n#include "b.hpp"\n',
    "include/lib/b.hpp": ('#pragma once\nint add(int a, int b) { return a + b; }\n'
                          'extern "C" inline int c_api(int a) { return a; }\n'
                          '#ifdef _WIN32\nint windows_only(int a) { return a; }\n#endif\n'),
    "src/u.cpp": "#include <lib/a.hpp>\nint user() { return add(1, 2) + c_api(3); }\n",
}


class CopiedTree(unittest.TestCase):
    """The mutated copy is what the real compiler reads (review: relative-include bypass)."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        for name, text in TREE.items():
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            (self.root / name).write_text(text, encoding="utf-8")
        self.database(["src/u.cpp"])
        (self.root / "w.json").write_text(json.dumps({"schema_version": 1, "witnesses": {
            "include/lib/b.hpp::add(2)": "static_assert(add(1, 2) == 3);",
            "include/lib/b.hpp::c_api(1)": "static_assert(c_api(4) == 4);"}}), encoding="utf-8")

    def database(self, names):
        (self.root / "compile_commands.json").write_text(json.dumps([{
            "directory": str(self.root), "file": name, "arguments": [COMPILERS[0], "-Iinclude", "-c", name]}
            for name in names]), encoding="utf-8")

    def run_tool(self):
        status, out, _ = run_cli("constexpr", self.root / "include", "--compile-commands",
                                 self.root / "compile_commands.json", "--witnesses", self.root / "w.json",
                                 "--std", "17", "--json")
        data = json.loads(out)
        return status, data, {c["name"]: c["results"][0]["state"] for c in data["constexpr"]["candidates"]}

    def test_relative_include_reaches_the_mutated_copy(self):
        status, data, states = self.run_tool()
        self.assertEqual(status, 0, data["errors"])
        self.assertEqual(states, {"add": "witnessed", "c_api": "witnessed", "windows_only": "inactive"})

    def test_poisoned_copy_fails_the_compile(self):
        from lorica_analysis.constexpr_overlay import Overlay
        unit = compiler.database_units(str(self.root / "compile_commands.json"))[0]
        toolchain = compiler.detect(COMPILERS[0], 60)
        with Overlay(str(self.root)) as overlay:
            overlay.write(str(self.root / "include/lib/b.hpp"), "#error lorica poisoned copy\n")
            argv, _ = compiler.strict_command(toolchain, unit, "17", overlay.to_copy)
            status, text = compiler.execute(argv, unit.directory, 60)
        self.assertNotEqual(status, 0)
        self.assertIn("lorica poisoned copy", text)

    def test_reading_an_original_is_a_tool_error(self):
        (self.root / "src/v.cpp").write_text('#include "%s"\n' % (self.root / "include/lib/b.hpp"))
        self.database(["src/u.cpp", "src/v.cpp"])
        status, data, _ = self.run_tool()
        self.assertEqual(status, 2)
        self.assertTrue(any("from the analysed tree instead of the copy" in e for e in data["errors"]))


COMPILERS, NOTES = available()

if __name__ == "__main__":
    if not COMPILERS:
        print("skipped: " + "; ".join(NOTES))
        sys.exit(77)
    if NOTES:
        print("partly skipped: " + "; ".join(NOTES))
    unittest.main()
