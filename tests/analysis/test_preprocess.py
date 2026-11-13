"""Preprocessor pre-pass: union of bracket-neutral branches, else the first live one."""
import unittest

from support import extract, measured
from lorica_analysis.complexity import ALL_BRANCHES
from lorica_analysis.lexer import tokenize
from lorica_analysis.preprocess import preprocess


def kept(source):
    return [t.text for t in preprocess(tokenize(source)).tokens]


class GroupTests(unittest.TestCase):
    def test_neutral_branches_are_kept_as_a_union(self):
        result = preprocess(tokenize("#if A\nint a;\n#elif B\nint b;\n#else\nint c;\n#endif\n"))
        self.assertEqual([t.text for t in result.tokens], ["int", "a", ";", "int", "b", ";", "int", "c", ";"])
        self.assertEqual(result.not_analysed, [])
        self.assertEqual(result.union_lines, [1, 3, 5, 7])

    def test_unbalanced_branches_keep_the_first_live_one(self):
        result = preprocess(tokenize("#if A\nf(a,\n#else\nf(b,\n#endif\nc);\n"))
        self.assertEqual([t.text for t in result.tokens], ["f", "(", "a", ",", "c", ")", ";"])
        self.assertEqual([r[:2] for r in result.not_analysed], [(4, 4)])
        self.assertEqual(result.union_lines, [])

    def test_if_zero_is_dropped_even_when_unbalanced(self):
        result = preprocess(tokenize("#if 0\nint broken( {\n#endif\nint x;\n"))
        self.assertEqual([t.text for t in result.tokens], ["int", "x", ";"])
        self.assertEqual(result.not_analysed, [(2, 2, "#if 0 branch")])
        result = preprocess(tokenize("#if 0\nint a(;\n#else\nint b;\n#endif\n"))
        self.assertEqual([t.text for t in result.tokens], ["int", "b", ";"])

    def test_nested_groups_resolve_innermost_first(self):
        self.assertEqual(kept("#if A\n#if B\n{\n#else\n{ {\n#endif\n}\n#endif\n"), ["{", "}"])

    def test_broken_conditional_structure_is_a_problem(self):
        self.assertEqual(preprocess(tokenize("int a;\n#endif\n")).problems, [(2, 2, "#endif without #if")])
        problems = preprocess(tokenize("#ifdef X\nint a;\n")).problems
        self.assertEqual(problems, [(1, 2, "unterminated #ifdef")])


class FixtureTests(unittest.TestCase):
    """fixtures/preprocess.cpp: the shapes of the review (vector.tcc, chrono.h, stl_algo.h)."""

    @classmethod
    def setUpClass(cls):
        cls.source = extract("preprocess.cpp")
        cls.metrics, cls.refused = measured(cls.source)

    def test_every_function_survives(self):
        self.assertEqual([(f.name, f.line, f.parameters) for f in self.source.functions], [
            ("split_head", 3, 1), ("split_arguments", 11, 2), ("split_else", 21, 1),
            ("balanced_in_body", 39, 1), ("after_all", 48, 1)])
        self.assertEqual(self.source.unparsed, [])
        self.assertEqual(self.refused, [])

    def test_dropped_branches_are_reported_as_not_analysed(self):
        self.assertEqual([(r.line, r.end_line) for r in self.source.not_analysed], [(5, 5), (16, 16), (36, 36)])
        self.assertIn("brackets unbalanced across the #if at line 2", self.source.not_analysed[0].reason)
        self.assertEqual(self.source.not_analysed[2].reason, "#if 0 branch")

    def test_first_branch_counted_where_brackets_differ(self):
        head = [t.text for t in self.source.tokens[:self.source.functions[0].body[0]]]
        self.assertEqual(head, ["int", "split_head", "(", "long", "a", ")"])  # #ifdef WIDE
        self.assertEqual(self.metrics["split_arguments"].cyclomatic, 2)
        self.assertEqual(self.metrics["split_else"].cognitive, 2)   # if + else of the FAST shape
        self.assertEqual(self.metrics["split_else"].label, "")

    def test_union_is_labelled_on_the_function(self):
        metrics = self.metrics["balanced_in_body"]
        self.assertEqual((metrics.cyclomatic, metrics.cognitive, metrics.label), (3, 2, ALL_BRANCHES))
        self.assertEqual(self.metrics["after_all"].label, "")


if __name__ == "__main__":
    unittest.main()
