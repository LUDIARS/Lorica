"""Lexer: literals, directives in a side channel, comments, robustness."""
import random
import unittest

import support  # noqa: F401
from lorica_analysis.lexer import CHAR, ERROR, NUMBER, PUNCT, STRING, tokenize


def texts(source):
    return [t.text for t in tokenize(source).tokens]


class LiteralTests(unittest.TestCase):
    def test_raw_string_with_braces_and_quotes(self):
        lexed = tokenize('auto s = R"x( { " )" } )x"; int f() {}')
        strings = [t for t in lexed.tokens if t.kind == STRING]
        self.assertEqual([t.text for t in strings], ['R"x( { " )" } )x"'])
        self.assertEqual(texts('R"x( { " )" } )x"; int f() {}')[1:], [";", "int", "f", "(", ")", "{", "}"])

    def test_raw_string_keeps_a_line_splice_and_its_lines(self):
        lexed = tokenize('auto s = u8R"(a\\\nb)";\nint x;')
        self.assertEqual(lexed.tokens[3].text, 'u8R"(a\\\nb)"')
        self.assertEqual(lexed.tokens[-2].line, 3)

    def test_digit_separators_and_character_literals(self):
        lexed = tokenize("int a = 1'000'000 + '{' + '\\'' + 0x1F'FFu + 1e+5;")
        kinds = [(t.kind, t.text) for t in lexed.tokens if t.kind in (NUMBER, CHAR)]
        self.assertEqual(kinds, [(NUMBER, "1'000'000"), (CHAR, "'{'"), (CHAR, "'\\''"),
                                 (NUMBER, "0x1F'FFu"), (NUMBER, "1e+5")])
        self.assertNotIn("{", texts("int a = '{';"))

    def test_alternative_tokens_and_digraphs(self):
        self.assertEqual(texts("a and b or not c <% %>"), ["a", "&&", "b", "||", "!", "c", "{", "}"])
        self.assertEqual(texts("a<::b> x;"), ["a", "<", "::", "b", ">", "x", ";"])

    def test_unterminated_literals_are_errors_not_exceptions(self):
        for source in ('"abc\nint x;', "'a\nint y;", 'R"x(never closed', "/* open"):
            with self.subTest(source=source):
                self.assertIn(ERROR, [t.kind for t in tokenize(source).tokens])


class DirectiveAndCommentTests(unittest.TestCase):
    def test_define_body_is_never_tokenised(self):
        lexed = tokenize("#define BEGIN_FN(name) int name(int a) { \\\n    if (a) {\nint x;\n")
        self.assertEqual(texts("#define BEGIN_FN(name) int name(int a) { \\\n    if (a) {\nint x;\n"),
                         ["int", "x", ";"])
        directive = lexed.directives[0]
        self.assertEqual((directive.name, directive.line, directive.end_line, directive.index),
                         ("define", 1, 2, 0))

    def test_directive_position_in_the_token_stream(self):
        lexed = tokenize("int a;\n#if X\nint b;\n#endif\n")
        self.assertEqual([(d.name, d.index) for d in lexed.directives], [("if", 3), ("endif", 6)])

    def test_block_comment_starting_on_a_directive_line_continues_it(self):
        lexed = tokenize("#define A 1 /* start\n end */ int y;\nint z;")
        self.assertEqual(texts("#define A 1 /* start\n end */ int y;\nint z;"), ["int", "z", ";"])
        self.assertEqual(lexed.directives[0].end_line, 2)
        self.assertEqual([c.line for c in lexed.comments], [1])

    def test_line_spliced_line_comment(self):
        lexed = tokenize("// comment \\\nint hidden;\nint shown;")
        self.assertEqual([t.text for t in lexed.tokens], ["int", "shown", ";"])
        self.assertEqual((lexed.comments[0].line, lexed.comments[0].end_line), (1, 2))
        self.assertEqual(lexed.tokens[0].line, 3)

    def test_hash_inside_a_line_is_not_a_directive(self):
        lexed = tokenize("int a = b # c;\n  # pragma once\n")
        self.assertEqual([d.name for d in lexed.directives], ["pragma"])
        self.assertIn("#", [t.text for t in lexed.tokens if t.kind == PUNCT])

    def test_comments_keep_their_lines(self):
        lexed = tokenize("int f(); // lorica-analyze: ignore(cognitive) why\n/* a\n b */")
        self.assertEqual([(c.line, c.end_line) for c in lexed.comments], [(1, 1), (2, 3)])
        self.assertTrue(lexed.comments[0].text.startswith("// lorica-analyze"))


class RobustnessTests(unittest.TestCase):
    def test_random_bytes_never_raise(self):
        generator = random.Random(1213)
        alphabet = "{}()[]<>;:,'\"\\/*#R\nu8 aZ_09.=&|?!\t\x00\x7fé�"
        for _ in range(300):
            text = "".join(generator.choice(alphabet) for _ in range(generator.randrange(400)))
            tokenize(text)
            tokenize(bytes(generator.randrange(256) for _ in range(200)).decode("utf-8", "replace"))

    def test_error_tokens_are_capped(self):
        self.assertLessEqual(len(tokenize("\x01" * 100000).tokens), 100)


if __name__ == "__main__":
    unittest.main()
