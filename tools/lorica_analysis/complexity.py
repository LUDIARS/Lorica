"""Complexity metrics of extracted function bodies. @implements SPEC-LR-ANALYZE

measure(source, function) parses the body with a small statement parser (compound,
if/else, for, while, do, switch, case, try/catch, labels, lambdas; everything else
is expression tokens) and returns Metrics, or raises ParseError. Only the body is
read: noexcept(...), requires and default arguments in the head are not counted.
Lambda bodies and local-class member functions count toward the enclosing function.

cyclomatic  1 + if + else if + for + while + do (once, not again for its while)
            + case + catch + ?: + each logical && || (and, or); default, else,
            goto and switch add nothing. A && that declares a reference is no
            operator (see _declarator).
cognitive   SonarSource B1/B2/B3 without the recursion increment, as clang-tidy's
            readability-function-cognitive-complexity applies them:
            +1 plus the nesting level for if, ?:, switch, for, while, do, catch;
            +1 for else if, else, goto and each logical-operator sequence (a run
            of the same operator in the expression tree: `a && b || c` is 2,
            `a && b && c` is 1, `a || b && c || d` is 2); the bodies of those
            statements and lambdas nest one level deeper. A fold over && or ||
            counts as one operator.
nesting     deepest nesting level of a statement or lambda body (the cognitive
            nesting level, without ?:)
parameters  from the declarator
nloc        lines from the declaration to the closing brace that hold code
"""
import bisect
from typing import List, NamedTuple, Tuple

from .extract import Function, Region, SourceFile
from .lexer import IDENTIFIER, KEYWORD, PUNCT

METRICS = ("cyclomatic", "cognitive", "nesting", "parameters", "nloc")
ALL_BRANCHES = "all preprocessor branches counted"


class Contribution(NamedTuple):
    line: int
    metric: str     # "cyclomatic" or "cognitive"
    amount: int
    reason: str


class Metrics(NamedTuple):
    cyclomatic: int
    cognitive: int
    nesting: int
    parameters: int
    nloc: int
    contributions: Tuple[Contribution, ...]
    label: str      # ALL_BRANCHES when the body spans #if groups kept as a union, else ""


class ParseError(Exception):
    pass


_NOT_IN_EXPRESSION = frozenset("if else for while do switch case return break continue goto try catch".split())
_JUMPS = frozenset("return break continue throw co_return co_yield goto".split())
_TRANSPARENT = frozenset("return throw co_return co_yield co_await case new delete else do".split())
_BUILTIN = frozenset("auto const volatile bool char char8_t char16_t char32_t wchar_t short int "
                     "long signed unsigned float double void".split())
_STATEMENT_START = frozenset("if for while do switch return case default break continue goto try "
                             "co_return".split())
_CLASS_KEYS = frozenset(("class", "struct", "union"))
_SEPARATORS = frozenset("? : ; = += -= *= /= %= &= |= ^= <<= >>=".split())
_BODY_AFTER = frozenset(") const noexcept override final mutable & && try".split())


def _macro_like(token) -> bool:
    return token.kind == IDENTIFIER and (token.text.isupper() or token.text.startswith("__"))


class _Body:
    def __init__(self, source: SourceFile, function: Function) -> None:
        self.t, self.m = source.tokens, source.match
        self.lambdas = {lam.introducer: lam for lam in function.lambdas}
        self.parameter_lists = [lam.parameters for lam in function.lambdas if lam.parameters]
        self.cyclomatic, self.cognitive, self.nesting = 1, 0, 0
        self.notes: List[Contribution] = []

    def _text(self, k: int) -> str:
        return self.t[k].text if k < len(self.t) else ""

    def _add(self, k: int, metric: str, amount: int, reason: str) -> None:
        if metric == "cyclomatic":
            self.cyclomatic += amount
        else:
            self.cognitive += amount
        self.notes.append(Contribution(self.t[k].line, metric, amount, reason))

    def _structure(self, k: int, level: int, reason: str, cyclomatic: bool = True) -> None:
        if cyclomatic:
            self._add(k, "cyclomatic", 1, reason)
        self._add(k, "cognitive", 1 + level, "%s (nesting %d)" % (reason, level) if level else reason)

    def _close(self, k: int) -> int:
        if self.t[k].kind != PUNCT or self.t[k].text not in "([{" or self.m[k] < 0:
            raise ParseError("line %d: expected a bracket" % self.t[k].line)
        return self.m[k]

    # -- statements
    def run(self, body: Tuple[int, int]) -> None:
        k = self.block(body[0], 0)
        while k <= body[1] and self._text(k) == "catch":
            k = self.handler(k, 0)
        if k != body[1] + 1:
            raise ParseError("line %d: body does not end at its brace" % self.t[k - 1].line)

    def block(self, k: int, level: int) -> int:
        end = self._close(k)
        k += 1
        while k < end:
            k = self.statement(k, level, end)
        return end + 1

    def nested(self, k: int, level: int, limit: int) -> int:
        self.nesting = max(self.nesting, level)
        return self.statement(k, level, limit)

    def statement(self, k: int, level: int, limit: int) -> int:
        if k >= limit:
            raise ParseError("line %d: statement expected" % self.t[limit].line)
        token, text = self.t[k], self.t[k].text
        if token.kind == PUNCT:
            if text == "{":
                return self.block(k, level)
            if text == ";":
                return k + 1
            if text == "[" and self._text(k + 1) == "[":
                return self.statement(self._close(k) + 1, level, limit)  # [[attribute]]
        elif token.kind == KEYWORD:
            if text == "if":
                return self.if_(k, level, limit, False)
            if text in ("for", "while", "switch"):
                self._structure(k, level, text, text != "switch")
                condition = k + 1
                while _macro_like(self.t[condition]):
                    condition += 1
                end = self._close(condition)
                self.expression(condition + 1, end, level + 1)
                return self.nested(end + 1, level + 1, limit)
            if text == "do":
                self._structure(k, level, "do")
                k = self.nested(k + 1, level + 1, limit)
                if self._text(k) != "while" or self._text(k + 1) != "(":
                    raise ParseError("line %d: do without while" % token.line)
                end = self._close(k + 1)
                self.expression(k + 2, end, level + 1)
                if self._text(end + 1) != ";":
                    raise ParseError("line %d: do-while without ;" % token.line)
                return end + 2
            if text == "try":
                k = self.block(k + 1, level)
                if self._text(k) != "catch":
                    raise ParseError("line %d: try without catch" % token.line)
                while k < limit and self._text(k) == "catch":
                    k = self.handler(k, level)
                return k
            if text in ("case", "default"):
                return self.label(k, limit)
            if text in ("public", "private", "protected") and self._text(k + 1) == ":":
                return k + 2
            if text == "goto":
                self._add(k, "cognitive", 1, "goto")
            if text in _JUMPS:
                return self.expression_statement(k + 1, level, limit)
            if text in _NOT_IN_EXPRESSION:
                raise ParseError("line %d: unexpected '%s'" % (token.line, text))
        elif token.kind == IDENTIFIER:
            if self._text(k + 1) == ":":
                return k + 2                                            # label
            after = self._close(k + 1) + 1 if self._text(k + 1) == "(" else k + 1
            if after < limit and self._text(after) == "{" and (after > k + 1 or _macro_like(token)):
                return self.block(after, level)     # MACRO(...) { }: macro control flow is invisible
            if (after > k + 1 or _macro_like(token)) and (after >= limit or (
                    self.t[after].line > self.t[after - 1].line and (
                        self._text(after) in _STATEMENT_START or (after > k + 1 and _macro_like(token)
                                                                  and self.t[after].kind in (IDENTIFIER, KEYWORD))))):
                self.expression(k, after, level)    # MACRO or MACRO(...) ending its line without `;`
                return after
        return self.expression_statement(k, level, limit)

    def expression_statement(self, k: int, level: int, limit: int) -> int:
        end = k
        while end < limit and self._text(end) != ";":
            end = self._close(end) + 1 if self._text(end) in ("(", "[", "{") else end + 1
        if end >= limit:
            raise ParseError("line %d: statement without ;" % self.t[k].line)
        self.expression(k, end, level)
        return end + 1

    def label(self, k: int, limit: int) -> int:
        if self.t[k].text == "case":
            self._add(k, "cyclomatic", 1, "case")
        end, pending = k + 1, 0
        while end < limit and not (self._text(end) == ":" and not pending):
            pending += {"?": 1, ":": -1}.get(self._text(end), 0)
            end = self._close(end) + 1 if self._text(end) in ("(", "[", "{") else end + 1
        if end >= limit:
            raise ParseError("line %d: label without :" % self.t[k].line)
        return end + 1

    def if_(self, k: int, level: int, limit: int, else_if: bool) -> int:
        if else_if:
            self._add(k, "cyclomatic", 1, "else if")
            self._add(k, "cognitive", 1, "else if")
        else:
            self._structure(k, level, "if")
        j = k + 1
        while self._text(j) in ("constexpr", "!") or _macro_like(self.t[j]):
            j += 1
        if self._text(j) == "consteval":
            j += 1
        else:
            end = self._close(j)
            self.expression(j + 1, end, level + 1 if else_if else level)
            j = end + 1
        j = self.nested(j, level + 1, limit)
        if j < limit and self._text(j) == "else":
            if self._text(j + 1) == "if":
                return self.if_(j + 1, level, limit, True)
            self._add(j, "cognitive", 1, "else")
            return self.nested(j + 1, level + 1, limit)
        return j

    def handler(self, k: int, level: int) -> int:
        self._structure(k, level, "catch")
        body = self._close(k + 1) + 1
        if self._text(body) != "{":
            raise ParseError("line %d: catch without a block" % self.t[k].line)
        self.nesting = max(self.nesting, level + 1)
        return self.block(body, level + 1)

    # -- expressions
    def expression(self, lo: int, hi: int, level: int, parent: str = "",
                   in_class: bool = False) -> None:
        """Scan lo..hi-1 for ?:, logical operators, lambdas and nested bodies.

        in_class: lo..hi is a local class body, whose member function bodies are
        statements again."""
        ops: List[Tuple[int, str]] = []
        groups: List[Tuple[int, int, int]] = []    # (open, operators before it, level)
        nest, angle, k, class_key = level, 0, lo, False
        while k < hi:
            token, text = self.t[k], self.t[k].text
            if token.kind == KEYWORD and text in _NOT_IN_EXPRESSION and not (
                    text == "default" and self._text(k - 1) == "="):
                raise ParseError("line %d: '%s' inside an expression" % (token.line, text))
            if token.kind != PUNCT:
                class_key = class_key or (text in _CLASS_KEYS and self._text(k - 1) != "enum")
                k += 1
                continue
            if text == "(":
                end = self._close(k)
                before = self.t[k - 1]
                if (before.kind == IDENTIFIER or (before.kind == KEYWORD and before.text not in _TRANSPARENT)
                        or before.text in (")", "]", ">", ">>")) and k > lo:
                    self.expression(k + 1, end, nest)      # call arguments: a new sequence
                else:
                    groups.append((k, len(ops), nest))
                k = end + 1
                continue
            if text == "[":
                lam = self.lambdas.get(k)
                if lam is not None:
                    self.nesting = max(self.nesting, nest + 1)
                    self.block(lam.body[0], nest + 1)
                    k = lam.body[1] + 1
                    continue
                if self._text(k + 1) != "[":
                    self.expression(k + 1, self._close(k), nest)
                k = self._close(k) + 1
                continue
            if text == "{":
                self.braces(k, nest, class_key, in_class)
                k, class_key = self.m[k] + 1, False
                continue
            if text in ("&&", "||"):
                if not (text == "&&" and self._declarator(k)):
                    self._add(k, "cyclomatic", 1, text)
                    ops.append((k, text))
            elif text in _SEPARATORS or (text == "," and not angle):
                self._sequences(ops, groups, parent)
                ops, groups = [], []
                if text == "?":
                    self._structure(k, nest, "?:")
                    nest += 1
                elif text in (",", ";"):
                    nest, angle = level, 0
            elif text == "<" and self.t[k - 1].kind == IDENTIFIER:
                angle += 1
            elif text in (">", ">>") and angle:
                angle = max(0, angle - len(text))
            k += 1
        self._sequences(ops, groups, parent)

    def _sequences(self, ops, groups, parent: str) -> None:
        # The expression tree of one segment: || binds loosest, so it is the root when
        # present and each run of && below it is a child. An operator counts when its
        # parent operator differs; a parenthesised operand inherits its neighbour.
        if any(op == "||" for _, op in ops):
            if parent != "||":
                self._add(next(k for k, op in ops if op == "||"), "cognitive", 1, "||")
            for n, (k, op) in enumerate(ops):
                if op == "&&" and (n == 0 or ops[n - 1][1] != "&&"):
                    self._add(k, "cognitive", 1, "&&")
        elif ops and parent != "&&":
            self._add(ops[0][0], "cognitive", 1, "&&")
        for open_, before, nest in groups:
            near = [ops[n][1] for n in (before - 1, before) if 0 <= n < len(ops)]
            inherited = "&&" if "&&" in near else "||" if near else parent
            self.expression(open_ + 1, self.m[open_], nest, inherited)

    def braces(self, k: int, level: int, class_body: bool, in_class: bool) -> None:
        end, before = self.m[k], self.t[k - 1]
        requires = before.text == "requires" or (
            before.text == ")" and self.m[k - 1] > 0 and self._text(self.m[k - 1] - 1) == "requires")
        if before.text == "(" and self.m[k - 1] == end + 1 and self._text(end - 1) == ";":
            self.block(k, level)                    # GNU statement expression ({ ...; })
        elif in_class and (before.text in _BODY_AFTER or before.text == "}") and not requires:
            self.nesting = max(self.nesting, level + 1)
            self.block(k, level + 1)                # a local class's member function
        else:                                       # braced initializer, class body, requires
            self.expression(k + 1, end, level, in_class=class_body)

    def _declarator(self, k: int) -> bool:
        """&& declares an rvalue or forwarding reference (T&&, auto&&, Args&&...)."""
        before, after = self.t[k - 1], self._text(k + 1)
        if before.text == "..." or (after == "..." and self._text(k + 2) == ")"):
            return False                            # a fold expression
        if after in (">", ">>", ")", ",", "...", "]", ";", "=") or before.text in _BUILTIN:
            return True
        if any(lo < k < hi for lo, hi in self.parameter_lists):
            return True
        return (before.kind == IDENTIFIER or before.text == ">") and k + 2 < len(self.t) and \
            self.t[k + 1].kind == IDENTIFIER and self._text(k + 2) in ("=", "{")


def measure(source: SourceFile, function: Function, lines: List[int]) -> Metrics:
    """Metrics of one function; lines is the sorted list of lines that hold kept tokens."""
    body = _Body(source, function)
    body.run(function.body)
    nloc = bisect.bisect_right(lines, function.end_line) - bisect.bisect_left(lines, function.start_line)
    at = bisect.bisect_left(source.union_lines, function.start_line)
    spans = at < len(source.union_lines) and source.union_lines[at] <= function.end_line
    return Metrics(body.cyclomatic, body.cognitive, body.nesting, function.parameters, nloc,
                   tuple(sorted(body.notes, key=lambda c: (c.line, c.metric))),
                   ALL_BRANCHES if spans else "")


def analyse(source: SourceFile):
    """[(Function, Metrics)] and the unparsed regions of bodies the parser refused."""
    lines = sorted({token.line for token in source.tokens})
    results, refused = [], []
    for function in source.functions:
        try:
            results.append((function, measure(source, function, lines)))
        except (ParseError, RecursionError, IndexError) as error:
            refused.append(Region(source.path, function.start_line, function.end_line,
                                  "statement parser: %s in %s" % (error or type(error).__name__,
                                                                   function.name)))
    return results, refused
