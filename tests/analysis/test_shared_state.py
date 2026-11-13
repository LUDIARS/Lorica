"""shared-state: the review's decision rules as fixtures, the gate, Lorica itself."""
import json
import os
from pathlib import Path
import random
import re
import shutil
import tempfile
import time
import unittest

from support import FIXTURES, ROOT, run_cli
from lorica_analysis import shared_state
from lorica_analysis.declarations import declarations
from lorica_analysis.extract import analyse_text

CASES = FIXTURES / "shared_state"
ANONYMOUS = "(anonymous namespace)::"
_EXPECT = re.compile(r"^// expect: (datum|finding|sharing|flag) (\S+) (.+?)\s*$", re.M)


def result(*texts, names=None):
    """shared_state.Result of literal texts (or fixture files) analysed as one set."""
    collector = shared_state.Collector()
    for k, text in enumerate(texts):
        collector.add(analyse_text(names[k] if names else "t%d.cpp" % k, text))
    return collector.result()


def findings(res):
    return {(kind, e.function.name) for e in res.entries for kind, n in e.metrics.items() if n}


def expectations(text):
    found = {"datum": {}, "finding": set(), "sharing": {}, "flag": set()}
    for kind, a, b in _EXPECT.findall(text):
        if kind == "datum":
            found["datum"][a] = b
        elif kind == "finding":
            found["finding"].add((a, b))
        elif kind == "sharing":
            found["sharing"][a] = b
        else:
            found["flag"].add((a, b))
    return found


class FixtureTests(unittest.TestCase):
    """Every `// expect:` line of fixtures/shared_state, exactly."""

    def test_every_rule_fixture(self):
        cases = sorted(CASES.glob("*.cpp"))
        self.assertGreaterEqual(len(cases), 35)
        for path in cases:
            text = path.read_text(encoding="utf-8")
            with self.subTest(fixture=path.name):
                want, res = expectations(text), result(text, names=[path.name])
                self.assertTrue(want["datum"] or want["sharing"], "fixture without expectations")
                self.assertEqual({n.replace(ANONYMOUS, ""): d[0] for n, d in res.data.items()}, want["datum"])
                self.assertEqual(findings(res), want["finding"])
                for function, sharing in want["sharing"].items():
                    self.assertEqual(res.functions[function][0], sharing, function)
                for function, flag in want["flag"]:
                    self.assertIn(flag, res.functions[function][1], function)

    def test_every_fixture_has_a_tsan_marker(self):
        for path in CASES.glob("*.cpp"):
            with self.subTest(fixture=path.name):
                self.assertRegex(path.read_text(encoding="utf-8"),
                                 r"// tsan: (race|clean|not-observable\(.+\))")


class RuleTests(unittest.TestCase):
    """Negative cases and mutations: each must flip the outcome."""

    def judge(self, text):
        return result(text).data

    def test_guard_mutations_produce_findings(self):
        # Removing the guard or weakening the order of each clean fixture is reported.
        mutations = {
            "c02b_mutable_under_lock.cpp": ("std::lock_guard<std::mutex> g(m); ", ""),
            "c06c_release_acquire.cpp": ("memory_order_acquire", "memory_order_relaxed"),
            "c07b_cas_failure_acquire.cpp": ("std::memory_order_acquire)", "std::memory_order_relaxed)"),
            "c09b_dclp_atomic.cpp": ("memory_order_acquire", "memory_order_relaxed"),
            "c10f_manual_lock.cpp": ("m.lock(); ", ""),
            "c21_private_helper.cpp": ("std::lock_guard<std::mutex> g(m); add_locked", "add_locked"),
        }
        for name, (old, new) in mutations.items():
            with self.subTest(fixture=name):
                text = (CASES / name).read_text(encoding="utf-8")
                self.assertIn(old, text)
                clean, broken = result(text), result(text.replace(old, new, 1))
                real = lambda res: {k for k in findings(res) if k[0] != "unknown"}  # noqa: E731
                self.assertLess(real(clean), real(broken))

    def test_lock_region_ends_with_its_block(self):
        data = self.judge("#include <mutex>\nstd::mutex m; int a = 0;\n"
                          "void f() { { std::lock_guard<std::mutex> g(m); ++a; } }\n"
                          "void g() { if (a) { std::lock_guard<std::mutex> h(m); ++a; } }\n")
        self.assertEqual(data["a"][:2], ("inconsistent", "inconsistent-locking"))

    def test_manual_lock_ends_at_unlock(self):
        data = self.judge("#include <mutex>\nstd::mutex m; int a = 0, b = 0;\n"
                          "void f() { m.lock(); ++a; m.unlock(); ++b; }\n"
                          "void g() { std::lock_guard<std::mutex> l(m); ++a; ++b; }\n")
        self.assertEqual((data["a"][0], data["b"][0]), ("lock:m", "inconsistent"))

    def test_for_and_if_conditions_scope_their_declarations(self):
        data = self.judge("int i = 0;\nvoid f() { for (int i = 0; i < 3; ++i) {} ++i; }\n")
        self.assertEqual(data["i"][:2], ("missing", "unsynchronized"))

    def test_access_kinds(self):
        for statement, kind in (("++x;", "rmw"), ("x++;", "rmw"), ("x += 1;", "rmw"), ("x = 1;", "write"),
                                ("x.push_back(1);", "write"), ("x[0] = 1;", "write"), ("int y = x;", "read"),
                                ("return x.size();", "read"), ("f(x);", "call"), ("f(&x);", "call"),
                                ("--x;", "rmw")):
            with self.subTest(statement=statement):
                res = result("int x;\nvoid f(int);\nvoid g() { %s }\n" % statement)
                notes = [n for e in res.entries if e.function.name == "x" for n in e.notes]
                self.assertEqual([n.reason.split()[0] for n in notes], [kind])

    def test_atomic_roles(self):
        counter = "#include <atomic>\nstd::atomic<int> n{0};\nint other = 0;\n"
        # A relaxed counter: no finding, even next to other shared data read before it.
        res = result(counter + "void f() { n.fetch_add(1, std::memory_order_relaxed); }\n"
                     "int g() { return n.load(std::memory_order_relaxed); }\n")
        self.assertEqual(findings(res), set())
        # The same atomic stored relaxed after a write to shared data publishes it.
        res = result(counter + "void f() { other = 1; n.store(1, std::memory_order_relaxed); }\n")
        self.assertEqual(findings(res), {("relaxed-publication", "f")})
        # A counter followed by an unrelated write neither publishes nor protects it.
        res = result(counter + "void f() { n.fetch_add(1, std::memory_order_relaxed); ++other; }\n")
        self.assertEqual(findings(res), {("unsynchronized", "other")})
        # A counter never publishes, even after a write to shared data.
        res = result(counter + "void f() { ++other; n.fetch_add(1, std::memory_order_relaxed); }\n")
        self.assertEqual(findings(res), {("unsynchronized", "other")})
        # A pointer atomic is a publication; the default order is never a finding.
        res = result("#include <atomic>\nstd::atomic<int*> p{nullptr};\n"
                     "int f() { return *p.load(); }\nvoid g(int* q) { p.store(q); }\n")
        self.assertEqual(findings(res), set())

    def test_lambda_lockset(self):
        base = "#include <mutex>\n#include <thread>\nstd::mutex m; int a = 0;\n"
        cases = {"[&] { ++a; }();": "lock:m",
                 "std::thread([&] { ++a; }).join();": "inconsistent",
                 "auto later = [&] { ++a; }; later();": "inconsistent"}
        for statement, sync in cases.items():
            with self.subTest(statement=statement):
                data = self.judge(base + "void f() { std::lock_guard<std::mutex> g(m); %s }\n"
                                         "void h() { std::lock_guard<std::mutex> g(m); ++a; }\n" % statement)
                self.assertEqual(data["a"][0], sync)

    def test_shadowing(self):
        for body in ("int a = 0; ++a;", "for (auto& a : list) ++a;", "auto [a, b] = pair(); ++a;",
                     "try {} catch (int& a) { ++a; }"):
            with self.subTest(body=body):
                self.assertEqual(self.judge("int a = 0;\nvoid f() { %s }\n" % body)["a"][0], "not-needed")
        self.assertEqual(self.judge("int a = 0;\nvoid f(int a) { ++a; }\n")["a"][0], "not-needed")
        self.assertEqual(self.judge("int a = 0;\nvoid f() { int b = 0, a = 1; ++a; }\n")["a"][0], "not-needed")
        self.assertEqual(self.judge("int a = 0;\nvoid f(int x) { ++a; }\n")["a"][0], "missing")

    def test_guard_variants(self):
        base = "#include <mutex>\nstd::mutex m; int a = 0;\n"
        cases = {"auto g = std::unique_lock(m);": "lock:m",
                 "std::unique_lock<std::mutex> g(m, std::adopt_lock);": "lock:m",
                 "std::unique_lock<std::mutex> g(m, std::try_to_lock);": "unknown",
                 "std::unique_lock<std::mutex> g(m, std::defer_lock); g.lock();": "unknown",
                 "std::lock_guard<std::mutex> g(get_mutex());": "unknown",
                 "std::scoped_lock g(m, n);": "lock:m,n"}
        for statement, sync in cases.items():
            with self.subTest(statement=statement):
                data = self.judge(base + "void f() { %s ++a; }\n" % statement)
                self.assertEqual(data["a"][0], sync)

    def test_declarations(self):
        source = analyse_text("d.hpp", (
            "namespace n { namespace {\nint a = 0, *b; const int c = 1; static long d;\n}\n"
            "struct S { unsigned x : 3; mutable int y; static int z; std::mutex m; int& r; "
            "int f(int); private: void p(); };\nint S::z = 0;\nstd::atomic<long> e(0);\n"
            "constexpr int k = 2; extern int g; int h(int);\n}\n"))
        found = {v.name.replace("(anonymous namespace)::", ""): (v.storage, sorted(v.specifiers))
                 for v in declarations(source).variables}
        self.assertEqual(found, {
            "n::a": ("global", []), "n::b": ("global", ["pointer"]), "n::c": ("global", ["const"]),
            "n::d": ("global", ["static"]), "n::S::x": ("member", []), "n::S::y": ("member", ["mutable"]),
            "n::S::z": ("static member", []), "n::e": ("global", ["atomic"]),
            "n::k": ("global", ["const", "constexpr"]), "n::g": ("global", ["extern"])})
        self.assertEqual(declarations(source).private, {"n::S::p"})


class CommandTests(unittest.TestCase):
    """The gate: exit status, thresholds per finding kind, baseline, suppression."""

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory)

    def write(self, name, text):
        path = self.directory / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_findings_fail_only_when_asked(self):
        path = shutil.copy(CASES / "c10_different_mutexes.cpp", self.directory)
        status, out, _ = run_cli("shared-state", path)
        self.assertEqual(status, 0)
        self.assertTrue(out.startswith("lorica-analyze shared-state: files 1, functions analysed 2, data 1,"))
        status, out, _ = run_cli("shared-state", path, "--max-inconsistent-locking", "0")
        self.assertEqual(status, 1)
        self.assertIn("FAIL %s:4 shared: inconsistent-locking 1 > 0\n    (global int: synchronization "
                      "inconsistent, inconsistent-locking; accesses: 5 rmw {a} inc_a; 6 rmw {b} inc_b)\n"
                      % path, out)
        self.assertEqual(run_cli("shared-state", path, "--max-unsynchronized", "0")[0], 0)

    def test_unknown_fails_only_with_its_threshold(self):
        path = self.write("u.cpp", "int a = 0;\nvoid f() { external(a); }\n")
        self.assertEqual(run_cli("shared-state", path)[0], 0)
        status, out, _ = run_cli("shared-state", path, "--max-unknown", "0")
        self.assertEqual(status, 1)
        self.assertIn("f: unknown 1 > 0", out)

    def test_baseline_and_suppression(self):
        path = self.write("b.cpp", "int a = 0;\nvoid f() { ++a; }\n")
        baseline = self.directory / "baseline.json"
        self.assertEqual(run_cli("shared-state", path, "--write-baseline", baseline)[0], 0)
        self.assertEqual(run_cli("shared-state", path, "--baseline", baseline)[0], 0)
        self.write("b.cpp", "int a = 0;\nint c = 0;\nvoid f() { ++a; ++c; }\n")
        status, out, _ = run_cli("shared-state", path, "--baseline", baseline)
        self.assertEqual(status, 0)     # a new datum is not in the baseline and has no threshold
        status, out, _ = run_cli("shared-state", path, "--baseline", baseline, "--max-unsynchronized", "0")
        self.assertEqual(status, 1)
        self.assertIn(":2 c: unsynchronized 1 > 0", out)
        self.write("b.cpp", "int a = 0;\nint c = 0; // lorica-analyze: ignore(unsynchronized) set before threads\n"
                            "void f() { ++a; ++c; }\n")
        status, out, _ = run_cli("shared-state", path, "--baseline", baseline, "--max-unsynchronized", "0")
        self.assertEqual(status, 0)
        self.assertIn("suppressed %s:2 c: unsynchronized 1 > 0: set before threads" % path, out)

    def test_json_and_unparsed(self):
        path = shutil.copy(CASES / "c22_unparsed.cpp", self.directory)
        status, out, _ = run_cli("shared-state", path, "--json")
        self.assertEqual(status, 0)
        report = json.loads(out)
        self.assertEqual(report["summary"]["unparsed_regions"], 1)
        kinds = {f["name"]: f["kind"] for f in report["functions"]}
        self.assertEqual(kinds, {"shared": "datum", "read_shared": "function"})
        self.assertEqual(run_cli("shared-state", path, "--strict")[0], 2)

    def test_cross_file_set(self):
        header = self.write("c.hpp", "#include <mutex>\nclass C {\n    std::mutex m_;\n    int n_ = 0;\n"
                                     "public:\n    void set(int v);\n    int get();\n};\n")
        source = self.write("c.cpp", '#include "c.hpp"\nvoid C::set(int v) { std::lock_guard<std::mutex> g(m_); '
                                     'n_ = v; }\nint C::get() { return n_; }\n')
        status, out, _ = run_cli("shared-state", source, header, "--max-inconsistent-locking", "0")
        self.assertEqual(status, 1)
        self.assertIn("c.hpp:4 C::n_: inconsistent-locking 1 > 0", out)


class LoricaTests(unittest.TestCase):
    """Lorica's own include/ and src/: the published self-report."""

    def test_self_report(self):
        collector = shared_state.Collector()
        for directory in ("include", "src"):
            for path in sorted((ROOT / directory).rglob("*.[ch]pp")):
                source = analyse_text(str(path.relative_to(ROOT)), path.read_text(encoding="utf-8"))
                self.assertEqual(source.unparsed, [])
                collector.add(source)
        res = collector.result()
        shared = {n: d[0] for n, d in res.data.items() if d[2] != "member"}
        self.assertEqual(shared, {
            "lorica::contracts::(anonymous namespace)::installed_handler": "atomic:acq_rel,acquire",
            "lorica::contracts::(anonymous namespace)::handling_violation": "not-needed"})
        self.assertEqual({k for k in findings(res) if k[0] != "unknown"}, set())
        streams = {n for n, (_, flags) in res.functions.items() if "shared-stream" in flags}
        self.assertEqual(streams, {"lorica::contracts::invoke_default_contract_violation_handler"})
        self.assertEqual(res.functions["lorica::contracts::detail::handle_violation"][0], "unknown")
        self.assertEqual(res.functions["lorica::contracts::set_violation_handler"][0],
                         "self-synchronized(unverified)")


class RobustnessTests(unittest.TestCase):
    def test_random_and_truncated_input_never_raises(self):
        rng = random.Random(7)
        texts = [p.read_text(encoding="utf-8") for p in sorted(CASES.glob("*.cpp"))]
        alphabet = "{}()[];:<>=+-*&|!,.~ \nabcxyz0lock_guard std::mutex atomic static thread_local return"
        for k in range(150):
            text = rng.choice(texts)
            cut = text[:rng.randrange(len(text))] if k % 2 else "".join(
                rng.choice(alphabet) for _ in range(rng.randrange(400)))
            result(cut)

    def test_linear_time(self):
        unit = (CASES / "c21_private_helper.cpp").read_text(encoding="utf-8")
        started = time.perf_counter()
        result(*[unit.replace("Counter", "Counter%d" % k).replace("add", "add%d" % k) for k in range(80)])
        self.assertLess(time.perf_counter() - started, 20)

    @unittest.skipUnless(os.environ.get("LORICA_ANALYSIS_SYSTEM_HEADERS"), "set LORICA_ANALYSIS_SYSTEM_HEADERS")
    def test_system_headers(self):
        status, out, err = run_cli("shared-state", os.environ["LORICA_ANALYSIS_SYSTEM_HEADERS"])
        self.assertIn(status, (0, 2), err)
        self.assertIn("result:", out)


if __name__ == "__main__":
    unittest.main()
