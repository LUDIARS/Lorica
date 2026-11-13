"""Variables declared outside function bodies. @implements SPEC-LR-ANALYZE

declarations(source) -> Declarations: the classes, the variables declared at
namespace and class scope (data members, static members, globals) and the member
functions declared only as private. It walks the statements that the extractor's
scope scanner leaves outside function bodies and reuses its head classification;
a statement that overlaps an unparsed region is skipped, never guessed.
parse_declaration() reads one simple declaration; the shared-state walker also uses
it for static and thread_local variables inside a body.

Not read: a variable initialised with parentheses whose first argument is not a
literal (`T x(a);` reads as a function declaration), function pointers, structured
bindings, template variables, and anything a macro declares.
"""
from typing import FrozenSet, List, NamedTuple, Optional

from .extract import SourceFile, _Extractor, _Scope
from .lexer import CHAR, IDENTIFIER, NUMBER, PUNCT, STRING

_NOT_VARIABLE = frozenset("using typedef friend static_assert namespace template enum return "
                          "operator goto case default concept export asm".split())
_SPECIFIERS = frozenset("static thread_local mutable extern constexpr constinit inline".split())
SYNC_TYPES = frozenset("mutex recursive_mutex timed_mutex recursive_timed_mutex shared_mutex "
                       "shared_timed_mutex once_flag condition_variable condition_variable_any "
                       "counting_semaphore binary_semaphore latch barrier".split())


class Decl(NamedTuple):
    name: str               # as written, with its qualifier (`C::count`)
    index: int              # token index of the name
    type: str
    specifiers: FrozenSet[str]  # _SPECIFIERS as written, plus const, reference, pointer,
                            # array, atomic (an atomic* type), sync (SYNC_TYPES)


class Variable(NamedTuple):
    name: str               # qualified, as the extractor qualifies functions
    storage: str            # member, static member, global or static local
    file: str
    line: int
    start_line: int         # first line of the declaration statement
    type: str
    specifiers: FrozenSet[str]
    in_class_body: bool
    in_unnamed_namespace: bool


class Declarations(NamedTuple):
    classes: FrozenSet[str]         # qualified names
    variables: List[Variable]
    private: FrozenSet[str]         # member functions declared only under private:


def spell(tokens, lo: int, hi: int, skip: FrozenSet[str] = frozenset()) -> str:
    out = ""
    for token in tokens[lo:hi]:
        if token.text in skip:
            continue
        word = token.kind != PUNCT
        out += (" " if out and word and (out[-1].isalnum() or out[-1] in "_>*&") else "") + token.text
    return out


def angle_end(tokens, match, k: int, hi: int) -> Optional[int]:
    """Index of the `>` closing the `<` at k, or None (a comparison)."""
    depth = 0
    while k < hi:
        text = tokens[k].text
        if tokens[k].kind == PUNCT and text in "([" and k < match[k] < hi:
            k = match[k] + 1
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


def parse_declaration(tokens, match, lo: int, hi: int, type_name: str = "") -> Optional[List[Decl]]:
    """The variables a simple declaration in tokens[lo:hi] declares, or None.

    With type_name the declarators follow a class body (`struct F {...} f;`)."""
    items, k = [], lo
    while k < hi:
        token = tokens[k]
        if token.kind == PUNCT and token.text in ("(", "[", "{"):
            if not k < match[k] < hi:
                return None
            if not (token.text == "[" and tokens[k + 1].text == "["):      # [[attribute]]
                items.append(k)
            k = match[k] + 1
            continue
        if token.text == "<" and items and tokens[items[-1]].kind == IDENTIFIER:
            end = angle_end(tokens, match, k, hi)
            if end is not None:
                k = end + 1
                continue
        if token.text in ("alignas", "__attribute__") and k + 1 < hi and tokens[k + 1].text == "(":
            k = max(k + 2, match[k + 1] + 1)
            continue
        items.append(k)
        k += 1
    texts = [tokens[k].text for k in items]
    if not items or texts[0] in _NOT_VARIABLE or "~" in texts or (
            len(items) == 2 and texts[0] in ("class", "struct", "union")):
        return None
    parts, part = [], []
    for k in items:
        if tokens[k].text == ",":
            parts.append(part)
            part = []
        else:
            part.append(k)
    parts.append(part)
    found, base = [], None
    for number, part in enumerate(parts):
        stop = next((j for j, k in enumerate(part) if tokens[k].text in ("=", ":", "(", "[", "{")),
                    len(part))
        if stop < len(part) and tokens[part[stop]].text == "(":
            first = tokens[part[stop] + 1]
            if first.kind not in (NUMBER, STRING, CHAR) and first.text not in ("true", "false", "nullptr"):
                return None                     # a function declaration (or T x(a);)
        names = [j for j in range(stop) if tokens[part[j]].kind == IDENTIFIER]
        if not names or (number == 0 and names[-1] == 0 and not type_name):
            return None
        j = names[-1]
        while j >= 2 and tokens[part[j - 1]].text == "::" and tokens[part[j - 2]].kind == IDENTIFIER:
            j -= 2                              # C::count, a static member defined outside
        name_at = part[names[-1]]
        if number == 0:
            base = (part[0], part[j] if j < len(part) else name_at, [tokens[k].text for k in part[:j]])
        prefix = base[2] + [tokens[k].text for k in part[:j]] if number else base[2]
        pointer = max((p for p, text in enumerate(prefix) if text == "*"), default=-1)
        flags = set(_SPECIFIERS & set(prefix))
        if "constexpr" in flags or "const" in prefix[pointer + 1:]:
            flags.add("const")
        if "&" in prefix or "&&" in prefix:
            flags.add("reference")
        if pointer >= 0:
            flags.add("pointer")
        if stop < len(part) and tokens[part[stop]].text == "[":
            flags.add("array")
        written = spell(tokens, base[0], base[1], _SPECIFIERS) or type_name
        words = set(written.replace("::", " ").replace("<", " ").replace(">", " ").split())
        if any(w.startswith("atomic") for w in words):
            flags.add("atomic")
        if words & SYNC_TYPES:
            flags.add("sync")
        found.append(Decl(spell(tokens, part[j], name_at + 1), name_at, written, frozenset(flags)))
    return found


class _Frame(NamedTuple):
    kind: str           # file, namespace, linkage, class
    name: Optional[str]
    close: int
    access: List[str]   # [current access specifier]


def declarations(source: SourceFile) -> Declarations:
    tokens, match = source.tokens, source.match
    extractor = _Extractor(source.path, tokens)
    extractor.match = match
    bad = [(r.line, r.end_line) for r in source.unparsed]
    frames = [_Frame("file", None, len(tokens), ["public"])]
    classes, variables, private, public = set(), [], set(), set()

    def scope() -> str:
        return "::".join(f.name or "(anonymous namespace)" for f in frames
                         if f.kind == "namespace" or (f.kind == "class" and f.name))

    def statement(lo: int, hi: int, type_name: str) -> None:
        if lo >= hi or any(a <= tokens[hi].line and tokens[lo].line <= b for a, b in bad):
            return
        frame, qualifier = frames[-1], scope()
        if frame.kind == "class" and not type_name:
            k = lo
            while k < hi and tokens[k].text != "(":
                k = match[k] + 1 if tokens[k].text in ("[", "{") and match[k] > k else k + 1
            if k < hi and tokens[k - 1].kind == IDENTIFIER:
                name = qualifier + "::" + tokens[k - 1].text
                (private if frame.access[0] == "private" else public).add(name)
        for decl in parse_declaration(tokens, match, lo, hi, type_name) or ():
            if "sync" in decl.specifiers or ("reference" in decl.specifiers and "static" not in decl.specifiers):
                continue
            name = (qualifier + "::" if qualifier else "") + decl.name
            in_class = frame.kind == "class"
            static = "static" in decl.specifiers or "thread_local" in decl.specifiers
            storage = ("static member" if static else "member") if in_class else (
                "static member" if name.rsplit("::", 1)[0] in classes else "global")
            variables.append(Variable(name, storage, source.path, tokens[decl.index].line, tokens[lo].line, decl.type,
                                      decl.specifiers, in_class, "(anonymous namespace)" in name))

    i = head = 0
    after_class = ""
    while i < len(tokens):
        token, text = tokens[i], tokens[i].text
        if token.kind == PUNCT and text in ("(", "[", "{"):
            close = match[i]
            if close < 0:
                i = head = i + 1
                continue
            if text != "{":
                if i == head + 1 and extractor._macro_statement(i, close, _Scope(frames[-1].kind, frames[-1].name, -1)):
                    head = close + 1
                i = close + 1
                continue
            kind, info = extractor._classify(head, i, _Scope(frames[-1].kind, frames[-1].name, -1))
            if kind in ("namespace", "linkage", "class"):
                if kind == "class":
                    keys = [tokens[k].text for k in range(head, i) if tokens[k].text in ("class", "struct", "union")]
                    frames.append(_Frame(kind, info, close, ["private" if keys[-1:] == ["class"] else "public"]))
                    classes.add(scope())
                else:
                    frames.append(_Frame(kind, info, close, ["public"]))
                i = head = i + 1
                continue
            if kind in ("function", "lambda", "macro-function") and frames[-1].kind == "class":
                at, sig = info[0], info[1]
                name = scope() + "::" + extractor._name(sig, at)[0] if kind == "function" else ""
                (private if frames[-1].access[0] == "private" else public).add(name)
            if kind in ("initializer", "mem-init", "requires"):
                i = close + 1
                continue
            i = head = close + 1
            continue
        if token.kind == PUNCT and text == ";":
            statement(head, i, after_class)
            i = head = i + 1
            after_class = ""
            continue
        if token.kind == PUNCT and text == "}" and len(frames) > 1 and frames[-1].close == i:
            popped = frames.pop()
            after_class = (popped.name or "class") if popped.kind == "class" else ""
            i = head = i + 1
            continue
        if text in ("public", "private", "protected") and i + 1 < len(tokens) and tokens[i + 1].text == ":":
            frames[-1].access[0] = text
            i = head = i + 2
            continue
        i += 1
    return Declarations(frozenset(classes), variables, frozenset(private - public))
