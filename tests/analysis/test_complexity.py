"""Complexity metrics: hand-derived fixture values, Lorica functions, the clang-tidy cross-check."""
import re
import shutil
import subprocess
import unittest

from support import FIXTURES, ROOT, extract, measured
from lorica_analysis.complexity import ALL_BRANCHES

# function: (cyclomatic, cognitive, nesting, parameters), derived by hand from the
# rules in spec/feature/source-analysis.md, with the counted constructs noted.
EXPECTED = {
    "f2": (1, 0, 0, 2),
    "else_if_chain": (4, 4, 1, 1),       # if, else if, else if (+1 each), else +1
    "do_while": (2, 1, 1, 1),            # do counted once, not again for its while
    "ternaries": (4, 4, 0, 2),           # ?: +1, ?: +1, ?: inside a ?: branch +2
    "mixed": (3, 2, 0, 3),               # a && b || c: two sequences
    "grouped": (3, 1, 0, 3),             # a && (b && c): one sequence
    "alternating": (4, 2, 0, 4),         # a || b && c || d: || tree, one && run
    "lambda_nesting": (2, 2, 2, 1),      # if in a lambda body: +1 +1 nesting
    "switcher": (4, 1, 1, 1),            # 3 case labels; switch +1 cognitive only
    "catcher": (5, 5, 2, 1),             # if +1, catch +1, if +2, catch +1
    "jumper": (2, 2, 1, 1),              # if +1, goto +1
    "braced": (4, 6, 3, 3),              # if +1, for +2, if +3
    "unbraced": (4, 6, 3, 3),            # the same: braces do not matter
    "forwarding": (1, 0, 0, 2),          # T&&, auto&&, static_cast<U&&>: declarators
    "all_of": (2, 1, 0, 1),              # fold over && counts as one operator
    "ternary_in_else_if": (4, 5, 1, 2),  # if +1, else if +1, ?: in its condition +2, else +1
    "with_initializer": (3, 3, 1, 1),    # if, if constexpr, else
    "searching": (6, 8, 3, 3),           # while +1 && +1, for +2, if +3 || +1
    "else_nesting": (3, 4, 2, 2),        # if +1, else +1, if +2
    "ternary_chain": (3, 3, 0, 2),       # ?: +1, ?: in the false branch +2
    "local_class": (2, 2, 2, 1),         # local class member body nests one level
    "requires_in_body": (2, 1, 1, 1),    # requires { } in a condition is no block
    "range_for": (3, 3, 1, 1),           # for +1, ?: +2
}

# Real Lorica functions, cyclomatic complexity counted by hand from the source.
LORICA_CYCLOMATIC = {
    ("include/lorica/byte_reader.hpp", "lorica::byte_reader::read"): 5,      # if, for, ?:, ?:
    ("include/lorica/byte_view.hpp", "lorica::byte_view::make"): 4,          # if, ||, &&
    ("include/lorica/byte_view.hpp", "lorica::byte_view::subview"): 3,       # if, ?:
    ("include/lorica/checked_integer.hpp", "lorica::checked_add"): 7,        # if, if, &&, ||, &&, else if
    ("include/lorica/checked_integer.hpp", "lorica::checked_multiply"): 11,
    ("include/lorica/checked_integer.hpp", "lorica::checked_divide"): 5,     # if, if, if, &&
    ("include/lorica/input_budget.hpp", "lorica::input_budget::consume"): 4,  # if, ||, ||
    ("include/lorica/sealed_pack.hpp", "lorica::detail::place_in_pack"): 5,  # four if
    ("include/lorica/contract_overlay.hpp", "lorica::contracts::detail::first_failed"): 3,  # ?:, fold
    ("src/sealed_region_linux.cpp", "lorica::detail::sealed_region::sealed_region"): 8,
    ("src/sealed_region_linux.cpp", "lorica::detail::sealed_region::~sealed_region"): 3,
    ("src/contract_violation.cpp", "lorica::contracts::detail::handle_violation"): 5,
}


class FixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.metrics, cls.refused = measured(extract("complexity.cpp"))

    def test_hand_derived_values(self):
        self.assertEqual(self.refused, [])
        found = {name: (m.cyclomatic, m.cognitive, m.nesting, m.parameters)
                 for name, m in self.metrics.items()}
        self.assertEqual(found, EXPECTED)

    def test_do_while_counts_once(self):
        notes = [(n.metric, n.reason) for n in self.metrics["do_while"].contributions]
        self.assertEqual(notes, [("cognitive", "do"), ("cyclomatic", "do")])

    def test_contributions_name_line_and_reason(self):
        notes = [(n.line, n.metric, n.amount, n.reason) for n in self.metrics["braced"].contributions]
        self.assertEqual(notes, [
            (66, "cognitive", 1, "if"), (66, "cyclomatic", 1, "if"),
            (67, "cognitive", 2, "for (nesting 1)"), (67, "cyclomatic", 1, "for"),
            (68, "cognitive", 3, "if (nesting 2)"), (68, "cyclomatic", 1, "if")])

    def test_else_if_is_not_counted_as_else_plus_if(self):
        reasons = [n.reason for n in self.metrics["else_if_chain"].contributions if n.metric == "cognitive"]
        self.assertEqual(reasons, ["if", "else if", "else if", "else"])

    def test_nloc_counts_lines_with_code(self):
        self.assertEqual(self.metrics["do_while"].nloc, 6)
        self.assertEqual(self.metrics["mixed"].nloc, 1)

    def test_rvalue_declarators_are_not_logical_operators(self):
        metrics, _ = measured(extract(
            "template <class... A> void f(A&&... a) {\n"
            "  auto g = [](auto&& x, int&& y) { return x; };\n"
            "  int&& r = 1; const auto&& s = r; T&& t{u};\n"
            "  call(static_cast<A&&>(a)...); h<int&&, long&&>();\n"
            "  bool b = p && q;\n}\n"))
        self.assertEqual((metrics["f"].cyclomatic, metrics["f"].cognitive), (2, 1))

    def test_template_argument_commas_do_not_split_a_sequence(self):
        metrics, _ = measured(extract("lorica_shapes.hpp"))
        self.assertEqual((metrics["reads"].cyclomatic, metrics["reads"].cognitive), (3, 1))
        self.assertEqual((metrics["lorica::checked_add"].cyclomatic,
                          metrics["lorica::checked_add"].cognitive), (7, 7))

    def test_head_is_not_counted(self):
        metrics, _ = measured(extract(
            "int f(bool a = x && y) noexcept(p && q) requires (r || s) { return 0; }\n"))
        self.assertEqual((metrics["f"].cyclomatic, metrics["f"].cognitive), (1, 0))

    def test_union_label(self):
        metrics, _ = measured(extract("lorica_shapes.hpp"))
        self.assertEqual(metrics["lorica::post_guard::~post_guard"].label, ALL_BRANCHES)
        self.assertEqual(metrics["lorica::checked_add"].label, "")


class LoricaTests(unittest.TestCase):
    def test_hand_counted_cyclomatic(self):
        found = {}
        for (path, name) in LORICA_CYCLOMATIC:
            metrics, refused = measured(extract((ROOT / path).read_text(encoding="utf-8"), path))
            self.assertEqual(refused, [])
            found[(path, name)] = metrics[name].cyclomatic
        self.assertEqual(found, LORICA_CYCLOMATIC)


TIDY = shutil.which("clang-tidy-18") or shutil.which("clang-tidy")
# Reviewed divergences from clang-tidy-18: its unbraced-nesting bug, and fold
# expressions, which it does not count.
TIDY_DIVERGENCES = {"unbraced": (6, 3), "all_of": (1, 0)}


@unittest.skipUnless(TIDY, "clang-tidy is not installed: cross-check not run")
class ClangTidyCrossCheck(unittest.TestCase):
    def test_fixture_agrees_except_reviewed_divergences(self):
        config = ("{Checks: '-*,readability-function-cognitive-complexity', CheckOptions: {"
                  "readability-function-cognitive-complexity.Threshold: 0, "
                  "readability-function-cognitive-complexity.IgnoreMacros: true}}")
        output = subprocess.run([TIDY, "--config=" + config, str(FIXTURES / "complexity.cpp"),
                                 "--", "-std=c++20"], capture_output=True, text=True).stdout
        tidy = {m.group(1): int(m.group(2)) for m in re.finditer(
            r"warning: function '([^']+)' has cognitive complexity of (\d+)", output)}
        if not tidy:
            self.skipTest("clang-tidy produced no result (no C++20 standard library?)")
        mine, _ = measured(extract("complexity.cpp"))
        differences = {name: (m.cognitive, tidy.get(name, 0)) for name, m in mine.items()
                       if m.cognitive != tidy.get(name, 0)}
        self.assertEqual(differences, TIDY_DIVERGENCES)


if __name__ == "__main__":
    unittest.main()
