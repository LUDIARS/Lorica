"""C++ tokenizer for the source analyzer. @implements SPEC-LR-ANALYZE

tokenize(text) never raises. Text that starts no token, an unterminated literal
and an unterminated block comment become ERROR tokens whose text is the message;
the extractor turns every surviving ERROR token into an unparsed region.

Tokens (Token(kind, text, line, column); 1-based physical position of the first
character):
    IDENTIFIER   names, including contextual keywords (final, override, import)
    KEYWORD      the C++23 keywords
    NUMBER       a pp-number: 1'000, 1e+5, 10ms and 0x1Fu are one token each
    STRING, CHAR the whole literal with prefix, raw delimiters and ud-suffix
    PUNCT        longest match (->*, <=>, ::); ">>" stays one token. Alternative
                 tokens use their primary spelling ("and" is "&&", "<%" is "{").
    ERROR        see above

Directives are not tokens: each logical directive line is a Directive in a side
channel, with `index` = the number of tokens before it, so a #define body is never
read as code. Comments are kept separately with their lines (for suppressions).
Backslash-newline is removed everywhere except inside raw strings, as in C++.
"""
import bisect
import re
from typing import List, NamedTuple

IDENTIFIER, KEYWORD, NUMBER, STRING, CHAR, PUNCT, ERROR = (
    "identifier", "keyword", "number", "string", "char", "punct", "error")


class Token(NamedTuple):
    kind: str
    text: str
    line: int
    column: int


class Directive(NamedTuple):
    name: str       # "if", "define", ... ("" for a null directive)
    text: str       # whole logical line, comments removed, splices joined
    line: int
    end_line: int
    index: int      # number of tokens before the directive


class Comment(NamedTuple):
    line: int
    end_line: int
    text: str       # including the // or /* */ markers


class LexResult(NamedTuple):
    tokens: List[Token]
    directives: List[Directive]
    comments: List[Comment]


KEYWORDS = frozenset("""
alignas alignof asm auto bool break case catch char char8_t char16_t char32_t class
concept const consteval constexpr constinit const_cast continue co_await co_return
co_yield decltype default delete do double dynamic_cast else enum explicit export
extern false float for friend goto if inline int long mutable namespace new noexcept
nullptr operator private protected public register reinterpret_cast requires return
short signed sizeof static static_assert static_cast struct switch template this
thread_local throw true try typedef typeid typename union unsigned using virtual void
volatile wchar_t while
""".split())
_ALTERNATIVE_WORDS = {
    "and": "&&", "and_eq": "&=", "bitand": "&", "bitor": "|", "compl": "~", "not": "!",
    "not_eq": "!=", "or": "||", "or_eq": "|=", "xor": "^", "xor_eq": "^=",
}
_DIGRAPHS = {"<%": "{", "%>": "}", "<:": "[", ":>": "]", "%:": "#", "%:%:": "##"}
_MAX_ERRORS = 100  # binary garbage must not become a million tokens

_WORD = "A-Za-z_$\u0080-\U0010ffff"
_SCAN = re.compile(r"""
    (?P<space>[ \t\f\v\r]+)
  | (?P<newline>\n)
  | (?P<line_comment>//[^\n]*)
  | (?P<block_comment>/\*)
  | (?P<raw>(?:u8|[uUL])?R")
  | (?P<string>(?:u8|[uUL])?")
  | (?P<char>(?:u8|[uUL])?')
  | (?P<number>\.?[0-9](?:[eEpP][+-]|'[0-9A-Za-z_]|[0-9A-Za-z_.])*)
  | (?P<word>[%(w)s][%(w)s0-9]*)
  | (?P<punct>%%:%%:|<=>|->\*|\.\.\.|<<=|>>=
        |<:(?!:(?![:>]))|<%%|%%>|:>|%%:            # "<::" is "<" "::" ([lex.pptoken])
        |::|->|\.\*|\+\+|--|<<|>>|<=|>=|==|!=|&&|\|\||\+=|-=|\*=|/=|%%=|&=|\|=|\^=|\#\#
        |[{}\[\]()<>;:,.?~!+\-*/%%^&|=\#])
""" % {"w": _WORD}, re.VERBOSE)
_STRING_REST = re.compile(r'(?:[^"\\\n]|\\[^\n])*"')
_CHAR_REST = re.compile(r"(?:[^'\\\n]|\\[^\n])*'")
_SUFFIX = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_RAW_DELIMITER = re.compile(r'([^ ()\\\t\v\f\n]{0,16})\(')
_DIRECTIVE_PART = re.compile(r"""
    (?P<line_comment>//[^\n]*)
  | (?P<block_comment>/\*)
  | (?P<literal>"(?:[^"\\\n]|\\[^\n])*"|'(?:[^'\\\n]|\\[^\n])*')
  | (?P<text>[^\n/"']+|[/"'])
""", re.VERBOSE)
_DIRECTIVE_NAME = re.compile(r"#\s*([A-Za-z_]\w*)?")


class _Lines:
    """The text with line splices removed, and the way back to physical lines."""

    def __init__(self, text: str) -> None:
        self.original = text
        self.starts, self.originals, pieces = [], [], []
        offset = position = 0
        lines = text.split("\n")
        for number, line in enumerate(lines):
            self.starts.append(offset)
            self.originals.append(position)
            position += len(line) + 1
            if number != len(lines) - 1:
                line = line[:-1] if line.endswith("\\") else line + "\n"
            pieces.append(line)
            offset += len(line)
        self.text = "".join(pieces)

    def location(self, offset: int):
        index = bisect.bisect_right(self.starts, offset) - 1
        return index + 1, offset - self.starts[index] + 1

    def to_original(self, offset: int) -> int:
        index = bisect.bisect_right(self.starts, offset) - 1
        return self.originals[index] + offset - self.starts[index]

    def from_original(self, position: int) -> int:
        index = bisect.bisect_right(self.originals, position) - 1
        return self.starts[index] + position - self.originals[index]


class _Lexer:
    def __init__(self, text: str) -> None:
        self.lines = _Lines(text.replace("\r\n", "\n"))
        self.text = self.lines.text
        self.result = LexResult([], [], [])
        self.errors = 0

    def run(self) -> LexResult:
        text, position, line_start = self.text, 0, True
        while position < len(text):
            found = _SCAN.match(text, position)
            if found is None:
                position = self._error(position, position + 1, "unexpected character")
                line_start = False
                continue
            kind, stop = found.lastgroup, found.end()
            if kind == "space":
                position = stop
            elif kind == "newline":
                position, line_start = stop, True
            elif kind == "line_comment":
                position = self._comment(position, stop)
            elif kind == "block_comment":
                close = text.find("*/", position + 2)
                position = (self._error(position, len(text), "unterminated /* comment")
                            if close < 0 else self._comment(position, close + 2))
            elif kind == "punct" and line_start and found.group() in ("#", "%:"):
                position = self._directive(position)
            else:
                position, line_start = self._token(kind, position, stop), False
        return self.result

    def _add(self, kind: str, start: int, text: str) -> None:
        line, column = self.lines.location(start)
        self.result.tokens.append(Token(kind, text, line, column))

    def _error(self, start: int, stop: int, message: str) -> int:
        self.errors += 1
        if self.errors <= _MAX_ERRORS:
            self._add(ERROR, start, message)
        return stop

    def _comment(self, start: int, stop: int) -> int:
        self.result.comments.append(Comment(self.lines.location(start)[0],
                                            self.lines.location(stop - 1)[0],
                                            self.text[start:stop]))
        return stop

    def _token(self, kind: str, start: int, stop: int) -> int:
        text = self.text[start:stop]
        if kind == "word":
            if text in _ALTERNATIVE_WORDS:
                self._add(PUNCT, start, _ALTERNATIVE_WORDS[text])
            else:
                self._add(KEYWORD if text in KEYWORDS else IDENTIFIER, start, text)
        elif kind == "punct":
            self._add(PUNCT, start, _DIGRAPHS.get(text, text))
        elif kind == "number":
            self._add(NUMBER, start, text)
        elif kind == "raw":
            return self._raw_string(start, stop)
        else:
            rest = (_STRING_REST if kind == "string" else _CHAR_REST).match(self.text, stop)
            if rest is None:
                end = self.text.find("\n", stop)
                return self._error(start, len(self.text) if end < 0 else end,
                                   "unterminated %s literal" % kind)
            stop = self._suffix(rest.end())
            self._add(STRING if kind == "string" else CHAR, start, self.text[start:stop])
        return stop

    def _suffix(self, stop: int) -> int:
        found = _SUFFIX.match(self.text, stop)
        return found.end() if found else stop

    def _raw_string(self, start: int, quote_end: int) -> int:
        # Read from the unspliced text: splicing is reverted inside raw strings, and a
        # splice could otherwise fake the closing )delimiter".
        original = self.lines.original
        opening = self.lines.to_original(quote_end)
        delimiter = _RAW_DELIMITER.match(original, opening)
        if delimiter is None:
            return self._error(start, quote_end, "invalid raw string delimiter")
        close = original.find(")" + delimiter.group(1) + '"', delimiter.end())
        if close < 0:
            return self._error(start, len(self.text), "unterminated raw string literal")
        end = close + len(delimiter.group(1)) + 2
        after = self.lines.from_original(end)
        stop = self._suffix(after)
        self._add(STRING, start, self.text[start:quote_end] + original[opening:end]
                  + self.text[after:stop])
        return stop

    def _directive(self, start: int) -> int:
        # To the end of the logical line; a block comment may carry it across lines.
        text, parts, position = self.text, [], start
        while position < len(text) and text[position] != "\n":
            found = _DIRECTIVE_PART.match(text, position)
            kind, stop = found.lastgroup, found.end()
            if kind == "line_comment":
                position = self._comment(position, stop)
            elif kind == "block_comment":
                close = text.find("*/", position + 2)
                if close < 0:
                    position = self._error(position, len(text), "unterminated /* comment")
                else:
                    position = self._comment(position, close + 2)
                    parts.append(" ")
            else:
                parts.append(found.group())
                position = stop
        spelling = "".join(parts).strip()
        if spelling.startswith("%:"):
            spelling = "#" + spelling[2:]
        name = _DIRECTIVE_NAME.match(spelling)
        self.result.directives.append(Directive(
            (name.group(1) or "") if name else "", spelling, self.lines.location(start)[0],
            self.lines.location(max(start, position - 1))[0], len(self.result.tokens)))
        return position


def tokenize(text: str) -> LexResult:
    """Tokens in source order, directives and comments in their side channels."""
    return _Lexer(text).run()
