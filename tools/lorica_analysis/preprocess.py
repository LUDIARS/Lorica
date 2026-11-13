"""Preprocessor pre-pass: one token stream from a file with conditional groups.

No macro is expanded and no condition is evaluated, except that `#if 0` and
`#elif 0` branches are dropped. For each conditional group (#if/#ifdef/#ifndef ...
#endif): when every live branch is bracket-neutral for () [] {}, all of them are
kept in source order (a union; metrics then cover all branches); otherwise only
the first live branch is kept and the others are recorded as not analysed. This
keeps signatures, argument lists and braces split by #if from desynchronising the
extractor. Groups are resolved innermost first, in one iterative pass.
"""
import re
from typing import List, NamedTuple, Tuple

from .lexer import PUNCT, LexResult, Token

_OPEN = {"(": ")", "[": "]", "{": "}"}
_CLOSE = frozenset(_OPEN.values())
_DEAD = re.compile(r"#\s*(?:if|elif)\s+0\s*$")
_IF = frozenset(("if", "ifdef", "ifndef"))
_ELSE = frozenset(("elif", "else", "elifdef", "elifndef"))

Range = Tuple[int, int, str]  # first line, last line, reason


class Preprocessed(NamedTuple):
    tokens: List[Token]
    not_analysed: List[Range]   # dropped branches (lines inside, directives excluded)
    problems: List[Range]       # conditional structure errors: unparsed
    union_lines: List[int]      # directive lines of groups kept as a union, sorted


def _neutral(tokens: List[Token]) -> bool:
    stack = []
    for token in tokens:
        if token.kind != PUNCT:
            continue
        if token.text in _OPEN:
            stack.append(_OPEN[token.text])
        elif token.text in _CLOSE and (not stack or stack.pop() != token.text):
            return False
    return not stack


def preprocess(lexed: LexResult) -> Preprocessed:
    tokens, directives = lexed.tokens, lexed.directives
    result = Preprocessed([], [], [], [])
    root: List[Token] = []
    groups = []  # open groups: list of branches, each [directive, tokens]
    current = root
    taken = 0

    def resolve(branches, end_line: int) -> List[Token]:
        bounds = [b[0].line for b in branches[1:]] + [end_line]
        live = []
        for (directive, body), stop in zip(branches, bounds):
            span = (directive.end_line + 1, stop - 1)
            if _DEAD.match(directive.text):
                if span[0] <= span[1]:
                    result.not_analysed.append(span + ("#if 0 branch",))
            else:
                live.append((span, body))
        if all(_neutral(body) for _, body in live):
            if live and len(live) == len(branches):  # an #if 0 group is no union
                result.union_lines.extend(b[0].line for b in branches)
                result.union_lines.append(end_line)
            return [token for _, body in live for token in body]
        for span, _ in live[1:]:
            if span[0] <= span[1]:
                result.not_analysed.append(span + (
                    "other preprocessor branch not analysed (brackets unbalanced across "
                    "the #if at line %d)" % branches[0][0].line,))
        return live[0][1]

    for directive in directives:
        current.extend(tokens[taken:directive.index])
        taken = directive.index
        if directive.name in _IF:
            groups.append([[directive, []]])
            current = groups[-1][-1][1]
        elif directive.name in _ELSE or directive.name == "endif":
            if not groups:
                result.problems.append((directive.line, directive.end_line,
                                        "#%s without #if" % directive.name))
                continue
            if directive.name == "endif":
                kept = resolve(groups.pop(), directive.line)
                current = groups[-1][-1][1] if groups else root
                current.extend(kept)
            else:
                groups[-1].append([directive, []])
                current = groups[-1][-1][1]
    current.extend(tokens[taken:])
    last = max([tokens[-1].line if tokens else 1] + [d.end_line for d in directives])
    while groups:
        branches = groups.pop()
        result.problems.append((branches[0][0].line, last, "unterminated #%s" % branches[0][0].name))
        kept = resolve(branches, last + 1)
        (groups[-1][-1][1] if groups else root).extend(kept)
    result.tokens.extend(root)
    result.union_lines.sort()
    return result
