"""Lexical accesses, locksets and calls of one function body. @implements SPEC-LR-ANALYZE

walk(source, function, lines) -> Facts: the events of the body in source order,
without knowing which names are shared (shared_state resolves them over the whole
analysed set). Each use of a name that is not a local or a by-value parameter is an
Event with its access (read, write, rmw, call = passed on or a member call that may
write, escape = returned by reference, atomic = an atomic member function with its
memory orders) and its lexical lockset (None when unknown).

Locks. A guard is `G<..> NAME(args);`, `G<..> NAME{args};` or `auto NAME = G(args);`
for G in GUARDS, held from its declaration to the end of its block (shared_lock in
shared mode). Not a guard, an Event `lock-not-held`: a temporary (`G<M>{m};`),
`G<M>(m);` (declares a variable m), no mutex argument, std::defer_lock, unless NAME is
used again. After any later use of NAME except as the lock of a condition-variable
wait (unlock, release, std::move, ...) the lockset is unknown to the end of the block;
likewise after try_to_lock, std::lock, and a manual m.lock() without an m.unlock() in
the same block with no return, throw, break, continue or goto between. A lock whose
mutex is a call expression has an unknown name. After std::call_once(flag, ...) the
rest of the block holds the pseudo-lock `call_once(flag)`.

Lambdas: a body run in place (invoked immediately, or passed to a synchronous
callee in SYNC_CALLEES such as a condition-variable predicate or an algorithm
without an execution policy) keeps the lockset; any other body has an empty lockset,
because it may run later or on another thread. The callable of std::call_once is
initialisation.
"""
from typing import Dict, FrozenSet, List, NamedTuple, Optional, Tuple

from .declarations import angle_end, parse_declaration, spell
from .extract import Function, SourceFile
from .lexer import IDENTIFIER, KEYWORD, PUNCT

GUARDS = frozenset(("lock_guard", "unique_lock", "scoped_lock", "shared_lock"))
SYNC_CALLEES = frozenset("""invoke apply wait wait_for wait_until visit for_each for_each_n transform
    sort stable_sort partial_sort find_if find_if_not any_of all_of none_of count_if remove_if
    copy_if replace_if partition stable_partition generate accumulate reduce transform_reduce
    inner_product min_element max_element minmax_element lower_bound upper_bound equal_range
    binary_search adjacent_find mismatch equal search unique merge""".split())
ATOMIC_OPS = frozenset("""load store exchange compare_exchange_weak compare_exchange_strong fetch_add
    fetch_sub fetch_and fetch_or fetch_xor fetch_max fetch_min test_and_set clear test wait""".split())
_READ_METHODS = frozenset("""size empty length capacity find count contains at front back begin end
    cbegin cend rbegin rend data c_str get value has_value compare substr starts_with ends_with
    str bucket_count load is_lock_free operator""".split())
_WRITE_METHODS = frozenset("""push_back emplace_back push_front emplace_front pop_back pop_front push
    pop emplace emplace_hint insert insert_or_assign try_emplace erase clear resize reserve assign
    swap reset release append replace shrink_to_fit merge extract splice sort""".split())
_ESCAPING = frozenset(("data", "c_str", "begin", "end", "get", "front", "back"))
_ASSIGN = frozenset("= += -= *= /= %= &= |= ^= <<= >>=".split())
_TYPES = frozenset("auto bool char char8_t char16_t char32_t wchar_t short int long signed unsigned "
                   "float double void const volatile".split())
_JUMPS = frozenset(("return", "throw", "break", "continue", "goto", "co_return"))
_CONTROL = frozenset(("if", "for", "while", "switch", "catch"))
STREAMS = frozenset(("cout", "cerr", "clog", "wcout", "wcerr", "wclog"))
_STDIO = frozenset(("printf", "puts", "putchar", "vprintf", "perror", "wprintf"))
_FILE_IO = frozenset(("fprintf", "fputs", "fputc", "putc", "fwrite", "fflush", "vfprintf",
                      "fputws", "fwprintf"))
MT_UNSAFE = {"strtok": "strtok_r", "rand": "a <random> engine per thread", "localtime": "localtime_r",
             "gmtime": "gmtime_r", "asctime": "strftime", "ctime": "ctime_r",
             "setlocale": "a locale object or uselocale", "setenv": "setting it before threads start",
             "putenv": "setting it before threads start", "tmpnam": "mkstemp",
             "getpwnam": "getpwnam_r", "gethostbyname": "getaddrinfo", "inet_ntoa": "inet_ntop",
             "strsignal": "sigabbrev_np or a table"}
EFFECTS = frozenset("""mmap munmap mprotect madvise mlock munlock VirtualAlloc VirtualFree VirtualProtect
    VirtualLock signal sigaction chdir umask setenv putenv unsetenv atexit set_terminate
    set_new_handler""".split())


class Event(NamedTuple):
    kind: str           # use, call, static, lock-not-held, fence, stream, libc, effect
    name: str           # chain as written (`x`, `C::x`), `static:<qualified>` for a static local
    line: int
    access: str = ""    # use: read write rmw call escape atomic; call: free member indirect
    locks: Optional[FrozenSet[str]] = frozenset()   # None: unknown; "m(shared)" for shared mode
    op: str = ""        # use: the atomic member function; static: the type
    orders: Tuple[Optional[str], ...] = ()  # per argument of an atomic call: order or None
    statement: int = 0
    flags: FrozenSet[str] = frozenset()  # this, param, const, init, lambda, condition,
                        # thread_local / atomic / pointer for a static local
    arity: int = -1     # call: number of arguments; stream: number of output operations


class Facts(NamedTuple):
    function: Function
    events: List[Event]
    returns_reference: bool
    this_escapes: bool  # a constructor passes `this` on


class _Lock:
    __slots__ = ("name", "var", "since", "until", "unknown_from")

    def __init__(self, name, var, since, until):
        self.name, self.var, self.since, self.until, self.unknown_from = name, var, since, until, None


class _Frame:
    __slots__ = ("end", "locks", "shadows", "lambdas", "statics", "unknown_from")

    def __init__(self, end, shadows=None, lambdas=None, statics=None):
        self.end, self.locks, self.unknown_from = end, [], None
        self.shadows = set() if shadows is None else shadows
        self.lambdas = set() if lambdas is None else lambdas
        self.statics: Dict[str, str] = {} if statics is None else statics


def _split(tokens, match, lo: int, hi: int) -> List[Tuple[int, int]]:
    """Top-level comma-separated ranges of tokens[lo:hi]."""
    parts, start, k = [], lo, lo
    while k < hi:
        if tokens[k].kind == PUNCT and tokens[k].text in "([{" and k < match[k] < hi:
            k = match[k] + 1
            continue
        if tokens[k].text == "<" and k > lo and tokens[k - 1].kind == IDENTIFIER:
            end = angle_end(tokens, match, k, hi)
            if end is not None:
                k = end + 1
                continue
        if tokens[k].text == ",":
            parts.append((start, k))
            start = k + 1
        k += 1
    return parts + [(start, hi)] if hi > lo else parts


def _order(tokens, lo: int, hi: int) -> Optional[str]:
    for k in range(lo, hi):
        text = tokens[k].text
        if text.startswith("memory_order_"):
            return text[len("memory_order_"):]
        if text == "memory_order" and k + 2 < hi and tokens[k + 1].text == "::":
            return tokens[k + 2].text
    return None


class _Walker:
    def __init__(self, source: SourceFile, function: Function, lines: List[int]) -> None:
        self.t, self.m, self.f = source.tokens, source.match, function
        self.lambdas = {lam.introducer: lam for lam in function.lambdas}
        self.events: List[Event] = []
        self.statement, self.parens, self.paired = 0, [], set()
        self.this_escapes = False
        self.params: Dict[str, Tuple[bool, bool]] = {}     # name -> (referent, const referent)
        self.returns_reference = False
        self._head(lines)

    # -- the declaration head: parameters and a reference/pointer return type
    def _head(self, lines: List[int]) -> None:
        import bisect
        t, f = self.t, self.f
        open_ = f.body[0]
        lo = bisect.bisect_left(lines, f.start_line, 0, open_)
        short = f.name.rsplit("::", 1)[-1]
        name = next((k for k in range(lo, open_) if t[k].line == f.line and (
            t[k].text == short.lstrip("~") or (t[k].text == "operator" and short.startswith("operator")))), None)
        if name is None or f.kind in ("macro-function", "lambda"):
            group = (self.m[open_ - 1], open_ - 1) if f.kind == "lambda" and t[open_ - 1].text == ")" else None
        else:
            k = name + 1
            if t[name].text == "operator" and k + 1 < open_ and t[k].text == "(" and t[k + 1].text == ")":
                k += 2
            while k < open_ and t[k].text != "(":
                k += 1
            group = (k, self.m[k]) if k < open_ and self.m[k] > k else None
            before = name - 1
            while before > lo and t[before].text == "::" and t[before - 1].kind == IDENTIFIER:
                before -= 2
            if before >= lo and t[before].text == "~":
                before -= 1
            trailing = group and any(t[j].text == "->" for j in range(group[1], open_))
            tail = range(group[1], open_) if trailing else range(before, before + 1)
            self.returns_reference = any(t[j].text in ("&", "&&", "*") for j in tail if j >= lo)
        if group:
            for lo_, hi_ in _split(t, self.m, group[0] + 1, group[1]):
                self._parameter(lo_, hi_)

    def _parameter(self, lo: int, hi: int) -> None:
        t = self.t
        end = next((k for k in range(lo, hi) if t[k].text == "="), hi)
        names = [k for k in range(lo, end) if t[k].kind == IDENTIFIER]
        if not names:
            return
        words = [t[k].text for k in range(lo, names[-1])]
        indirection = [j for j, w in enumerate(words) if w in ("&", "&&", "*")]
        const = bool(indirection) and "const" in words[:indirection[0]]
        self.params[t[names[-1]].text] = (bool(indirection) and "*" not in words, const)

    # -- helpers
    def _locks(self, k: int, frames: List[_Frame]) -> Optional[FrozenSet[str]]:
        held = set()
        for frame in frames:
            if frame.unknown_from is not None and frame.unknown_from <= k:
                return None
            for lock in frame.locks:
                if lock.since <= k <= lock.until:
                    if (lock.unknown_from is not None and lock.unknown_from <= k) or lock.name == "?":
                        return None
                    if lock.name:
                        held.add(lock.name)
        return frozenset(held)

    def _emit(self, kind, name, k, frames, flags, **fields) -> None:
        if any(p[2] == "control" for p in self.parens):
            flags = flags | {"condition"}
        self.events.append(Event(kind, name, self.t[k].line, locks=self._locks(k, frames),
                                 statement=self.statement, flags=frozenset(flags), **fields))

    def _statement_end(self, k: int, hi: int) -> int:
        t, m = self.t, self.m
        while k < hi:
            if t[k].text == "{" and m[k] > k:
                if t[k - 1].text in (")", "else", "do", "try"):
                    return m[k]
                k = m[k] + 1
                continue
            if t[k].text in ("(", "[") and m[k] > k:
                k = m[k] + 1
                continue
            if t[k].text == ";":
                return k
            k += 1
        return hi

    def _starts_statement(self, k: int, lo: int) -> bool:
        return k == lo or self.t[k - 1].text in (";", "{", "}")

    def _lookup(self, name: str, frames: List[_Frame]):
        for frame in reversed(frames):
            if name in frame.shadows:
                return "local", frame
            if name in frame.statics:
                return "static", frame.statics[name]
        return None, None

    # -- the walk
    def run(self) -> Facts:
        open_, close = self.f.body
        self._walk(open_ + 1, close, [_Frame(close)], frozenset())
        return Facts(self.f, self.events, self.returns_reference, self.this_escapes)

    def _walk(self, lo: int, hi: int, frames: List[_Frame], context: FrozenSet[str]) -> None:
        t, m = self.t, self.m
        saved, self.parens = self.parens, []
        k = lo
        while k < hi:
            while len(frames) > 1 and frames[-1].end < k:
                frames.pop()
            while self.parens and self.parens[-1][1] < k:
                self.parens.pop()
            token, text = t[k], t[k].text
            if token.kind == PUNCT:
                if text == ";":
                    self.statement += 1
                elif text == "{" and m[k] > k:
                    frames.append(_Frame(m[k]))
                    self.statement += 1
                elif text == "(" and m[k] > k:
                    before = t[k - 1]
                    kind = "control" if before.text in _CONTROL else "expr"
                    self.parens.append((k, m[k], kind, before.text if before.kind == IDENTIFIER else ""))
                    if kind == "control":
                        frames.append(_Frame(self._statement_end(m[k] + 1, hi)))
                elif text == "[" and k in self.lambdas:
                    k = self._lambda(k, frames, context)
                    continue
                elif text == "[" and m[k] > k and t[k - 1].text in ("auto", "&", "&&"):
                    frames[-1].shadows.update(x.text for x in t[k + 1:m[k]] if x.kind == IDENTIFIER)
                    k = m[k] + 1        # structured binding
                    continue
                k += 1
            elif token.kind == KEYWORD:
                if text in ("static", "thread_local") and self._starts_statement(k, lo):
                    k = self._static_local(k, hi, frames, context)
                    continue
                if text == "this":
                    if k + 2 < hi and t[k + 1].text == "->" and t[k + 2].kind == IDENTIFIER:
                        k = self._identifier(k + 2, lo, hi, frames, context | {"this"})
                        continue
                    if self.f.kind == "constructor":
                        self.this_escapes = True
                k += 1
            elif token.kind == IDENTIFIER:
                k = self._identifier(k, lo, hi, frames, context)
            else:
                k += 1
        self.parens = saved

    def _lambda(self, k: int, frames: List[_Frame], context: FrozenSet[str]) -> int:
        t, lam = self.t, self.lambdas[k]
        open_, close = lam.body
        callee = self.parens[-1][3] if self.parens and t[k - 1].text in ("(", ",") else ""
        policy = bool(self.parens) and any(t[j].text == "execution" for j in range(self.parens[-1][0], k))
        inherit = (close + 1 < len(t) and t[close + 1].text == "(") or (
            callee in SYNC_CALLEES and not policy) or callee == "call_once"
        if self.f.kind == "constructor" and any(t[j].text in ("this", "&", "=") for j in range(k, self.m[k])):
            self.this_escapes = True
        inner = _Frame(close)
        if lam.parameters:
            for lo_, hi_ in _split(t, self.m, lam.parameters[0] + 1, lam.parameters[1]):
                names = [j for j in range(lo_, hi_) if t[j].kind == IDENTIFIER and t[j].text not in ("=",)]
                if names:
                    inner.shadows.add(t[names[-1]].text)
        if inherit:
            outer = frames
        else:
            outer = [_Frame(f.end, f.shadows, f.lambdas, f.statics) for f in frames]
        flags = context | {"lambda"} | ({"init"} if callee == "call_once" else set())
        self._walk(open_ + 1, close, outer + [inner], frozenset(flags))
        return close + 1

    def _static_local(self, k: int, hi: int, frames: List[_Frame], context) -> int:
        end = self._statement_end(k, hi)
        decls = parse_declaration(self.t, self.m, k, end) or []
        for decl in decls:
            if "const" in decl.specifiers or "reference" in decl.specifiers:
                frames[-1].shadows.add(decl.name)
                continue
            qualified = self.f.name + "::" + decl.name
            frames[-1].statics[decl.name] = qualified
            self._emit("static", "static:" + qualified, decl.index, frames, set(decl.specifiers),
                       op=decl.type)
        if not decls:
            return k + 1
        self._walk(decls[0].index + 1, end, frames, context | {"init"})
        return end

    def _declares(self, k: int) -> bool:
        """An obvious local declaration: `T x =`, `T* x;`, `auto& x :`, `T x{`..."""
        t = self.t
        if self.parens and self.parens[-1][2] != "control" and self.parens[-1][3] != "catch":
            return False
        after = t[k + 1].text if k + 1 < len(t) else ";"
        if after not in ("=", ";", "{", "(", ":", "[", ",", ")"):
            return False
        if after in (",", ")") and not (self.parens and self.parens[-1][3] in ("catch", "for", "if")):
            if after == ")" or self.parens:
                return False
        before = k - 1
        if t[before].text in ("*", "&", "&&"):
            before -= 1
        word = t[before]
        if word.text in (">", ">>"):
            return self._closes_template(before)
        return (word.kind == IDENTIFIER and t[before - 1].text not in (".", "->")) or word.text in _TYPES

    def _closes_template(self, k: int) -> bool:
        depth, t = 0, self.t
        while k > 0 and t[k].text not in (";", "{", "}", "(", ")"):
            depth += {">": 1, ">>": 2, "<": -1}.get(t[k].text, 0)
            if depth <= 0:
                return t[k - 1].kind == IDENTIFIER
            k -= 1
        return False

    def _identifier(self, k: int, lo: int, hi: int, frames: List[_Frame], context) -> int:
        t, m = self.t, self.m
        token, text = t[k], t[k].text
        after = t[k + 1].text if k + 1 < len(t) else ";"
        flags = set(context)
        if t[k - 1].text in (".", "->") and "this" not in flags:
            if after == "(":
                self._emit("call", text, k, frames, flags, access="member", arity=self._arity(k + 1))
            return k + 1
        if after == "::":
            return k + 1
        start = k
        while start >= 2 and t[start - 1].text == "::" and t[start - 2].kind == IDENTIFIER:
            start -= 2
        chain = spell(t, start, k + 1)
        qualified = start < k or t[k - 1].text == "::"
        if chain.startswith("std::") or not qualified:
            special = self._special(k, text, after, hi, frames, flags)
            if special is not None:
                return special
        if text in GUARDS:
            return self._guard(k, start, lo, hi, frames, flags)
        if chain.startswith("std::") or (after != "(" and k + 1 < len(t) and t[k + 1].kind == IDENTIFIER):
            return k + 1                        # the standard library, or a type: `C c;`
        kind, where = (None, None) if qualified or "this" in flags else self._lookup(text, frames)
        if kind is None and not qualified and "this" not in flags and self._declares(k):
            frames[-1].shadows.add(text)
            if after == "=" and t[k + 2].text == "[":
                frames[-1].lambdas.add(text)
            return k + 1
        if kind == "local":
            if any(text == lock.var for f in frames for lock in f.locks):
                self._guard_used(k, text, frames)
            elif after == "(" and text not in where.lambdas:
                self._emit("call", text, k, frames, flags, access="indirect", arity=self._arity(k + 1))
            return k + 1
        if kind == "static":
            chain = "static:" + where
        elif not qualified and "this" not in flags and text in self.params:
            referent, const = self.params[text]
            deref = self._unary(k, "*") or after in ("->", "[")
            if after == "(":
                self._emit("call", text, k, frames, flags, access="indirect", arity=self._arity(k + 1))
                return k + 1
            if not (referent or deref):
                return k + 1
            flags |= {"param"} | ({"const"} if const and not deref else set())
        elif after == "(" or (after == "<" and self._template_call(k + 1)):
            self._emit("call", chain, k, frames, flags, access="free", arity=self._arity(self._call_paren(k + 1)))
            return k + 1
        self._use(k, start, chain, frames, flags)
        return k + 1

    def _special(self, k, text, after, hi, frames, flags) -> Optional[int]:
        t = self.t
        if text in STREAMS:
            end = self._statement_end(k, hi)
            self._emit("stream", text, k, frames, flags,
                       arity=max(1, sum(1 for j in range(k, end) if t[j].text == "<<")))
            return k + 1
        if after != "(":
            return None
        close = self.m[k + 1]
        args = {x.text for x in t[k + 2:close]}
        if text == "atomic_thread_fence":
            self._emit("fence", text, k, frames, flags, orders=(_order(t, k + 2, close),))
        elif text in MT_UNSAFE:
            self._emit("libc", text, k, frames, flags)
        elif text in _STDIO or (text in _FILE_IO and args & {"stdout", "stderr"}):
            self._emit("stream", text, k, frames, flags, arity=1)
        elif text in EFFECTS:
            self._emit("effect", text, k, frames, flags)
        elif text == "call_once":
            parts = _split(t, self.m, k + 2, close)
            flag = spell(t, *parts[0]) if parts else "?"
            frames[-1].locks.append(_Lock("call_once(%s)" % flag, None, close, frames[-1].end))
        elif text == "lock" and t[k - 1].text == "::":
            frames[-1].unknown_from = k         # std::lock(a, b): which lock is which is unknown
        else:
            return None
        return k + 1

    def _unary(self, k: int, op: str) -> bool:
        t = self.t
        if t[k - 1].text != op:
            return False
        before = t[k - 2]
        return before.kind == PUNCT and before.text not in (")", "]") or before.text in ("return", "throw")

    def _template_call(self, k: int) -> bool:
        end = angle_end(self.t, self.m, k, len(self.t))
        return end is not None and end + 1 < len(self.t) and self.t[end + 1].text == "("

    def _call_paren(self, k: int) -> int:
        if self.t[k].text == "<":
            k = angle_end(self.t, self.m, k, len(self.t)) + 1
        return k

    def _arity(self, k: int) -> int:
        if k >= len(self.t) or self.t[k].text != "(" or self.m[k] < k:
            return -1
        return len(_split(self.t, self.m, k + 1, self.m[k]))

    def _use(self, k: int, start: int, chain: str, frames, flags) -> None:
        t, m = self.t, self.m
        j, method = k + 1, None
        while j < len(t):
            if t[j].text == "[" and m[j] > j:
                j = m[j] + 1
            elif t[j].text in (".", "->") and j + 1 < len(t) and t[j + 1].kind == IDENTIFIER:
                if j + 2 < len(t) and t[j + 2].text == "(" and m[j + 2] > j:
                    method = method or (t[j + 1].text, j + 2)
                    j = m[j + 2] + 1
                else:
                    j += 2
            else:
                break
        after = t[j].text if j < len(t) else ";"
        before = start - 1
        if "this" in flags:
            before -= 2
        elif t[before].text == "::":
            before -= 1
        deref = self._unary(before + 1, "*")
        if deref:
            before -= 1
        address = self._unary(before + 1, "&")
        fields = {}
        if after in _ASSIGN:
            access = "write" if after == "=" else "rmw"
        elif after in ("++", "--") or t[before].text in ("++", "--"):
            access = "rmw"
        elif method and method[0] in ATOMIC_OPS:
            close = m[method[1]]
            orders = tuple(_order(t, a, b) for a, b in _split(t, m, method[1] + 1, close))
            access, fields = "atomic", {"op": method[0], "orders": orders}
        elif method:
            access = "read" if method[0] in _READ_METHODS else "write" if method[0] in _WRITE_METHODS else "call"
        else:
            access = "read"
        returned = t[before - 1 if address else before].text == "return" and after == ";"
        if returned and (address or (self.returns_reference and (not method or method[0] in _ESCAPING))):
            access = "escape"
        elif address:
            access = "call"
        elif access == "read" and t[before].text in ("(", ",") and after in (")", ",") and \
                self.parens and self.parens[-1][2] == "expr" and self.parens[-1][3] and not deref:
            access = "call"         # passed by name: possibly by non-const reference
        if method and method[0] in ("lock", "lock_shared", "unlock", "unlock_shared", "try_lock"):
            self._manual_lock(k, t[k].text, method[0], frames)
            return
        self._emit("use", chain, k, frames, flags, access=access, **fields)

    # -- locks
    def _manual_lock(self, k: int, name: str, method: str, frames: List[_Frame]) -> None:
        t, frame = self.t, frames[-1]
        if method in ("unlock", "unlock_shared"):
            if k not in self.paired:
                frame.unknown_from = k if frame.unknown_from is None else frame.unknown_from
            return
        if method == "try_lock":
            frame.unknown_from = k if frame.unknown_from is None else frame.unknown_from
            return
        depth, j = 0, k + 1
        unlock = "unlock_shared" if method == "lock_shared" else "unlock"
        while j < frame.end:
            text = t[j].text
            depth += {"{": 1, "}": -1}.get(text, 0)
            if text in _JUMPS:
                break
            if depth == 0 and text == name and j + 2 < len(t) and t[j + 1].text in (".", "->") \
                    and t[j + 2].text == unlock:
                self.paired.add(j)
                frame.locks.append(_Lock(name + ("(shared)" if method == "lock_shared" else ""), None, k, j))
                return
            j += 1
        frame.unknown_from = k if frame.unknown_from is None else frame.unknown_from

    def _guard_used(self, k: int, name: str, frames: List[_Frame]) -> None:
        if self.parens and self.parens[-1][3] in ("wait", "wait_for", "wait_until"):
            return
        for frame in frames:
            for lock in frame.locks:
                if lock.var == name and lock.since < k and lock.unknown_from is None:
                    lock.unknown_from = k

    def _guard(self, k: int, start: int, lo: int, hi: int, frames: List[_Frame], flags) -> int:
        t, m = self.t, self.m
        guard = t[k].text
        named_auto = start >= 3 and t[start - 1].text == "=" and t[start - 3].text == "auto"
        if not (named_auto or self._starts_statement(start, lo)):
            return k + 1
        j = k + 1
        if j < hi and t[j].text == "<":
            end = angle_end(t, m, j, hi)
            if end is None:
                return k + 1
            j = end + 1
        end = self._statement_end(j, hi)
        text = spell(t, start, end)
        var, args = None, None
        if named_auto and t[j].text in ("(", "{"):
            var, args = t[start - 2].text, (j + 1, m[j])
        elif t[j].kind == IDENTIFIER:
            var = t[j].text
            if t[j + 1].text in ("(", "{") and m[j + 1] > j:
                args = (j + 2, m[j + 1])
        frame = frames[-1]
        if var is None:                                     # G<M>{m}; or G<M>(m);
            self._emit("lock-not-held", text, k, frames, flags)
            return end
        frame.shadows.add(var)
        names, tags = [], set()
        for a, b in _split(t, m, *args) if args else []:
            words = {x.text for x in t[a:b]}
            tag = words & {"defer_lock", "try_to_lock", "adopt_lock"}
            if tag:
                tags |= tag
                continue
            mutex = spell(t, a, b)
            for prefix in ("this->", "::", "*this->"):
                mutex = mutex[len(prefix):] if mutex.startswith(prefix) else mutex
            names.append("?" if "(" in words or not mutex else mutex)
        if guard != "scoped_lock":
            names = names[:1]
        if "try_to_lock" in tags:
            lock = _Lock("?", var, end, frame.end)
        elif not names or "defer_lock" in tags:
            if not any(x.text == var for x in t[end:frame.end]):
                self._emit("lock-not-held", text, k, frames, flags)
            lock = _Lock(None, var, end, frame.end)
        else:
            shared = "(shared)" if guard == "shared_lock" else ""
            for name in names[1:]:
                frame.locks.append(_Lock(name + shared, var, end, frame.end))
            lock = _Lock(names[0] + shared, var, end, frame.end)
        frame.locks.append(lock)
        return end


def walk(source: SourceFile, function: Function, lines: List[int]) -> Facts:
    return _Walker(source, function, lines).run()
