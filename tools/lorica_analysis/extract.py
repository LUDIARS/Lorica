"""Function extraction that fails closed. @implements SPEC-LR-ANALYZE

Entry point: analyse_text(path, text) -> SourceFile. Nothing is compiled or
expanded: templates are read as written and macros are not expanded.

Pipeline: lexer -> preprocessor pre-pass -> bracket matching over the kept tokens
-> a scope scanner that classifies only each `{` met at declaration scope (file,
namespace, extern "C", class), using the head tokens since the previous `;`, `{`
or `}`: namespace / linkage / class / enum / function / initializer / unparsed.
Function bodies are never scanned as declarations.

Fail-closed contract: what the scanner cannot classify becomes an unparsed Region
(file, line, end_line, reason), raised when
  1. a skipped non-function brace block holds `;` or if/for/while/switch/return/do
     at its own depth (a class or function read as an initializer);
  2. a control keyword appears at namespace or class scope (a macro opened a body);
  3. bracket kinds mismatch, 4. a bracket is unclosed or a closer stray;
  5. a head has parentheses but no recognisable declarator (K&R definitions,
     functions returning function pointers);
  plus lexical errors and broken #if structure. A function whose lines overlap an
  unparsed region is dropped: no name or number is guessed for it. The complexity
  pass adds 6. its statement parser failing on a body.

Reading results: SourceFile.tokens is the kept token list, and SourceFile.match[i]
is the index of the bracket matching the ( [ { ) ] } at i, or -1. Function.body is
(open, close): the indices of the body's `{` and of the last `}` (the last handler
for a function-try-block). Walk a body with
    i = open + 1
    while i < close: ... skip a group with i = match[i] + 1 ...
Function.lambdas lists every lambda in the body, nested ones included, in source
order, each with the indices of its `[`, its parameter list and its body.
"""
import os
from typing import FrozenSet, List, NamedTuple, Optional, Tuple

from .lexer import CHAR, ERROR, IDENTIFIER, KEYWORD, NUMBER, PUNCT, STRING, Comment, Token, tokenize
from .preprocess import preprocess

HEADER_EXTENSIONS = frozenset((".h", ".hh", ".hpp", ".hxx", ".h++", ".inl", ".ipp", ".tcc", ".tpp"))


class Region(NamedTuple):
    file: str
    line: int
    end_line: int
    reason: str


class Lambda(NamedTuple):
    line: int
    introducer: int                        # index of `[`
    parameters: Optional[Tuple[int, int]]  # indices of `(` and `)`, or None
    body: Tuple[int, int]                  # indices of `{` and `}`


class Function(NamedTuple):
    name: str           # qualified: enclosing namespaces and classes, then the name as
                        # written; template arguments are dropped
    kind: str           # function, constructor, destructor, operator, lambda (a lambda
                        # bound to a variable at declaration scope, named after it) or
                        # macro-function (`TEST(a, b) {`, named by the macro text)
    file: str
    line: int           # line of the name
    start_line: int     # first line of the declaration (template head included)
    end_line: int       # line of the closing brace
    body_line: int      # line of the body's opening brace
    parameters: int     # 0 for macro-functions
    specifiers: FrozenSet[str]  # read from the head: constexpr consteval static inline
                        # virtual explicit friend template const noexcept override final
    in_class_body: bool
    in_header: bool     # by extension (HEADER_EXTENSIONS)
    in_unnamed_namespace: bool
    body: Tuple[int, int]
    lambdas: Tuple[Lambda, ...]


class SourceFile(NamedTuple):
    path: str
    tokens: List[Token]
    match: List[int]
    comments: List[Comment]
    functions: List[Function]
    unparsed: List[Region]
    not_analysed: List[Region]  # preprocessor branches the pre-pass dropped
    union_lines: List[int]      # directive lines of #if groups kept as a union


class _Item(NamedTuple):
    kind: str   # "tok", "(", "[", "{", "<" (template arguments) or "op" (operator name)
    text: str
    lo: int
    hi: int


_OPENERS = {"(": ")", "[": "]", "{": "}"}
_CLOSERS = {")": "(", "]": "[", "}": "{"}
_CONTROL = frozenset("if else for while do switch case return goto break continue catch".split())
_STATEMENT = frozenset("if for while switch return do".split())
_FOLLOWS = frozenset("const volatile noexcept override final -> : & && try throw = mutable".split())
_MACRO_CONTINUES = _FOLLOWS | {"{", ";", ",", "("}
_SPECIFIERS = frozenset("constexpr consteval static inline virtual explicit friend".split())
_SUFFIX_SPECIFIERS = frozenset("const noexcept override final".split())
_ATTRIBUTES = frozenset(("alignas", "__attribute__", "__attribute", "__declspec", "_Pragma"))
_NOT_SUBSCRIPTED = frozenset(
    "bool char char8_t char16_t char32_t double float int long short signed unsigned "
    "void wchar_t auto this delete operator".split())


def _macro_like(token: Token) -> bool:
    return token.kind == IDENTIFIER and token.text.isupper()


class _Scope(NamedTuple):
    kind: str   # file, namespace, linkage, class
    name: Optional[str]
    open: int


class _Extractor:
    def __init__(self, path: str, tokens: List[Token]) -> None:
        self.path, self.tokens = path, tokens
        self.match = [-1] * len(tokens)
        self.regions: List[Region] = []
        self.functions: List[Function] = []
        self.header = os.path.splitext(path)[1].lower() in HEADER_EXTENSIONS

    # -- bracket matching: properly nested pairs; every surprise is a region
    def _match_brackets(self) -> None:
        tokens, stack, open_kinds = self.tokens, [], {"(": 0, "[": 0, "{": 0}
        last = tokens[-1].line if tokens else 1
        for i, token in enumerate(tokens):
            if token.kind != PUNCT:
                if token.kind == ERROR:
                    self._region(token.line, token.line, "lexical error: " + token.text)
                continue
            if token.text in _OPENERS:
                stack.append(i)
                open_kinds[token.text] += 1
            elif token.text in _CLOSERS:
                want = _CLOSERS[token.text]
                if not open_kinds[want]:
                    self._region(token.line, token.line, "stray '%s'" % token.text)
                    continue
                while tokens[stack[-1]].text != want:
                    lost = stack.pop()
                    open_kinds[tokens[lost].text] -= 1
                    self._region(tokens[lost].line, token.line, "'%s' closed by '%s'"
                                 % (tokens[lost].text, token.text))
                opener = stack.pop()
                open_kinds[want] -= 1
                self.match[opener], self.match[i] = i, opener
        for lost in stack:
            self._region(tokens[lost].line, last, "unclosed '%s'" % tokens[lost].text)

    def _region(self, line: int, end_line: int, reason: str) -> None:
        self.regions.append(Region(self.path, line, end_line, reason))

    # -- scope scanner
    def run(self) -> None:
        self._match_brackets()
        tokens, match = self.tokens, self.match
        scopes = [_Scope("file", None, -1)]
        i, head, poison = 0, 0, None
        while i < len(tokens):
            token = tokens[i]
            text = token.text
            if token.kind == PUNCT and text in "([{" and match[i] < 0:
                i = head = i + 1        # already a region: unclosed or closed by another kind
                continue
            if token.kind == PUNCT and text in "([" and text:
                close = match[i]
                if i == head + 1 and self._macro_statement(i, close, scopes[-1]):
                    head = close + 1
                i = close + 1
                continue
            if token.kind == PUNCT and text == "{":
                if poison is not None:
                    self._region(tokens[poison].line, tokens[match[i]].line,
                                 "control keyword '%s' at %s scope" % (tokens[poison].text, scopes[-1].kind))
                    i = head = match[i] + 1
                    poison = None
                    continue
                i, head = self._brace(i, head, scopes)
                continue
            if token.kind == PUNCT and text in ";}":
                if poison is not None:
                    self._region(tokens[poison].line, token.line, "control keyword '%s' at %s scope"
                                 % (tokens[poison].text, scopes[-1].kind))
                    poison = None
                if text == "}" and len(scopes) > 1 and match[i] == scopes[-1].open:
                    scopes.pop()
                head = i + 1
            elif token.kind == KEYWORD:
                if text in _CONTROL and poison is None:
                    poison = i
                elif (text in ("public", "private", "protected") and scopes[-1].kind == "class"
                      and i + 1 < len(tokens) and tokens[i + 1].text == ":"):
                    i = head = i + 2
                    continue
            i += 1

    def _macro_statement(self, i: int, close: int, scope: _Scope) -> bool:
        # `NAME(...)` alone on its line(s) before a new declaration, as in
        # LORICA_REJECT_MIXED(checked_add): not part of the next head. A constructor
        # (the class's own name) is never one.
        name, after = self.tokens[i - 1], close + 1
        if name.kind != IDENTIFIER or (scope.kind == "class" and name.text == scope.name):
            return False
        return after >= len(self.tokens) or (
            self.tokens[after].line > self.tokens[close].line
            and self.tokens[after].text not in _MACRO_CONTINUES)

    def _brace(self, i: int, head: int, scopes: List[_Scope]):
        """Classify the `{` at i; returns (next index, next head start)."""
        tokens, close = self.tokens, self.match[i]
        kind, info = self._classify(head, i, scopes[-1])
        if kind in ("mem-init", "requires"):
            return close + 1, head          # part of the head; keep reading it
        if kind in ("namespace", "linkage", "class"):
            scopes.append(_Scope(kind, info, i))
            return i + 1, i + 1
        if kind in ("function", "lambda", "macro-function"):
            while (close + 2 < len(tokens) and tokens[close + 1].text == "catch"
                   and tokens[close + 2].text == "(" and self.match[close + 2] > 0
                   and tokens[self.match[close + 2] + 1].text == "{"
                   and self.match[self.match[close + 2] + 1] > 0):
                close = self.match[self.match[close + 2] + 1]  # function-try-block handler
            self._add_function(kind, info, head, i, close, scopes)
            return close + 1, close + 1
        if kind == "unparsed":
            self._region(tokens[head].line if head < i else tokens[i].line, tokens[close].line, info)
            return close + 1, close + 1
        statement = self._statement_inside(i, close)
        if statement is not None:
            self._region(tokens[i].line, tokens[close].line,
                         "brace block read as %s holds a statement at line %d" % (kind, statement))
        return close + 1, (head if kind in ("initializer", "enum") and statement is None else close + 1)

    def _statement_inside(self, open_: int, close: int) -> Optional[int]:
        k = open_ + 1
        while k < close:
            token = self.tokens[k]
            if token.kind == PUNCT and token.text in _OPENERS:
                k = self.match[k] + 1
                continue
            if (token.kind == PUNCT and token.text == ";") or (
                    token.kind == KEYWORD and token.text in _STATEMENT):
                return token.line
            k += 1
        return None

    # -- head classification
    def _items(self, lo: int, hi: int) -> List[_Item]:
        tokens, match, out, i = self.tokens, self.match, [], lo
        while i < hi:
            token = tokens[i]
            if token.kind == ERROR:
                i += 1
                continue
            if token.kind == PUNCT and token.text in _OPENERS and 0 <= match[i] < hi:
                out.append(_Item(token.text, token.text, i, match[i]))
                i = match[i] + 1
                continue
            if token.kind == KEYWORD and token.text == "operator":
                end = self._operator_end(i, hi)
                if end is not None:
                    out.append(_Item("op", self._spell(i, end[0]), i, end[1] - 1))
                    i = end[1]
                    continue
            if token.text == "<" and out and out[-1].kind == "tok" and (
                    tokens[out[-1].lo].kind == IDENTIFIER or out[-1].text == "template"):
                end = self._angle_end(i, hi)
                if end is not None:
                    out.append(_Item("<", "<>", i, end))
                    i = end + 1
                    continue
            out.append(_Item("tok", token.text, i, i))
            i += 1
        return out

    def _angle_end(self, i: int, hi: int) -> Optional[int]:
        depth, k = 0, i
        while k < hi:
            text = self.tokens[k].text
            if text in "([" and self.tokens[k].kind == PUNCT and 0 <= self.match[k] < hi:
                k = self.match[k] + 1
                continue
            if text == "<":
                depth += 1
            elif text in (">", ">>"):
                depth -= len(text)
                if depth <= 0:
                    return k
            elif text in ("{", "}", ";", ")", "]"):
                return None
            k += 1
        return None

    def _operator_end(self, i: int, hi: int) -> Optional[Tuple[int, int]]:
        """(end of the name, index of the parameter list's `(`) after `operator`."""
        tokens, k = self.tokens, i + 1
        if k + 1 < hi and tokens[k].text in "([" and self.match[k] == k + 1:
            k += 2                          # operator() and operator[]
        elif k < hi and tokens[k].kind == PUNCT and tokens[k].text != "(":
            k += 1                          # operator<=>, operator<<, ...
        else:                               # conversion, new[], delete, ""_x, co_await
            while k < hi and tokens[k].text != "(" and not self._attribute(k):
                if tokens[k].text in ("{", ";", "}"):
                    return None
                if tokens[k].text == "<":
                    end = self._angle_end(k, hi)
                    k = k if end is None else end
                k += 1
        name_end = k
        while k < hi and self._attribute(k):
            k = self.match[k] + 1           # operator== [[nodiscard]] (...)
        return (name_end, k) if k < hi and tokens[k].text == "(" else None

    def _attribute(self, k: int) -> bool:
        return (self.tokens[k].text == "[" and k + 1 < len(self.tokens)
                and self.tokens[k + 1].text == "[" and self.match[k] > k)

    def _spell(self, lo: int, hi: int) -> str:
        pieces = []
        for token in self.tokens[lo:hi]:
            if pieces and (pieces[-1][-1].isalnum() or pieces[-1][-1] == "_") and (
                    token.text[0].isalnum() or token.text[0] in "_\"'"):
                pieces.append(" ")
            pieces.append(token.text)
        return "".join(pieces)

    def _strip(self, items: List[_Item]):
        """Drop attributes, template heads and requires-clauses; report a template head."""
        out, template, k = [], False, 0
        while k < len(items):
            item = items[k]
            following = items[k + 1] if k + 1 < len(items) else None
            if item.kind == "tok" and item.text == "template" and following and following.kind == "<":
                template, k = True, k + 2
            elif item.kind == "[" and self.tokens[item.lo + 1].text == "[":
                k += 1                              # [[attribute]]
            elif item.kind == "tok" and item.text in _ATTRIBUTES and following and following.kind == "(":
                k += 2
            elif item.kind == "tok" and item.text == "requires":
                k = self._constraint_end(items, k + 1)
            else:
                out.append(item)
                k += 1
        return out, template

    def _constraint_end(self, items: List[_Item], k: int) -> int:
        while k < len(items):
            item = items[k]
            if item.kind == "tok" and item.text == "requires":      # requires-expression
                k += 1
                for kind in ("(", "{"):
                    if k < len(items) and items[k].kind == kind:
                        k += 1
            elif item.kind == "(":
                k += 1
            elif item.kind == "tok" and self.tokens[item.lo].kind in (IDENTIFIER, KEYWORD) \
                    or item.text == "::":
                while k < len(items) and (items[k].kind == "<" or items[k].text == "::" or (
                        items[k].kind == "tok" and self.tokens[items[k].lo].kind == IDENTIFIER)
                        or items[k].text in ("true", "false")):
                    k += 1
                    if items[k - 1].kind == "tok" and k < len(items) and items[k].kind == "tok" \
                            and items[k - 1].text != "::" and items[k].text != "::":
                        break   # two names in a row: the constraint ended
            else:
                break
            if k < len(items) and items[k].text in ("&&", "||"):
                k += 1
                continue
            break
        return k

    def _classify(self, head: int, brace: int, scope: _Scope):
        tokens = self.tokens
        items = self._items(head, brace)
        if items and items[-1].text == "requires" or (
                len(items) >= 2 and items[-1].kind == "(" and items[-2].text == "requires"
                and (len(items) == 2 or self._in_expression(items[-3]))):
            return "requires", None
        sig, template = self._strip(items)
        if not sig:
            return "block", None
        texts = [item.text if item.kind == "tok" else item.kind for item in sig]
        words = [tokens[item.lo] for item in sig]
        if "namespace" in texts and "=" not in texts:
            at = texts.index("namespace")
            if all(t.kind == IDENTIFIER or t.text in ("inline", "export") for t in words[:at]):
                return "namespace", self._namespace_name(sig[at + 1:])
        if len(sig) == 2 and texts[0] == "extern" and words[1].kind == STRING:
            return "linkage", None
        keys = [k for k, t in enumerate(texts) if t in ("class", "struct", "union")
                and words[k].kind == KEYWORD and (k == 0 or texts[k - 1] != "enum")]
        bases = next((k for k in range(keys[0] + 1, len(sig)) if texts[k] == ":"), len(sig)) \
            if keys else 0
        if keys and "=" not in texts and not any(
                sig[k].kind == "(" and not _macro_like(words[k - 1])
                for k in range(keys[0] + 1, bases)):
            return "class", self._class_name(sig[keys[0] + 1:])
        if "enum" in texts and "(" not in texts:
            return "enum", None
        if "=" in texts:
            at = texts.index("=")
            if at + 1 < len(sig) and sig[at + 1].kind == "[" and at > 0 and words[at - 1].kind == IDENTIFIER:
                return "lambda", (at - 1, sig)
        if "(" not in texts:
            return "initializer", None
        strong = weak = None
        for k, item in enumerate(sig):
            if item.kind == "tok" and item.text in ("=", ":", "->"):
                break
            if item.kind != "(" or k == 0:
                continue
            before = sig[k - 1]
            if not (before.kind in ("op", "<") or (before.kind == "tok" and words[k - 1].kind == IDENTIFIER)):
                continue
            after = sig[k + 1] if k + 1 < len(sig) else None
            if after is None or (after.kind == "tok" and after.text in _FOLLOWS):
                strong = k
                break
            if weak is None and after.kind == "tok" and _macro_like(words[k + 1]):
                weak = k
        at = strong if strong is not None else weak
        if at is None:
            if "=" in texts and texts.index("=") < texts.index("("):
                return "initializer", None
            return "unparsed", "declaration head has parentheses but no declarator"
        rest = texts[at + 1:]
        if "," in rest[:rest.index(":") if ":" in rest else len(rest)]:
            return "initializer", None      # a declarator list
        if ":" in rest and tokens[brace - 1].text not in (")", "}", "..."):
            return "mem-init", None         # a brace in a constructor's initializer list
        return "function", (at, sig, template)

    def _in_expression(self, item: _Item) -> bool:
        """`requires (` after this item starts a requires-expression, not a clause."""
        return item.kind == "tok" and (item.text in ("requires", "return") or (
            self.tokens[item.lo].kind == PUNCT and item.text not in (">", ">>")))

    def _namespace_name(self, rest: List[_Item]) -> Optional[str]:
        parts, expect_name = [], True
        for item in rest:
            token = self.tokens[item.lo]
            if item.kind == "tok" and token.text == "inline":
                continue
            if expect_name and item.kind == "tok" and token.kind == IDENTIFIER:
                parts.append(token.text)
                expect_name = False
            elif not expect_name and item.text == "::":
                expect_name = True
            else:
                break
        return "::".join(parts) or None

    def _class_name(self, rest: List[_Item]) -> Optional[str]:
        end = next((k for k, item in enumerate(rest) if item.text in (":", "final")), len(rest))
        names = [k for k in range(end) if rest[k].kind == "tok" and self.tokens[rest[k].lo].kind == IDENTIFIER]
        if not names:
            return None
        k, parts = names[-1], [rest[names[-1]].text]
        while k >= 2 and rest[k - 1].text == "::" and rest[k - 2].kind in ("tok", "<"):
            k -= 2 if rest[k - 2].kind == "tok" else 3
            if k < 0 or self.tokens[rest[k].lo].kind != IDENTIFIER:
                break
            parts.append(rest[k].text)
        return "::".join(reversed(parts))

    # -- function records
    def _add_function(self, kind: str, info, head: int, brace: int, close: int,
                      scopes: List[_Scope]) -> None:
        tokens = self.tokens
        scope_names = [s.name or "(anonymous namespace)" for s in scopes if s.kind == "namespace"
                       or (s.kind == "class" and s.name)]
        in_class = scopes[-1].kind == "class"
        if kind == "lambda":
            at, sig = info
            name_item, parameters, specifiers = sig[at], 0, frozenset()
            name = sig[at].text
            for lam in self._lambdas(sig[at + 2].lo - 1, brace + 1):
                parameters = self._count_parameters(*lam.parameters) if lam.parameters else 0
                break
        else:
            at, sig, template = info
            name, first = self._name(sig, at)
            name_item = sig[at - 1]
            prefix = [item.text for item in sig[:first] if item.kind == "tok"]
            last = scopes[-1].name if in_class else None
            short = name.split("::")
            if (not prefix and len(short) == 1 and sig[at - 1].kind == "tok" and name != last
                    and not name.startswith("~")):
                kind, name = "macro-function", self._spell(sig[at - 1].lo, sig[at].hi + 1)
                parameters = 0
            else:
                if short[-1].startswith("~"):
                    kind = "destructor"
                elif sig[at - 1].kind == "op" or (sig[at - 1].kind == "<" and sig[at - 2].kind == "op"):
                    kind = "operator"
                elif short[-1] == (short[-2] if len(short) > 1 else last):
                    kind = "constructor"
                parameters = self._count_parameters(sig[at].lo, sig[at].hi)
            suffix = []
            for item in sig[at + 1:]:
                if item.text in ("->", ":", "=", "try"):
                    break
                if item.kind == "(" and suffix and suffix[-1] == "noexcept" and \
                        self._spell(item.lo + 1, item.hi) == "false":
                    suffix.pop()
                suffix.append(item.text)
            specifiers = frozenset((_SPECIFIERS & set(prefix)) | (_SUFFIX_SPECIFIERS & set(suffix))
                                   | ({"template"} if template else set()))
        self.functions.append(Function(
            "::".join(scope_names + [name]), kind, self.path, tokens[name_item.lo].line,
            tokens[head].line, tokens[close].line, tokens[brace].line, parameters, specifiers, in_class, self.header,
            any(s.kind == "namespace" and s.name is None for s in scopes),
            (brace, close), tuple(self._lambdas(brace, close))))

    def _name(self, sig: List[_Item], at: int):
        """(name as written without template arguments, index of its first item)."""
        k = at - 1
        if sig[k].kind == "<":
            k -= 1
        parts = [sig[k].text]
        if k > 0 and sig[k - 1].text == "~":
            parts[0], k = "~" + parts[0], k - 1
        while k >= 2 and sig[k - 1].text == "::":
            j = k - 2
            if sig[j].kind == "<":
                j -= 1
            if j < 0 or sig[j].kind != "tok" or self.tokens[sig[j].lo].kind != IDENTIFIER:
                break
            parts.append(sig[j].text)
            k = j
        if k > 0 and sig[k - 1].text == "::":
            k -= 1                          # ::f, a global qualifier
        return "::".join(reversed(parts)), k

    def _count_parameters(self, open_: int, close: int) -> int:
        tokens = self.tokens
        if close == open_ + 1 or (close == open_ + 2 and tokens[open_ + 1].text == "void"):
            return 0
        count, angle, start, k = 1, 0, open_ + 1, open_ + 1
        while k < close:
            token = tokens[k]
            if token.kind == PUNCT and token.text in _OPENERS:
                k = self.match[k] + 1
                continue
            if token.text == "<" and tokens[k - 1].kind == IDENTIFIER:
                angle += 1
            elif token.text in (">", ">>") and angle:
                angle = max(0, angle - len(token.text))
            elif token.text == "," and not angle:
                count, start = count + 1, k + 1
            k += 1
        return count - (1 if close == start + 1 and tokens[start].text == "..." and count > 1 else 0)

    def _lambdas(self, open_: int, close: int) -> List[Lambda]:
        tokens, match, found = self.tokens, self.match, []
        for k in range(open_ + 1, close):
            token = tokens[k]
            if token.kind != PUNCT or token.text != "[" or not k < match[k] < close:
                continue
            before, inner = tokens[k - 1], tokens[k + 1]
            if inner.text == "[" or before.text == "[" or before.kind in (IDENTIFIER, NUMBER, STRING, CHAR) \
                    or (before.kind == PUNCT and before.text in (")", "]", ">")) \
                    or (before.kind == KEYWORD and before.text in _NOT_SUBSCRIPTED):
                continue
            j, parameters = match[k] + 1, None
            if j < close and tokens[j].text == "<":
                end = self._angle_end(j, close)
                j = j if end is None else end + 1
            if j < close and tokens[j].text == "(":
                parameters, j = (j, match[j]), match[j] + 1
            while j < close:
                text = tokens[j].text
                if text == "{" and tokens[j].kind == PUNCT:
                    found.append(Lambda(token.line, k, parameters, (j, match[j])))
                    break
                if text in "([" and tokens[j].kind == PUNCT:
                    j = match[j] + 1
                    continue
                if text in (";", ",", ")", "]", "}", "="):
                    break
                j += 1
        return found


def _merge(regions: List[Region]) -> List[Region]:
    merged: List[Region] = []
    extra = 0
    for region in sorted(set(regions), key=lambda r: (r.line, r.end_line)):
        if merged and region.line <= merged[-1].end_line + 1:
            last = merged[-1]
            extra += 1
            merged[-1] = last._replace(end_line=max(last.end_line, region.end_line),
                                       reason=last.reason.split(" (+")[0] + " (+%d more)" % extra)
        else:
            merged.append(region)
            extra = 0
    return merged


def analyse_text(path: str, text: str) -> SourceFile:
    """Extract the functions of one file; never raises for any text."""
    lexed = tokenize(text)
    pre = preprocess(lexed)
    extractor = _Extractor(path, pre.tokens)
    extractor.run()
    regions = _merge(extractor.regions + [Region(path, *p) for p in pre.problems])
    functions = [f for f in extractor.functions
                 if not any(r.line <= f.end_line and f.start_line <= r.end_line for r in regions)]
    return SourceFile(path, pre.tokens, extractor.match, lexed.comments, functions, regions,
                      [Region(path, *r) for r in pre.not_analysed], pre.union_lines)
