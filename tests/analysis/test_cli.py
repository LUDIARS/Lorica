"""Command-line contract: exit status, thresholds, baseline, suppression, input, reports."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from support import FIXTURES, run_cli
from lorica_analysis import sources

SIMPLE = "int simple(int a) { return a; }\n"
BRANCHY = ("int branchy(int a) {\n"
           "    if (a > 1) { if (a > 2) { return 2; } }\n"
           "    return 0;\n}\n")                       # cognitive 3, cyclomatic 3
WORSE = ("int branchy(int a) {\n"
         "    if (a > 1) { if (a > 2) { if (a > 3) { return 3; } } }\n"
         "    return 0;\n}\n")                         # cognitive 6
COVERAGE = "lorica-analyze complexity: files "


class CliTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory)

    def write(self, name, text):
        path = self.directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_no_threshold_never_fails(self):
        path = self.write("a.cpp", SIMPLE + BRANCHY)
        status, out, _ = run_cli("complexity", path)
        self.assertEqual(status, 0)
        self.assertTrue(out.startswith(COVERAGE + "1, functions analysed 2, unparsed regions 0,"))
        self.assertTrue(out.endswith("result: pass, findings 0, suppressed 0\n"))

    def test_threshold_exceeded_exits_1_with_contributions(self):
        path = self.write("a.cpp", SIMPLE + BRANCHY)
        status, out, _ = run_cli("complexity", path, "--max-cognitive", "2", "--max-cyclomatic", "3")
        self.assertEqual(status, 1)
        self.assertIn("FAIL %s:2 branchy: cognitive 3 > 2\n    line 3: +1 if\n"
                      "    line 3: +2 if (nesting 1)\n" % path, out)
        self.assertNotIn("cyclomatic 3", out)
        self.assertEqual(run_cli("complexity", path, "--max-cognitive", "3")[0], 0)
        for option in ("--max-nesting", "--max-parameters", "--max-nloc"):
            with self.subTest(option=option):
                self.assertEqual(run_cli("complexity", path, option, "0")[0], 1)

    def test_usage_and_input_errors_exit_2(self):
        self.assertEqual(run_cli("complexity")[0], 2)
        self.assertEqual(run_cli("complexity", self.directory / "missing.cpp")[0], 2)
        self.assertEqual(run_cli("complexity", self.write("a.cpp", SIMPLE), "--max-cognitive", "x")[0], 2)
        self.assertEqual(run_cli("nonsense", self.directory)[0], 2)
        status, out, _ = run_cli("complexity", self.write("empty/readme.txt", "x"))
        self.assertEqual(status, 0)  # a file named explicitly is analysed whatever its extension
        status, out, _ = run_cli("complexity", self.directory / "empty")
        self.assertEqual(status, 2)
        self.assertIn("error: no C or C++ file selected", out)

    def test_oversized_file_is_refused(self):
        path = self.write("a.cpp", SIMPLE * 10)
        saved, sources.MAX_BYTES = sources.MAX_BYTES, 64
        try:
            status, out, _ = run_cli("complexity", path)
        finally:
            sources.MAX_BYTES = saved
        self.assertEqual(status, 2)
        self.assertIn("larger than 64 bytes, not analysed", out)

    def test_strict_turns_any_unparsed_region_into_exit_2(self):
        for fixture in ("macro_body.cpp", "kr.c", "function_pointer.cpp", "unterminated.cpp",
                        "stray.cpp", "mismatch.cpp"):
            with self.subTest(fixture=fixture):
                path = FIXTURES / fixture
                self.assertEqual(run_cli("complexity", path)[0], 0)
                status, out, _ = run_cli("complexity", path, "--strict")
                self.assertEqual(status, 2)
                self.assertIn("unparsed regions 1,", out)
                self.assertIn("\nunparsed %s:" % path, out)
                self.assertIn("result: incomplete", out)

    def test_no_numbers_for_an_unparsed_region(self):
        status, out, _ = run_cli("complexity", FIXTURES / "macro_body.cpp", "--json")
        report = json.loads(out)
        self.assertEqual([f["name"] for f in report["functions"]], ["after_macro"])
        self.assertEqual(report["unparsed"][0]["line"], 6)

    def test_json_schema(self):
        path = self.write("a.cpp", BRANCHY)
        status, out, _ = run_cli("complexity", path, "--json", "--max-cognitive", "1")
        report = json.loads(out)
        self.assertEqual(status, 1)
        self.assertEqual(sorted(report), ["command", "errors", "findings", "functions", "not_analysed",
                                          "schema_version", "summary", "unparsed"])
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["summary"], {"files": 1, "functions": 1, "unparsed_regions": 0,
                                             "lines_not_analysed": 0, "findings": 1, "suppressed": 0,
                                             "improved": 0, "result": "fail"})
        function = report["functions"][0]
        self.assertEqual(sorted(function), ["contributions", "end_line", "file", "kind", "label", "line",
                                            "metrics", "name", "start_line"])
        self.assertEqual(function["metrics"], {"cyclomatic": 3, "cognitive": 3, "nesting": 2,
                                               "parameters": 1, "nloc": 4})
        self.assertEqual(report["findings"], [{"file": str(path), "line": 1, "function": "branchy",
                                               "metric": "cognitive", "value": 3, "limit": 1,
                                               "baseline": None, "suppressed": ""}])

    def test_coverage_counts_lines_not_analysed(self):
        status, out, _ = run_cli("complexity", FIXTURES / "preprocess.cpp")
        self.assertIn("unparsed regions 0, lines not analysed 3\n", out)
        self.assertIn("\nnot analysed %s:36-36: #if 0 branch\n" % (FIXTURES / "preprocess.cpp"), out)

    def test_baseline(self):
        path = self.write("src/a.cpp", SIMPLE + BRANCHY)
        baseline = self.directory / "baseline.json"
        self.assertEqual(run_cli("complexity", path, "--write-baseline", baseline)[0], 0)
        recorded = json.loads(baseline.read_text())
        self.assertEqual(recorded["schema_version"], 1)
        self.assertEqual(recorded["functions"]["src/a.cpp::branchy(1)"]["cognitive"], 3)
        gate = ("--max-cognitive", "1", "--baseline", baseline)
        # An existing finding does not fail.
        self.assertEqual(run_cli("complexity", path, *gate)[0], 0)
        # A function that gets worse fails, even under the threshold.
        path.write_text(SIMPLE + WORSE, encoding="utf-8")
        status, out, _ = run_cli("complexity", path, *gate)
        self.assertEqual(status, 1)
        self.assertIn("branchy: cognitive 6 > 3 (baseline 3)", out)
        self.assertEqual(run_cli("complexity", path, "--max-cognitive", "10", "--baseline", baseline)[0], 0)
        # A new function over the threshold fails.
        path.write_text(SIMPLE + BRANCHY + BRANCHY.replace("branchy", "fresh"), encoding="utf-8")
        status, out, _ = run_cli("complexity", path, *gate)
        self.assertEqual(status, 1)
        self.assertIn("fresh: cognitive 3 > 1\n", out)
        # An improvement is reported and --write-baseline records it.
        path.write_text(SIMPLE + "int branchy(int a) { return a; }\n", encoding="utf-8")
        status, out, _ = run_cli("complexity", path, *gate, "--write-baseline", baseline)
        self.assertEqual(status, 0)
        self.assertIn("values improved on the baseline: 1 (--write-baseline", out)
        self.assertEqual(json.loads(baseline.read_text())["functions"]["src/a.cpp::branchy(1)"]["cognitive"], 0)
        # The working directory does not matter: keys are relative to the baseline.
        cwd = os.getcwd()
        try:
            os.chdir(self.directory / "src")
            self.assertEqual(run_cli("complexity", "a.cpp", "--baseline", baseline)[0], 0)
        finally:
            os.chdir(cwd)

    def test_baseline_without_threshold_fails_on_any_worsening(self):
        path = self.write("a.cpp", BRANCHY)
        baseline = self.directory / "b.json"
        run_cli("complexity", path, "--write-baseline", baseline)
        path.write_text(WORSE, encoding="utf-8")
        self.assertEqual(run_cli("complexity", path, "--baseline", baseline)[0], 1)

    def test_unusable_baseline_exits_2(self):
        bad = self.write("bad.json", '{"schema_version": 99, "functions": {}}')
        status, _, err = run_cli("complexity", self.write("a.cpp", SIMPLE), "--baseline", bad)
        self.assertEqual(status, 2)
        self.assertIn("not a usable baseline", err)

    def test_suppression_with_and_without_reason(self):
        path = self.write("a.cpp", BRANCHY.replace(
            "int branchy(int a) {", "int branchy(int a) { // lorica-analyze: ignore(cognitive) table-driven, reviewed"))
        status, out, _ = run_cli("complexity", path, "--max-cognitive", "1")
        self.assertEqual(status, 0)
        self.assertIn("suppressed %s:1 branchy: cognitive 3 > 1: table-driven, reviewed\n" % path, out)
        self.assertIn("result: pass, findings 0, suppressed 1", out)
        path.write_text(BRANCHY.replace("int branchy(int a) {", "/* lorica-analyze: ignore(complexity) */ "
                                        "int branchy(int a) {"), encoding="utf-8")
        status, out, _ = run_cli("complexity", path, "--max-cognitive", "1")
        self.assertEqual(status, 1)
        self.assertIn("FAIL %s:1 branchy: suppression without a reason\n" % path, out)
        self.assertIn("FAIL %s:1 branchy: cognitive 3 > 1\n" % path, out)

    def test_input_selection(self):
        self.write("src/a.cpp", SIMPLE)
        self.write("src/b.hpp", BRANCHY)
        self.write("src/notes.txt", "int x() { if (y) {} }")
        self.write("src/third_party/c.cc", SIMPLE.replace("simple", "vendored"))
        status, out, _ = run_cli("complexity", self.directory, "--json")
        self.assertEqual(json.loads(out)["summary"]["files"], 3)
        status, out, _ = run_cli("complexity", self.directory, "--json", "--exclude", "*/third_party/*",
                                 "--exclude", "*.hpp")
        self.assertEqual([f["name"] for f in json.loads(out)["functions"]], ["simple"])
        database = self.write("build/compile_commands.json", json.dumps([
            {"directory": str(self.directory / "src"), "file": "a.cpp"},
            {"directory": str(self.directory), "file": "src/third_party/c.cc"}]))
        status, out, _ = run_cli("complexity", "--compile-commands", database, "--json")
        self.assertEqual([f["name"] for f in json.loads(out)["functions"]], ["simple", "vendored"])
        self.assertEqual(run_cli("complexity", "--compile-commands", self.write("x.json", "{"))[0], 2)

    def test_invalid_utf8_is_replaced_not_fatal(self):
        path = self.directory / "latin1.cpp"
        path.write_bytes(b"// caf\xe9\nint f() { return 1; }\n")
        status, out, _ = run_cli("complexity", path)
        self.assertEqual((status, "functions analysed 1," in out), (0, True))

    def test_all_lists_every_function(self):
        path = self.write("a.cpp", SIMPLE + BRANCHY)
        _, out, _ = run_cli("complexity", path, "--all")
        self.assertIn("cyclomatic  cognitive  nesting  parameters  nloc  function\n"
                      "         1          0        0           1     1  %s:1 simple\n"
                      "         3          3        2           1     4  %s:2 branchy\n" % (path, path), out)


if __name__ == "__main__":
    unittest.main()
