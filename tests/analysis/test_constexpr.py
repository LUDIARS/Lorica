"""constexpr subcommand without a real compiler: locator, flags, overlay, result states.

The compiler is replaced in-process by FakeCompiler, which reads the copied files
the way GCC would for these purposes (includes relative to the including file, then
-I; `#ifdef _WIN32` and `#if 0` blocks skipped; `#error`; the canary printed) and
decides from FAKE_* markers in comments:
  FAKE_NAME(f)      this line defines f
  FAKE_CONSTANT     f really constant-evaluates (a witness of it passes)
  FAKE_REJECT       constexpr on this line is an error
  FAKE_EXTENSION    an error only under -pedantic-errors (a C++20 construct in C++17)
  FAKE_INVALID      an error only under -Werror=invalid-constexpr, unless -fpermissive
                    or -Wno-invalid-constexpr follows it
  FAKE_NEEDS(g)     an error while g's line has no constexpr (a call to g)
  FAKE_GARBAGE      the compiler exits 1 with no diagnostic
  FAKE_BROKEN       an error with or without constexpr (the unit never compiles)
  FAKE_SYNTAX       constexpr on this line is a syntax error (a misplaced specifier)
  FAKE_DECL(f)      a separate declaration of f: a definition with constexpr and this
                    line without it is a "differs in 'constexpr'" error
A witness `static_assert(f(...))` passes when f's line holds constexpr and
FAKE_CONSTANT; `static_assert(true || f(...))` always passes (it never evaluates f).
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from support import FIXTURES, extract, run_cli
from lorica_analysis import constexpr_compiler as compiler
from lorica_analysis.constexpr_compiler import ToolError, Toolchain, Unit
from lorica_analysis.constexpr_locate import EXTERNAL, MEMBER, TEMPLATE, declaration_offset, locate
from lorica_analysis.constexpr_overlay import Overlay

SHAPES = FIXTURES / "constexpr"
GCC = Toolchain("g++", "gcc", "13.3.0", "17")
CLANG = Toolchain("clang++", "clang", "18.1.3", "17")


class FakeCompiler:
    def __init__(self, family="gcc"):
        self.family, self.calls = family, []

    def __call__(self, argv, cwd, timeout):
        self.calls.append(list(argv))
        if "--version" in argv:
            return 0, ("clang version 18.1.3\n" if self.family == "clang" else
                       "g++ (Fake) 13.3.0\nCopyright (C) 2023 Free Software Foundation, Inc.\n")
        if "-dM" in argv:
            return 0, "#define __cplusplus 201703L\n"
        includes = [a[2:] or argv[k + 1] for k, a in enumerate(argv) if a.startswith("-I")]
        source = next(a for a in argv[1:] if a.endswith(".cpp") and not a.startswith("-"))
        lines, headers, errors = [], [], []
        self._read(source, 0, includes, lines, headers, errors)
        defined = {m.group(1): text for _, _, text in lines for m in [re.search(r"FAKE_NAME\((\w+)\)", text)] if m}
        out = list(headers)
        for path, number, text in lines:
            probe = re.search(r"lorica-probe:(\d+)", text)
            if probe:
                out.append("%s:%d:1: note: '#pragma message: lorica-probe:%s'" % (path, number, probe.group(1)))
            where = "%s:%d:1: error: " % (path, number)
            if "FAKE_BROKEN" in text:
                errors.append(where + "broken unit")
            if path == "lorica-witness" and "static_assert(" in text and "true ||" not in text:
                name = re.search(r"static_assert\(\s*(\w+)\(", text).group(1)
                body = defined.get(name, "")
                if "constexpr" not in body or "FAKE_CONSTANT" not in body:
                    errors.append(where + "non-constant condition for static assertion")
            if "constexpr" not in text.split("//")[0] or path == "lorica-witness":
                continue
            flags = argv[argv.index("-Werror=invalid-constexpr"):] if "-Werror=invalid-constexpr" in argv else []
            if "FAKE_GARBAGE" in text:
                return 1, "the compiler crashed\n"
            if "FAKE_SYNTAX" in text:
                errors.append(where + "expected unqualified-id before 'constexpr'")
            if "FAKE_REJECT" in text:
                errors.append(where + "fake rejection")
            if "FAKE_EXTENSION" in text and "-pedantic-errors" in argv and "-fpermissive" not in argv:
                errors.append(where + "'try' in 'constexpr' function only available with '-std=c++20'")
            if "FAKE_INVALID" in text and flags and "-fpermissive" not in argv \
                    and "-Wno-invalid-constexpr" not in flags:
                errors.append(where + "call to non-'constexpr' function 'int ext(int)'")
            for needed in re.findall(r"FAKE_NEEDS\((\w+)\)", text):
                if "constexpr" not in defined.get(needed, "").split("//")[0]:
                    errors.append(where + "call to non-'constexpr' function 'int %s(int)'" % needed)
            for name in re.findall(r"FAKE_NAME\((\w+)\)", text):
                for decl_path, decl_number, decl in lines:
                    if "FAKE_DECL(%s)" % name in decl and "constexpr" not in decl.split("//")[0]:
                        errors.append(where + "redeclaration 'constexpr int %s(int)' differs in 'constexpr' from "
                                      "previous declaration\n%s:%d:5: note: previous declaration 'int %s(int)'"
                                      % (name, decl_path, decl_number, name))
        return (1 if errors else 0), "\n".join(out + errors) + "\n"

    def _read(self, path, depth, includes, lines, headers, errors):
        label, skip, number_base = path, 0, 0
        with open(path, encoding="utf-8") as stream:
            content = stream.read().split("\n")
        for number, text in enumerate(content, 1):
            stripped = text.strip()
            if stripped.startswith(("#if 0", "#ifdef _WIN32")):
                skip += 1
            elif stripped.startswith("#endif") and skip:
                skip -= 1
            elif skip:
                continue
            elif stripped.startswith('#line 1 "lorica-witness"'):
                label, number_base = "lorica-witness", number
            elif stripped.startswith("#error"):
                errors.append("%s:%d:2: error: %s" % (label, number, stripped))
            elif stripped.startswith("#include"):
                quote, name = re.match(r'#include\s*([<"])([^>"]+)', stripped).groups()
                found = [os.path.join(d, name) for d in ([os.path.dirname(path)] if quote == '"' else []) + includes
                         if os.path.isfile(os.path.join(d, name))]
                if found:
                    headers.append("." * (depth + 1) + " " + os.path.normpath(found[0]))
                    self._read(found[0], depth + 1, includes, lines, headers, errors)
            else:
                lines.append((label, number - number_base if label == "lorica-witness" else number, text))
        return lines


def tree_hash(root):
    digest = hashlib.sha256()
    for directory, subdirectories, files in sorted(os.walk(root)):
        subdirectories.sort()
        for name in sorted(files):
            path = os.path.join(directory, name)
            digest.update(os.path.relpath(path, root).encode() + b"\0" + Path(path).read_bytes())
    return digest.hexdigest()


class LocatorTests(unittest.TestCase):
    def located(self, name):
        text = (SHAPES / name).read_text(encoding="utf-8")
        source = extract("constexpr/" + name)
        return source, text, locate(source, text)

    def test_header_shapes(self):
        source, text, found = self.located("shapes.hpp")
        self.assertEqual(found.refused, [])
        self.assertEqual(found.already, 2)          # already() and literal's constructor
        inserted = {c.function.name: (text[c.offset:].split("(")[0], c.hidden) for c in found.candidates}
        self.assertEqual(inserted, {
            "trap": ("inline void trap", ""),                       # after [[noreturn]]
            "sealed::sealed": ("explicit sealed", ""),
            "sealed::load": ("int load", MEMBER),                   # no constexpr constructor
            "sealed::limit": ("static int limit", ""),              # static: no object needed
            "sealed::same": ("friend bool same", ""),
            "literal::operator bool": ("explicit operator bool", ""),
            "literal::twice": ("virtual int twice", ""),
            "literal::get": ("inline int literal::get", ""),        # out of line, literal class
            "plain::get": ("int get", ""),                          # aggregate: may be literal
            "guard::guard": ("explicit guard", TEMPLATE),           # member of a class template
            "guard::~guard": ("~guard", TEMPLATE),
            "read": ("T read", TEMPLATE),                           # after template<> requires [[]]
            "c_api": ("inline int c_api", ""),                      # after extern "C"
            "unexplained": ("int unexplained", ""),                 # a suppression needs a reason
            "one": ("int one", ""), "two": ("int two", ""),         # two definitions on one line
        })
        for candidate in found.candidates:
            self.assertEqual(text[candidate.canary - 1], "{")
        self.assertEqual({f.name: r for f, r in found.excluded}, {
            "twice": "a lambda bound to a variable: implicitly constexpr since C++17 where it qualifies",
            "quiet": "suppressed: kept as a run-time function"})

    def test_source_file_shapes(self):
        _, _, found = self.located("shapes.cpp")
        self.assertEqual([c.function.name for c in found.candidates],
                         ["helper", "(anonymous namespace)::hidden_helper", "(anonymous namespace)::local::get"])
        self.assertEqual({f.name: r for f, r in found.excluded}, {
            "parse": EXTERNAL, "TEST(suite,name)": "generated by a macro invocation",
            "main": "main cannot be constexpr"})
        self.assertIn("would have to move to a header, which changes linkage and exported symbols", EXTERNAL)

    def test_lorica_to_string_is_excluded_with_the_abi_reason(self):
        root = Path(__file__).resolve().parents[2]
        path = root / "src" / "contract_violation.cpp"
        text = path.read_text(encoding="utf-8")
        found = locate(extract(text, str(path)), text)
        reasons = [r for f, r in found.excluded if f.name == "lorica::contracts::to_string"]
        self.assertEqual(reasons, [EXTERNAL] * 3)
        self.assertNotIn("lorica::contracts::to_string", [c.function.name for c in found.candidates])

    def test_insertion_is_refused_when_not_read_back(self):
        text = "#define HEAD(x) int x\nHEAD(f)() { return 1; }\n"
        found = locate(extract(text, "m.hpp"), text)
        self.assertEqual(found.candidates, [])

    def test_declaration_offset(self):
        source, text, _ = self.located("shapes.hpp")
        line = next(n for n, l in enumerate(text.split("\n"), 1) if "int get() const;" in l)
        offset = declaration_offset(source, text, line, "literal::get")
        self.assertTrue(text[offset:].startswith("int get() const;"))
        line = next(n for n, l in enumerate(text.split("\n"), 1) if "to_string(int kind)" in l)
        offset = declaration_offset(source, text, line, "to_string")
        self.assertTrue(text[offset:].startswith("LORICA_API const char*"))   # after [[nodiscard]]
        self.assertIsNone(declaration_offset(source, text, 1, "nowhere"))


# Paths come back in the host's form (os.path.normpath): backslashes on Windows.
N = os.path.normpath


class FlagTests(unittest.TestCase):
    UNIT = Unit("g++", "/build", "/src/a.cpp", (
        "-fpermissive", "-w", "-Wno-invalid-constexpr", "-Wno-error=invalid-constexpr", "-fimplicit-constexpr",
        "-Wno-pedantic", "-Wno-c++20-extensions", "-Wno-error", "-Wno-gnu-statement-expression", "-std=gnu++20",
        "-o", "a.o", "-c", "-MD", "-MF", "a.d", "-I", "../include", "-I/abs/inc", "-isystem", "/sys",
        "-DX=1", "-Wall", "-Werror", "/src/a.cpp"), "20")

    def test_strict_flags_appended_and_defeating_flags_removed(self):
        mapped = lambda p: N("/copy") + p if p.startswith((N("/include"), N("/src"))) else p   # noqa: E731
        argv, removed = compiler.strict_command(GCC, self.UNIT, "17", mapped)
        self.assertEqual(removed, ["-fpermissive", "-w", "-Wno-invalid-constexpr", "-Wno-error=invalid-constexpr",
                                   "-fimplicit-constexpr", "-Wno-pedantic", "-Wno-c++20-extensions", "-Wno-error",
                                   "-Wno-gnu-statement-expression"])
        self.assertEqual(argv, ["g++", "-I", N("/copy/include"), "-I" + N("/abs/inc"), "-isystem", N("/sys"),
                                "-DX=1", "-Wall", "-Werror", N("/copy/src/a.cpp"), "-std=c++17", "-fsyntax-only", "-pedantic-errors",
                                "-Werror=invalid-constexpr", "-H", "-fdiagnostics-color=never"])
        argv, _ = compiler.strict_command(CLANG, self.UNIT, "23", mapped, "/tmp/witness.cpp")
        self.assertEqual(argv[-8:], ["/tmp/witness.cpp", "-std=c++23", "-fsyntax-only", "-pedantic-errors",
                                     "-Werror=invalid-constexpr", "-H", "-fdiagnostics-color=never",
                                     "-Wno-error=#pragma-messages"])

    def test_standards(self):
        self.assertEqual([compiler.standard([a]) for a in ("-std=gnu++17", "-std=c++2a", "--std=c++2b", "-O2")],
                         ["17", "20", "23", None])

    def test_database(self):
        with tempfile.TemporaryDirectory() as work:
            path = os.path.join(work, "compile_commands.json")
            Path(path).write_text(json.dumps([
                {"directory": "/b", "file": "../s/a.cpp", "command": "ccache g++ -std=gnu++20 -c '../s/a.cpp'"},
                {"directory": "/b", "file": "c.c", "arguments": ["gcc", "-c", "c.c"]},
                {"directory": "/b", "file": "d.cc", "arguments": ["clang++", "d.cc"]}]))
            units = compiler.database_units(path)
            self.assertEqual([(u.compiler, u.file, u.std) for u in units],
                             [("g++", N("/s/a.cpp"), "20"), ("clang++", N("/b/d.cc"), None)])
            Path(path).write_text("{")
            with self.assertRaises(ToolError):
                compiler.database_units(path)

    def test_detect(self):
        for name in ("cl", "cl.exe", "clang-cl", "/opt/x/clang-cl.exe"):
            with self.assertRaisesRegex(ToolError, "MSVC is not supported"):
                compiler.detect(name, 5)
        with mock.patch.object(compiler, "execute", FakeCompiler("clang")):
            self.assertEqual(compiler.detect("clang++-18", 5), Toolchain("clang++-18", "clang", "18.1.3", "17"))
        with mock.patch.object(compiler, "execute", lambda argv, cwd, t: (0, "icpx 2024.1\n")):
            with self.assertRaisesRegex(ToolError, "neither GCC nor Clang"):
                compiler.detect("icpx", 5)


class ParseTests(unittest.TestCase):
    GCC_OUTPUT = """. /copy/include/lib/a.hpp
.. /copy/include/lib/b.hpp
/copy/include/lib/b.hpp:3:1: note: '#pragma message: lorica-probe:4'
In file included from /copy/src/u.cpp:1:
/copy/include/lib/b.hpp: In instantiation of 'constexpr int f(T) [with T = NC]':
/copy/src/u.cpp:3:24:   required from here
/copy/include/lib/b.hpp:9:44: error: call to non-'constexpr' function 'int NC::size_nc() const'
/copy/include/lib/b.hpp:2:5: note: 'int NC::size_nc() const' declared here
Multiple include guards may be useful for:
/copy/include/lib/b.hpp
"""
    CLANG_OUTPUT = """/copy/a.hpp:3:28: warning: lorica-probe:0 [-W#pragma-messages]
<scratch space>:2:2: note: expanded from here
/copy/a.hpp:7:16: error: constexpr declaration of 'get' follows non-constexpr declaration
/copy/a.hpp:6:28: note: previous declaration is here
<scratch space>:4:2: note: expanded from here
1 error generated.
"""

    def test_gcc(self):
        out = compiler.parse(self.GCC_OUTPUT, "/")
        self.assertEqual(out.probes, {4})
        self.assertEqual(out.headers, [N("/copy/include/lib/a.hpp"), N("/copy/include/lib/b.hpp")])
        self.assertEqual(out.errors, [compiler.Diagnostic(
            N("/copy/include/lib/b.hpp"), 9, "call to non-'constexpr' function 'int NC::size_nc() const'", (
                (N("/copy/src/u.cpp"), 3, "required from here"),
                (N("/copy/include/lib/b.hpp"), 2, "'int NC::size_nc() const' declared here")))])

    def test_clang(self):
        out = compiler.parse(self.CLANG_OUTPUT, "/")
        self.assertEqual(out.probes, {0})
        self.assertEqual(out.errors, [compiler.Diagnostic(
            N("/copy/a.hpp"), 7, "constexpr declaration of 'get' follows non-constexpr declaration",
            ((N("/copy/a.hpp"), 6, "previous declaration is here"),))])


class ExecuteTests(unittest.TestCase):
    def test_no_shell_and_closed_input(self):
        text = "$(touch pwned); echo `id` | cat"
        status, out = compiler.execute([sys.executable, "-c", "import sys; print(sys.argv[1]); print(sys.stdin.read() == '')",
                                        text], None, 30)
        self.assertEqual((status, out), (0, text + "\nTrue\n"))

    def test_timeout_and_missing_program(self):
        status, out = compiler.execute([sys.executable, "-c", "import time; time.sleep(30)"], None, 0.5)
        self.assertIsNone(status)
        self.assertIn("timed out after 0.5 s", out)
        status, out = compiler.execute(["/nonexistent/lorica-cxx"], None, 5)
        self.assertIsNone(status)


class OverlayTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        for name, text in {"include/lib/a.hpp": '#include "b.hpp"\n', "include/lib/b.hpp": "int b();\n",
                           ".git/HEAD": "x", "build/CMakeCache.txt": "", "build/gen.hpp": "",
                           "src/u.cpp": "#include <lib/a.hpp>\n"}.items():
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            (self.root / name).write_text(text)

    def test_copy_mapping_and_cleanup(self):
        before = tree_hash(self.root)
        with Overlay(str(self.root)) as overlay:
            b = str(self.root / "include/lib/b.hpp")
            copy = overlay.to_copy(b)
            self.assertNotEqual(copy, b)
            self.assertTrue(copy.startswith(overlay.directory))
            self.assertEqual(overlay.to_original(copy), os.path.realpath(b))
            self.assertTrue(overlay.is_original(b))
            self.assertFalse(overlay.is_original(copy))
            self.assertEqual(overlay.to_copy(str(self.root / "build/gen.hpp")), str(self.root / "build/gen.hpp"))
            self.assertFalse(os.path.exists(os.path.join(overlay.tree, ".git")))
            self.assertEqual(overlay.to_copy("/usr/include/stdio.h"), "/usr/include/stdio.h")
            overlay.write(b, "constexpr int b();\n")
            self.assertEqual(Path(copy).read_text(), "constexpr int b();\n")
            with self.assertRaises(ToolError):
                overlay.write("/usr/include/stdio.h", "")
            directory = overlay.directory
        self.assertFalse(os.path.exists(directory))
        self.assertEqual(tree_hash(self.root), before)

    def test_refusals(self):
        with self.assertRaisesRegex(ToolError, "more than 2 files"):
            Overlay(str(self.root), max_files=2)
        with mock.patch.object(tempfile, "tempdir", str(self.root / "src")):
            with self.assertRaisesRegex(ToolError, "inside the analysed tree"):
                Overlay(str(self.root))
        self.assertEqual(sorted(os.listdir(self.root / "src")), ["u.cpp"])

    def test_poisoned_copy_is_the_one_compiled(self):
        fake = FakeCompiler()
        with Overlay(str(self.root)) as overlay:
            overlay.write(str(self.root / "include/lib/b.hpp"), "#error poisoned copy\n")
            unit = Unit("g++", str(self.root), str(self.root / "src/u.cpp"), ("-Iinclude", "src/u.cpp"), None)
            argv, _ = compiler.strict_command(GCC, unit, "17", overlay.to_copy)
            status, text = fake(argv, unit.directory, 5)
            self.assertEqual(status, 1)
            self.assertIn("poisoned copy", text)
            headers = compiler.parse(text, unit.directory).headers
            self.assertEqual(len(headers), 2)
            self.assertFalse(any(overlay.is_original(h) for h in headers))


HEADER = """#pragma once
int ext(int);
int add(int a, int b) { return a + b; } // FAKE_NAME(add) FAKE_CONSTANT
int log_value(int a) { return a; } // FAKE_NAME(log_value)
int bad(int a) { return a; } // FAKE_NAME(bad) FAKE_REJECT
int base(int a) { return a; } // FAKE_NAME(base) FAKE_REJECT
int caller(int a) { return base(a); } // FAKE_NAME(caller) FAKE_NEEDS(base)
int risky(int a) { return a; } // FAKE_NAME(risky) FAKE_EXTENSION
int calls(int a) { return ext(a); } // FAKE_NAME(calls) FAKE_INVALID
int twice(int); // FAKE_DECL(twice)
inline int twice(int a) { return 2 * a; } // FAKE_NAME(twice) FAKE_CONSTANT
template <class T> int tmpl(T t) { return t; } // FAKE_NAME(tmpl)
#ifdef _WIN32
int windows_only(int a) { return a; } // FAKE_NAME(windows_only)
#endif
int run_time(int a) { return a; } // lorica-analyze: ignore(constexpr) needs the clock
int unwitnessed(int a) { return a; } // FAKE_NAME(unwitnessed) FAKE_CONSTANT (constant, but no witness)
"""
WITNESSES = {"lib/b.hpp::add(2)": "static_assert(add(1, 2) == 3);",
             "lib/b.hpp::log_value(1)": "static_assert(log_value(1) == 1);",
             "lib/b.hpp::twice(1)": "static_assert(twice(2) == 4);",
             "lib/b.hpp::tmpl(1)": ["constexpr int k = 1;", "static_assert(true || tmpl(k));"],
             "lib/b.hpp::gone(0)": "static_assert(gone());"}


class TrialTests(unittest.TestCase):
    """Result-state logic end to end through the command line, with FakeCompiler."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, onerror=self._writable)
        self.files = {"include/lib/a.hpp": '#pragma once\n#include "b.hpp"\n', "include/lib/b.hpp": HEADER,
                      "src/u.cpp": "#include <lib/a.hpp>\nint user() { return add(1, 2); }\n"}
        for name, text in self.files.items():
            self.write(name, text)
        self.write("include/witnesses.json", json.dumps({"schema_version": 1, "witnesses": WITNESSES}))
        self.database([("src/u.cpp", ["-fpermissive", "-Wno-invalid-constexpr", "-Wno-pedantic"])])
        self.fake = FakeCompiler()
        patcher = mock.patch.object(compiler, "execute", self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.temporary = Path(tempfile.mkdtemp())      # outside the analysed tree
        self.addCleanup(shutil.rmtree, self.temporary)
        patcher = mock.patch.object(tempfile, "tempdir", str(self.temporary))
        patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def _writable(function, path, _):
        os.chmod(os.path.dirname(path), stat.S_IRWXU)
        os.chmod(path, stat.S_IRWXU)
        function(path)

    def write(self, name, text):
        (self.root / name).parent.mkdir(parents=True, exist_ok=True)
        (self.root / name).write_text(text, encoding="utf-8")

    def database(self, units):
        self.write("build/compile_commands.json", json.dumps([{
            "directory": str(self.root / "build"), "file": str(self.root / name),
            "arguments": ["g++", "-I../include"] + flags + ["-c", str(self.root / name)]} for name, flags in units]))

    def run_json(self, *extra, analysed=("include",)):
        status, out, err = run_cli("constexpr", *[self.root / p for p in analysed], "--compile-commands",
                                   self.root / "build/compile_commands.json", "--witnesses",
                                   self.root / "include/witnesses.json", "--std", "17", "--json", *extra)
        data = json.loads(out) if out.startswith("{") else {}
        return status, data, err

    @staticmethod
    def states(data):
        return {c["name"]: {r["configuration"]: (r["state"], r["detail"]) for r in c["results"]}
                for c in data["constexpr"]["candidates"]}

    def test_three_states_and_the_reasons(self):
        status, data, err = self.run_json()
        self.assertEqual(status, 0, err)
        states = {name: results["g++ c++17"] for name, results in self.states(data).items()}
        self.assertEqual({n: s for n, (s, _) in states.items()}, {
            "add": "witnessed", "log_value": "accepted", "bad": "rejected", "base": "rejected",
            "caller": "rejected", "risky": "rejected", "calls": "rejected", "twice": "witnessed",
            "tmpl": "accepted", "windows_only": "inactive", "unwitnessed": "accepted"})
        self.assertEqual(states["unwitnessed"][1], "necessary condition only, not verified: no witness")
        self.assertIn("witness does not compile", states["log_value"][1])
        self.assertIn("non-constant condition", states["log_value"][1])
        self.assertIn("also compiles without the change", states["tmpl"][1])
        self.assertTrue(states["bad"][1].replace(os.sep, "/").endswith("lib/b.hpp:5: fake rejection"))
        self.assertTrue(states["caller"][1].replace(os.sep, "/").endswith("lib/b.hpp:7: call to non-'constexpr' function 'int base(int)'"))
        self.assertIn("only available with '-std=c++20'", states["risky"][1])     # -pedantic-errors kept
        self.assertIn("call to non-'constexpr'", states["calls"][1])             # -Werror=invalid-constexpr
        self.assertEqual(data["constexpr"]["configurations"][0]["removed_flags"],
                         ["-fpermissive", "-Wno-invalid-constexpr", "-Wno-pedantic"])
        self.assertEqual(data["constexpr"]["unused_witnesses"], ["lib/b.hpp::gone(0)"])
        self.assertEqual([e["name"] for e in data["constexpr"]["excluded"]], ["run_time"])
        hidden = {c["name"]: c["hidden"] for c in data["constexpr"]["candidates"] if c["hidden"]}
        self.assertEqual(hidden, {"tmpl": TEMPLATE})
        self.assertEqual({f["name"]: f["metrics"] for f in data["functions"]}["add"], {"witnessed": 1, "accepted": 0})

    def test_fixed_point_recompiles_after_a_rejection(self):
        self.run_json()
        compiles = [c for c in self.fake.calls if "-fsyntax-only" in c and not any("witness-" in a for a in c)]
        # unchanged; all mutated; without bad, base, risky, calls (twice's declaration fixed);
        # without caller, which base's rejection broke
        self.assertEqual(len(compiles), 4)

    def test_declaration_and_out_of_line_definition_get_the_specifier_together(self):
        patch = self.root / "out" / "witnessed.diff"
        patch.parent.mkdir()
        self.run_json("--emit-patch", patch)
        changed = [l for l in patch.read_text().splitlines() if l.startswith("+") and not l.startswith("+++")]
        self.assertEqual(changed, [
            "+constexpr int add(int a, int b) { return a + b; } // FAKE_NAME(add) FAKE_CONSTANT",
            "+constexpr int twice(int); // FAKE_DECL(twice)",
            "+constexpr inline int twice(int a) { return 2 * a; } // FAKE_NAME(twice) FAKE_CONSTANT"])

    def test_read_only_tree_is_untouched_and_the_copy_removed(self):
        before = tree_hash(self.root / "include"), tree_hash(self.root / "src")
        for directory, subdirectories, files in os.walk(self.root / "include"):
            for name in files + subdirectories:
                os.chmod(os.path.join(directory, name), stat.S_IREAD | stat.S_IEXEC)
        os.chmod(self.root / "include", stat.S_IREAD | stat.S_IEXEC)
        status, data, err = self.run_json()
        self.assertEqual(status, 0, err)
        self.assertEqual(self.states(data)["add"]["g++ c++17"][0], "witnessed")
        self.assertEqual((tree_hash(self.root / "include"), tree_hash(self.root / "src")), before)
        self.assertEqual(os.listdir(self.temporary), [])        # the copy is gone

    def test_relative_include_resolves_to_the_copy(self):
        # a.hpp includes "b.hpp" relatively; b.hpp holds the candidates. Through the copy:
        status, data, _ = self.run_json()
        self.assertEqual(self.states(data)["add"]["g++ c++17"][0], "witnessed")
        # A unit that reaches an original by an absolute path is a tool error, not a result.
        self.write("src/v.cpp", '#include "%s"\n' % (self.root / "include/lib/b.hpp"))
        self.database([("src/u.cpp", []), ("src/v.cpp", [])])
        status, data, _ = self.run_json()
        self.assertEqual(status, 2)
        self.assertTrue(any("from the analysed tree instead of the copy" in e for e in data["errors"]))

    def test_unit_that_never_compiles_and_compiler_without_diagnostic(self):
        self.write("src/u.cpp", "#include <lib/a.hpp>\nint broken() { return 0; } // FAKE_BROKEN\n")
        status, data, _ = self.run_json()
        self.assertEqual(status, 2)
        self.assertIn("does not compile unchanged under the strict flags", data["errors"][0])
        self.assertEqual({s for r in self.states(data).values() for s, _ in r.values()}, {"inactive"})
        self.write("src/u.cpp", "#include <lib/a.hpp>\n")
        self.write("include/lib/b.hpp", "int crash(int a) { return a; } // FAKE_GARBAGE\n")
        status, data, _ = self.run_json()
        self.assertEqual(status, 2)
        self.assertEqual(self.states(data)["crash"]["g++ c++17"][0], "error")

    def test_syntax_error_is_a_tool_error_not_a_rejection(self):
        self.write("include/lib/b.hpp", "int odd(int a) { return a; } // FAKE_SYNTAX\n")
        status, data, _ = self.run_json()
        self.assertEqual(status, 2)
        self.assertEqual(self.states(data)["odd"]["g++ c++17"][0], "error")
        self.assertIn("the inserted specifier broke the syntax of odd", data["errors"][0])

    def test_gate_and_baseline(self):
        status, data, _ = self.run_json("--max-witnessed", "0")
        self.assertEqual(status, 1)
        self.assertEqual(sorted(f["function"] for f in data["findings"]), ["add", "twice"])
        baseline = self.root / "out" / "baseline.json"
        baseline.parent.mkdir()
        self.assertEqual(self.run_json("--write-baseline", baseline)[0], 0)
        self.assertEqual(self.run_json("--max-witnessed", "0", "--baseline", baseline)[0], 0)

    def test_text_report(self):
        status, out, _ = run_cli("constexpr", self.root / "include", "--compile-commands",
                                 self.root / "build/compile_commands.json", "--std", "17", "--witnesses",
                                 self.root / "include/witnesses.json")
        self.assertEqual(status, 0)
        self.assertIn("tried g++ 13.3.0 -std=c++17: units 1; strict flags -fsyntax-only -pedantic-errors "
                      "-Werror=invalid-constexpr -H -fdiagnostics-color=never; removed -fpermissive "
                      "-Wno-invalid-constexpr -Wno-pedantic\n", out)
        self.assertIn(":3 add: witnessed everywhere\n    witnessed g++ c++17: witness compiled in ", out)
        self.assertIn(":4 log_value: accepted at most (not verified)\n    accepted g++ c++17: necessary condition "
                      "only, not verified: the witness does not compile: lorica-witness:1: non-constant", out)
        self.assertIn(":14 windows_only: inactive in every configuration\n", out)
        self.assertIn("hidden: 1 (template 1); --show-hidden lists them\n", out)
        self.assertNotIn(":12 tmpl", out)
        self.assertIn("note: witness not used (no candidate has this key): lib/b.hpp::gone(0)\n", out)

    def test_without_a_compiler_only_facts(self):
        status, out, _ = run_cli("constexpr", self.root / "include", self.root / "src", "--all")
        self.assertEqual(status, 0)
        self.assertEqual(self.fake.calls, [])
        self.assertIn("nothing was compiled (no --compiler and no --compile-commands): no function is "
                      "reported as rejected, accepted or witnessed\nnot tried: 11\n", out)
        self.assertIn("    not tried %s:12 tmpl (hidden: template)\n" % (self.root / "include/lib/b.hpp"), out)
        self.assertIn("    excluded %s:16 run_time: suppressed: needs the clock\n" % (self.root / "include/lib/b.hpp"),
                      out)
        self.assertIn("    excluded %s:2 user: %s\n" % (self.root / "src/u.cpp", EXTERNAL), out)

    def test_compiler_without_database_and_msvc(self):
        status, out, _ = run_cli("constexpr", self.root / "include", self.root / "src", "--compiler", "cl.exe")
        self.assertEqual(status, 2)
        self.assertIn("error: cl.exe: MSVC is not supported; GCC and Clang only", out)
        self.write("src/u.cpp", '#include "../include/lib/b.hpp"\n')
        status, data, _ = (lambda r: (r[0], json.loads(r[1]), r[2]))(run_cli(
            "constexpr", self.root / "include", self.root / "src", "--compiler", "g++", "--std", "20", "--json"))
        self.assertEqual(status, 0)
        self.assertEqual({c["name"]: c["results"][0]["state"] for c in data["constexpr"]["candidates"]}["bad"],
                         "rejected")


if __name__ == "__main__":
    unittest.main()
