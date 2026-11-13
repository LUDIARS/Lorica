"""Extractor: head classification, fail-closed regions, Lorica's own sources, robustness."""
import os
from pathlib import Path
import random
import time
import unittest

from support import FIXTURES, ROOT, extract, measured
from lorica_analysis.complexity import analyse
from lorica_analysis.extract import analyse_text
from lorica_analysis.lexer import tokenize


def names(source):
    return [f.name for f in source.functions]


def spans(regions):
    return [(r.line, r.end_line) for r in regions]


class HeadTests(unittest.TestCase):
    """fixtures/heads.cpp: one case per head-classification rule."""

    @classmethod
    def setUpClass(cls):
        cls.source = extract("heads.cpp")
        cls.by_line = {(f.line, f.name): f for f in cls.source.functions}

    def test_table(self):
        expected = [
            (13, "Widget::Widget", "constructor", 0),          # : a_{1}, b_(2) {}
            (14, "Widget::Widget", "constructor", 1),          # function-try-block
            (15, "Widget::~Widget", "destructor", 0),
            (16, "Widget::operator bool", "operator", 0),
            (17, "Widget::operator()", "operator", 2),
            (18, "Widget::operator<=>", "operator", 1),
            (19, "Widget::operator<<", "operator", 1),
            (20, "Widget::f", "function", 2),                  # default arguments with braces
            (22, "Widget::g", "function", 1),                  # requires requires
            (23, "Widget::h", "function", 0),                  # trailing requires-clause
            (24, "Widget::t", "function", 0),                  # -> decltype(...)
            (25, "Widget::m", "function", 0),
            (26, "Widget::n", "function", 0),
            (27, "Widget::s", "function", 0),
            (28, "Widget::v", "function", 0),
            (29, "Widget::operator==", "operator", 1),         # [[nodiscard]] before (
            (32, 'operator ""_km', "operator", 1),             # user-defined literal
            (34, "after_macro", "function", 1),                # API int f() NOEXCEPT {
            (38, "TEST(Suite,Name)", "macro-function", 0),
            (45, "Exported::get", "function", 0),              # class EXPORT_CLASS X {
            (49, "prefixed::inside", "function", 0),           # MACRO namespace x {
            (53, "(anonymous namespace)::hidden", "function", 3),
            (58, "outer::inner::Widget2_convert", "function", 1),
            (61, "lambda_at_scope", "lambda", 1),              # namespace-scope lambda
            (64, "global_qualified", "function", 0),
        ]
        self.assertEqual([(f.line, f.name, f.kind, f.parameters) for f in self.source.functions], expected)
        self.assertEqual(self.source.unparsed, [])

    def test_specifiers_and_placement(self):
        s = self.by_line[(27, "Widget::s")]
        self.assertEqual(s.specifiers, {"static", "constexpr", "noexcept"})
        self.assertEqual(self.by_line[(28, "Widget::v")].specifiers, {"virtual", "const"})
        self.assertEqual(self.by_line[(14, "Widget::Widget")].specifiers, {"explicit"})
        convert = self.by_line[(58, "outer::inner::Widget2_convert")]
        self.assertEqual(convert.specifiers, {"template", "constexpr", "noexcept"})
        self.assertEqual((convert.start_line, convert.line, convert.body_line, convert.end_line), (57, 58, 58, 58))
        self.assertTrue(s.in_class_body and not s.in_header and not s.in_unnamed_namespace)
        hidden = self.by_line[(53, "(anonymous namespace)::hidden")]
        self.assertTrue(hidden.in_unnamed_namespace and not hidden.in_class_body)
        self.assertEqual(self.by_line[(23, "Widget::h")].specifiers, {"const"})
        self.assertTrue(extract("lorica_shapes.hpp").functions[0].in_header)

    def test_initializers_bitfields_and_declarations_are_not_functions(self):
        source = extract("struct S { int x : 3; int y{4}; int z = {5}; int a[2] = {1, 2}; };\n"
                         "int v = {5}; int w{f(1)}; int declared(int);\n")
        self.assertEqual((names(source), source.unparsed), ([], []))


class AdversarialTests(unittest.TestCase):
    """fixtures/hard.cpp: the review's 30 hard constructs."""

    def test_functions_regions_and_dropped_branches(self):
        source = extract("hard.cpp")
        self.assertEqual([(f.line, f.name) for f in source.functions], [
            (19, "Widget::Widget"), (20, "Widget::Widget"), (21, "Widget::operator bool"),
            (22, "Widget::operator()"), (24, "Widget::operator<<"), (25, "Widget::f"),
            (27, "Widget::g"), (28, "Widget::h"), (36, "after_macro"), (41, "uniform_or_shift"),
            (50, "fwd"), (55, "loops"), (68, "split_head"), (77, "recursion_overload"),
            (81, "digits"), (82, "labels"), (83, "S2::m"), (83, "S2::n"), (85, "lam"),
            (86, "braced"), (94, "unbraced")])
        self.assertEqual(spans(source.unparsed), [(32, 33), (65, 65), (84, 84)])  # BEGIN_FN, K&R, fn pointer
        self.assertEqual(spans(source.not_analysed), [(70, 70)])

    def test_known_silent_misses_stay_documented(self):
        # Functions generated by a #define body are invisible (spec: limits).
        self.assertFalse([n for n in names(extract("hard.cpp")) if "get_" in n])


class FailClosedTests(unittest.TestCase):
    """Each shape yields an unparsed region and never a function with numbers."""

    def check(self, fixture, regions, survivors):
        source = extract(fixture)
        self.assertEqual(spans(source.unparsed), regions)
        self.assertEqual(names(source), survivors)
        for function in source.functions:
            for region in source.unparsed:
                self.assertFalse(region.line <= function.end_line and function.start_line <= region.end_line)

    def test_brace_macros(self):
        self.check("macro_body.cpp", [(6, 7)], ["after_macro"])

    def test_kr_definition(self):
        self.check("kr.c", [(2, 2)], ["modern"])

    def test_function_returning_a_function_pointer(self):
        self.check("function_pointer.cpp", [(2, 2)], ["after"])

    def test_unterminated_brace(self):
        self.check("unterminated.cpp", [(3, 7)], [])

    def test_stray_brace_and_mismatch(self):
        self.check("stray.cpp", [(3, 3)], ["before", "after"])
        self.check("mismatch.cpp", [(3, 3)], ["before", "after"])

    def test_class_body_read_as_initializer_is_caught(self):
        # Without a class-key the scanner cannot know `DECLARE Foo {` opens a class.
        source = extract("DECLARE_CLASS Foo {\n  int f() { return 1; }\n};\nint g() { return 2; }\n")
        self.assertEqual((spans(source.unparsed), names(source)), ([(1, 3)], ["g"]))

    def test_control_keyword_at_declaration_scope(self):
        source = extract("namespace n {\nOPEN_BODY\n  if (x) return 1;\n}\nint g() { return 2; }\n")
        self.assertEqual((spans(source.unparsed), names(source)), ([(3, 3)], ["g"]))

    def test_deleting_any_closing_brace_never_shifts_later_functions(self):
        text = (FIXTURES / "heads.cpp").read_text(encoding="utf-8")
        whole = {(f.line, f.name) for f in extract("heads.cpp").functions}
        starts = [0]
        for line in text.split("\n"):
            starts.append(starts[-1] + len(line) + 1)
        closers = [starts[t.line - 1] + t.column - 1 for t in tokenize(text).tokens if t.text == "}"]
        for at in closers:
            source = analyse_text("heads.cpp", text[:at] + text[at + 1:])
            with self.subTest(offset=at):
                self.assertTrue(source.unparsed)
                self.assertLessEqual({(f.line, f.name) for f in source.functions}, whole)

    def test_body_the_statement_parser_refuses_is_unparsed(self):
        _, refused = measured(extract("int f(int a) {\n  if (a) return 1; else\n}\n"))
        self.assertEqual(spans(refused), [(1, 3)])
        self.assertIn("statement parser", refused[0].reason)


class LoricaShapeTests(unittest.TestCase):
    """fixtures/lorica_shapes.hpp: contracts.hpp, checked_integer.hpp, libstdc++ shapes."""

    def test_functions(self):
        source = extract("lorica_shapes.hpp")
        self.assertEqual([(f.line, f.name, f.kind) for f in source.functions], [
            (16, "lorica::post_guard::post_guard", "constructor"),
            (24, "lorica::post_guard::~post_guard", "destructor"),
            (42, "lorica::checked_add", "function"),
            (55, "ranges::in_ranges", "function"),
            (59, "basic_string::front", "function"),
            (65, "c_api", "function"),
            (73, "count", "function"),
            (76, "reads", "function")])
        self.assertEqual((source.unparsed, source.not_analysed), ([], []))
        self.assertNotIn("noexcept", source.functions[1].specifiers)  # noexcept(false)


class LambdaTests(unittest.TestCase):
    def test_lambdas_nested_ones_included(self):
        source = extract("int outer(int n) {\n"
                         "    auto a = [&](int x) { return [x](int y) { return x + y; }(n); };\n"
                         "    int arr[2] = {1, 2};\n"
                         "    return a(arr[0]) + [] { return 1; }();\n}\n")
        lambdas = source.functions[0].lambdas
        tokens, match = source.tokens, source.match
        self.assertEqual([(lam.line, lam.parameters is not None) for lam in lambdas],
                         [(2, True), (2, True), (4, False)])
        for lam in lambdas:
            self.assertEqual((tokens[lam.introducer].text, tokens[lam.body[0]].text), ("[", "{"))
            self.assertEqual(match[lam.body[0]], lam.body[1])
        outer, inner = lambdas[0].body, lambdas[1].body
        self.assertTrue(outer[0] < inner[0] < inner[1] < outer[1])


SELF_EXPECTED = {
    "include/lorica/bounded_text.hpp": [
        "lorica::detail::source_text", "lorica::detail::put_text", "lorica::copy_string",
        "lorica::append_string", "lorica::format_into"],
    "include/lorica/byte_reader.hpp": [
        "lorica::byte_reader::byte_reader", "lorica::byte_reader::size",
        "lorica::byte_reader::offset", "lorica::byte_reader::remaining",
        "lorica::byte_reader::take", "lorica::byte_reader::skip", "lorica::byte_reader::read",
        "lorica::byte_reader::read_big_endian", "lorica::byte_reader::read_little_endian",
        "lorica::byte_reader::read_prefixed", "lorica::byte_reader::assemble",
        "lorica::byte_reader::swapped", "lorica::byte_reader::shifted"],
    "include/lorica/byte_view.hpp": [
        "lorica::byte_view::make", "lorica::byte_view::size", "lorica::byte_view::at",
        "lorica::byte_view::subview", "lorica::byte_view::byte_view"],
    "include/lorica/checked_integer.hpp": [
        "lorica::narrow", "lorica::checked_add", "lorica::checked_subtract",
        "lorica::checked_multiply", "lorica::checked_divide", "lorica::saturating_add",
        "lorica::saturating_subtract", "lorica::saturating_multiply", "lorica::saturate_cast"],
    "include/lorica/checked_size.hpp": [
        "lorica::checked_add", "lorica::checked_multiply", "lorica::contains_range"],
    "include/lorica/contract_overlay.hpp": [
        "lorica::contracts::test_result::operator bool", "lorica::contracts::detail::call",
        "lorica::contracts::detail::first_failed", "lorica::contracts::contract",
        "lorica::contracts::overlay::pre", "lorica::contracts::overlay::pre",
        "lorica::contracts::overlay::post", "lorica::contracts::overlay::post",
        "lorica::contracts::overlay::on_violation", "lorica::contracts::overlay::on_violation",
        "lorica::contracts::overlay::operator()", "lorica::contracts::overlay::test",
        "lorica::contracts::overlay::overlay", "lorica::contracts::overlay::extend",
        "lorica::contracts::overlay::rebuild",
        "lorica::contracts::overlay::require_callable_conditions",
        "lorica::contracts::overlay::check", "lorica::contracts::overlay::sink"],
    "include/lorica/contract_violation.hpp": [
        "lorica::contracts::source_location::file_name",
        "lorica::contracts::source_location::function_name",
        "lorica::contracts::source_location::line",
        "lorica::contracts::contract_violation::contract_violation",
        "lorica::contracts::contract_violation::kind",
        "lorica::contracts::contract_violation::semantic",
        "lorica::contracts::contract_violation::mode",
        "lorica::contracts::contract_violation::comment",
        "lorica::contracts::contract_violation::location",
        "lorica::contracts::contract_violation::evaluation_exception",
        "lorica::contracts::contract_violation::is_terminating"],
    "include/lorica/contracts.hpp": [
        "lorica::contracts::detail::trap",
        "lorica::contracts::detail::contract_violated_during_constant_evaluation",
        "lorica::contracts::detail::holds",
        "lorica::contracts::detail::evaluate_at_runtime", "lorica::contracts::detail::check",
        "lorica::contracts::detail::check_result",
        "lorica::contracts::detail::post_guard::post_guard",
        "lorica::contracts::detail::post_guard::~post_guard",
        "lorica::contracts::detail::make_post_guard"],
    "include/lorica/detail/sealed_region.hpp": ["lorica::detail::sealed_region::data"],
    "include/lorica/input_budget.hpp": [
        "lorica::input_budget::input_budget", "lorica::input_budget::consume",
        "lorica::input_budget::permits_depth", "lorica::input_budget::remaining"],
    "include/lorica/sealed_pack.hpp": [
        "lorica::detail::place_in_pack", "lorica::pack_slot::pack_slot",
        "lorica::pack_array_slot::size", "lorica::pack_array_slot::pack_array_slot",
        "lorica::pack_builder::pack_builder", "lorica::pack_builder::add",
        "lorica::pack_builder::add_array", "lorica::pack_builder::used",
        "lorica::pack_builder::capacity", "lorica::pack_builder::reserve",
        "lorica::sealed_pack::sealed_pack", "lorica::sealed_pack::load", "lorica::sealed_pack::at",
        "lorica::sealed_pack::read"],
    "include/lorica/sealed_value.hpp": ["lorica::sealed_value::sealed_value", "lorica::sealed_value::load"],
    "include/lorica/unsafe_api.hpp": [],
    "src/contract_violation.cpp": [
        "lorica::contracts::(anonymous namespace)::handler_scope::handler_scope",
        "lorica::contracts::(anonymous namespace)::handler_scope::~handler_scope",
        "lorica::contracts::(anonymous namespace)::write_text",
        "lorica::contracts::set_violation_handler", "lorica::contracts::get_violation_handler",
        "lorica::contracts::to_string", "lorica::contracts::to_string", "lorica::contracts::to_string",
        "lorica::contracts::invoke_default_contract_violation_handler",
        "lorica::contracts::detail::handle_violation"],
    "src/sealed_region_linux.cpp": [
        "lorica::detail::sealed_region::sealed_region", "lorica::detail::sealed_region::~sealed_region"],
    "src/sealed_region_windows.cpp": [
        "lorica::detail::sealed_region::sealed_region", "lorica::detail::sealed_region::~sealed_region"],
}


def lorica_sources(*directories):
    return sorted(p for d in directories for p in (ROOT / d).rglob("*")
                  if p.suffix in (".hpp", ".cpp", ".c", ".h") and "analysis" not in p.parts)


class SelfApplicationTests(unittest.TestCase):
    """Lorica's own sources: every file parses, and the functions are exactly these.

    The expected names were read from the sources and cross-checked against
    clang-tidy-18 (readability-function-size reports every function with a body;
    the extra entries here are one-line empty-body constructors it does not print,
    and the Windows file, which it cannot compile on Linux)."""

    def test_no_unparsed_region_in_any_lorica_source(self):
        for path in lorica_sources("include", "src", "tests", "examples"):
            source = analyse_text(str(path), path.read_text(encoding="utf-8"))
            _, refused = analyse(source)
            with self.subTest(path=str(path.relative_to(ROOT))):
                self.assertEqual((source.unparsed, refused), ([], []))

    def test_function_names_in_include_and_src(self):
        found = {}
        for path in lorica_sources("include/lorica", "src"):
            relative = path.relative_to(ROOT).as_posix()
            found[relative] = names(analyse_text(relative, path.read_text(encoding="utf-8")))
        self.assertEqual(found, SELF_EXPECTED)

    def test_checked_add_after_the_macro_invocations(self):
        source = extract((ROOT / "include/lorica/checked_integer.hpp").read_text(encoding="utf-8"))
        add = [f for f in source.functions if f.name == "lorica::checked_add"][0]
        self.assertEqual(add.parameters, 2)
        self.assertIn("template", add.specifiers)


class RobustnessTests(unittest.TestCase):
    def test_random_and_truncated_input_never_raises(self):
        generator = random.Random(4242)
        alphabet = list("{}()[]<>;:,'\"\\/*#\n ") + ["if", "else", "for", "do", "while", "switch",
                                                     "case", "try", "catch", "class", "struct",
                                                     "namespace", "template", "operator", "requires",
                                                     "&&", "||", "?", "return", "x", "R\"(", ")\""]
        for _ in range(200):
            text = " ".join(generator.choice(alphabet) for _ in range(generator.randrange(300)))
            analyse(analyse_text("random.cpp", text))
        for path in lorica_sources("include", "src") + sorted(p for p in FIXTURES.iterdir() if p.is_file()):
            text = path.read_text(encoding="utf-8")
            for cut in range(0, len(text), max(1, len(text) // 40)):
                analyse(analyse_text(path.name, text[:cut]))

    def test_time_is_linear(self):
        unit = (FIXTURES / "complexity.cpp").read_text(encoding="utf-8").replace("#include <utility>", "")

        def seconds(copies):
            text = "\n".join("namespace n%d {\n%s\n}" % (k, unit) for k in range(copies))
            start = time.perf_counter()
            analyse(analyse_text("big.cpp", text))
            return time.perf_counter() - start
        small, large = seconds(20), seconds(160)
        self.assertLess(large, 8 * small * 3 + 0.5)    # 8x the input, within 3x of linear
        nested = "int f() {" + "{" * 2000 + "}" * 2000 + "}\n" + "a<" * 5000 + "\n"
        start = time.perf_counter()
        analyse(analyse_text("deep.cpp", nested))
        self.assertLess(time.perf_counter() - start, 5)

    @unittest.skipUnless(os.environ.get("LORICA_ANALYSIS_SYSTEM_HEADERS"),
                         "set LORICA_ANALYSIS_SYSTEM_HEADERS to a header tree, e.g. /usr/include/c++/13")
    def test_system_header_tree(self):
        start = time.perf_counter()
        for path in sorted(Path(os.environ["LORICA_ANALYSIS_SYSTEM_HEADERS"]).rglob("*")):
            if path.is_file() and not path.is_symlink():
                analyse(analyse_text(str(path), path.read_text(encoding="utf-8", errors="replace")))
        self.assertLess(time.perf_counter() - start, 120)


if __name__ == "__main__":
    unittest.main()
