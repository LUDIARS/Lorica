"""Shared state and synchronization over an analysed file set. @implements SPEC-LR-ANALYZE

Lexical, per analysed file set: not a proof of the absence of data races. The
primary result is one row per datum: every non-const member, global, static
member, static local and thread_local declared in the set, with the lexical lockset
of each access and a `synchronization` value:
    not-needed               not accessed, read-only in the set, or thread_local
    caller-must-synchronize  a member, never locked: the object is caller-synchronized
    lock:<names>             every access holds these locks (consistent in the
                             analysed set; the strongest positive statement made)
    atomic:<orders>          a std::atomic, judged per operation (findings below)
    inconsistent             some accesses hold a lock and others another or none
    missing                  a global or static written with no lock anywhere
    unknown                  a lockset, a name or a write could not be resolved
Each function gets a `sharing` value, never a safety verdict: no-shared-state <
caller-synchronized:read < caller-synchronized:write < self-synchronized(unverified)
< unknown < thread-hostile, joined over its own accesses and its callees resolved in
the set; an unresolved or indirect call makes it unknown, never safe.

Barriers. std::atomic_thread_fence orders nothing by itself and never repairs a
data race on a non-atomic object: it gives happens-before only together with an
atomic object that the writer modifies after a release fence and the reader loads
before an acquire fence, which is equivalent to release/acquire on that atomic.
Plain shared data needs std::atomic or a lock; publishing data needs a
happens-before edge (release/acquire, a lock, thread start/join, call_once).

Findings (the gate's metrics, one count per entry): FINDINGS. Accesses in
constructors and destructors of the datum's class (unless `this` is passed on), in
the callable of std::call_once and in the initialiser of a static local are
initialisation and exempt. Locks held at every call site propagate into callees in
an unnamed namespace, static free functions and private members.
"""
from typing import Dict, FrozenSet, List, NamedTuple, Optional, Set, Tuple

from .accesses import MT_UNSAFE, Event, Facts, walk
from .declarations import Declarations, Variable, declarations
from .extract import Function, SourceFile
from .gate import Entry

FINDINGS = ("inconsistent-locking", "unsynchronized", "write-under-shared-lock", "reference-escapes-lock",
            "const-writes-mutable", "lock-not-held", "relaxed-publication", "invalid-order",
            "fence-without-atomic", "mt-unsafe-call", "unknown")
SHARING = ("no-shared-state", "caller-synchronized:read", "caller-synchronized:write",
           "self-synchronized(unverified)", "unknown", "thread-hostile")
_C_LIBRARY = frozenset("""memcpy memmove memset memcmp memchr strlen strnlen strcmp strncmp strchr
    strrchr strstr strcpy strncpy strcat strncat snprintf sprintf vsnprintf sscanf strtol strtoul
    strtoll strtoull strtod strtof atoi atol atof abs labs llabs malloc calloc realloc free abort
    exit _Exit quick_exit assert offsetof isalpha isdigit isspace isalnum isupper islower isxdigit
    isprint iscntrl ispunct toupper tolower wcslen va_start va_end va_arg va_copy""".split())
_WRITER = frozenset("store exchange compare_exchange_weak compare_exchange_strong fetch_add fetch_sub "
                    "fetch_and fetch_or fetch_xor fetch_max fetch_min test_and_set clear".split())
_READER = frozenset("load exchange compare_exchange_weak compare_exchange_strong fetch_add fetch_sub "
                    "fetch_and fetch_or fetch_xor fetch_max fetch_min test_and_set test wait".split())
_PUBLISH = frozenset("store exchange compare_exchange_weak compare_exchange_strong".split())
_OBSERVE = frozenset("load exchange compare_exchange_weak compare_exchange_strong test wait".split())
_ORDER_AT = {"load": 0, "test": 0, "test_and_set": 0, "clear": 0, "wait": 1, "store": 1,
             "compare_exchange_weak": 2, "compare_exchange_strong": 2}
_INVALID = {"load": ("release", "acq_rel"), "test": ("release", "acq_rel"), "wait": ("release", "acq_rel"),
            "store": ("acquire", "consume", "acq_rel"), "clear": ("acquire", "consume", "acq_rel")}


class Note(NamedTuple):         # a report line, shaped like complexity.Contribution
    line: int
    metric: str
    amount: int
    reason: str


class _Access(NamedTuple):
    facts: Facts
    event: Event
    access: str                         # the event's, corrected with the datum's type
    locks: Optional[FrozenSet[str]]     # effective: own, from callers, atomic publication
    init: bool


class _Datum:
    def __init__(self, variable: Variable, source: SourceFile) -> None:
        self.v, self.source, self.accesses = variable, source, []
        self.sync, self.finding, self.note, self.offending = "not-needed", "", "", set()
        self.atomic = "atomic" in variable.specifiers
        self.publication = self.atomic and "*" in variable.type


class _File(NamedTuple):
    source: SourceFile          # without tokens: comments for suppressions
    declarations: Declarations
    facts: List[Facts]


def _norm(name: str) -> str:
    return name.replace("(anonymous namespace)::", "")


def _scopes(name: str) -> List[str]:
    parts = name.split("::")[:-1]
    return ["::".join(parts[:k]) for k in range(len(parts), -1, -1)]


def _join(*values: str) -> str:
    return max(values, key=SHARING.index, default=SHARING[0])


def _combine(a, b):
    return None if a is None or b is None else a | b


def _locks(locks: Optional[FrozenSet[str]]) -> str:
    return "?" if locks is None else "{%s}" % ",".join(sorted(locks))


class Result(NamedTuple):
    entries: List[Entry]
    data: Dict[str, Tuple[str, str, str]]           # datum -> (synchronization, finding, storage)
    functions: Dict[str, Tuple[str, FrozenSet[str]]]  # function -> (sharing, flags)


class Collector:
    """COMMANDS entry: add() reads one file, finish() judges the whole set."""

    def __init__(self) -> None:
        self.files: List[_File] = []

    def add(self, source: SourceFile):
        lines = [token.line for token in source.tokens]
        facts = [walk(source, function, lines) for function in source.functions]
        self.files.append(_File(source._replace(tokens=[], match=[]), declarations(source), facts))
        return [], []

    def finish(self):
        return self.result().entries, []

    def result(self) -> Result:
        files, self.files = self.files, []
        analysis = _Analysis(files)
        entries = analysis.entries()
        return Result(entries, {d.v.name: (d.sync, d.finding, d.v.storage) for d in analysis.data.values()},
                      analysis.summary)


class _Analysis:
    def __init__(self, files: List[_File]) -> None:
        self.classes: Set[str] = set().union(*(f.declarations.classes for f in files))
        self.private = {_norm(n) for f in files for n in f.declarations.private}
        self.data: Dict[str, _Datum] = {}
        for file in files:
            for variable in file.declarations.variables:
                key = _norm(variable.name)
                if "const" not in variable.specifiers and (
                        key not in self.data or variable.in_class_body and not self.data[key].v.in_class_body):
                    self.data[key] = _Datum(variable, file.source)
            for facts in file.facts:
                for event in facts.events:
                    if event.kind == "static":     # flags: the declaration's specifiers
                        f = facts.function
                        variable = Variable(event.name[7:], "static local", f.file, event.line, event.line,
                                            event.op, event.flags, False, f.in_unnamed_namespace)
                        self.data[_norm(variable.name)] = _Datum(variable, file.source)
        self.facts = [facts for file in files for facts in file.facts]
        self.sources = {f.source.path: f.source for f in files}
        self.by_key: Dict[str, List[Facts]] = {}
        self.by_short: Dict[str, List[Facts]] = {}
        for facts in self.facts:
            self.by_key.setdefault(_norm(facts.function.name), []).append(facts)
            self.by_short.setdefault(facts.function.name.rsplit("::", 1)[-1], []).append(facts)
        self.class_short = {c.rsplit("::", 1)[-1] for c in self.classes}

    # -- name resolution
    def owner(self, function: Function) -> Optional[str]:
        parts = function.name.split("::")
        return next(("::".join(parts[:k]) for k in range(len(parts) - 1, 0, -1)
                     if "::".join(parts[:k]) in self.classes), None)

    def datum(self, facts: Facts, event: Event) -> Optional[_Datum]:
        name = event.name
        if name.startswith("static:"):
            return self.data.get(_norm(name[7:]))
        if "param" in event.flags:
            return None
        owner = self.owner(facts.function)
        scopes = [owner] if "this" in event.flags else _scopes(facts.function.name)
        for scope in scopes:
            if scope is not None:
                found = self.data.get(_norm((scope + "::" if scope else "") + name.lstrip(":")))
                if found:
                    return found
        return None

    def callees(self, facts: Facts, event: Event) -> Optional[List[Facts]]:
        """Resolved functions of a call, [] for a library call, None when unknown."""
        if event.access == "indirect":
            return None
        if event.access == "member":
            found = [f for f in self.by_short.get(event.name, []) if self.owner(f.function)]
        else:
            found = next((self.by_key[k] for k in (_norm((s + "::" if s else "") + event.name.lstrip(":"))
                                                    for s in _scopes(facts.function.name)) if k in self.by_key), [])
            short = event.name.rsplit("::", 1)[-1]
            if not found and not (short in self.class_short or short in _C_LIBRARY
                                  or short.startswith("__builtin")):
                return None
        same = [f for f in found if f.function.parameters == event.arity]
        return same or found

    # -- the analysis
    def entries(self) -> List[Entry]:
        self.uses: Dict[int, List[Tuple[Event, Optional[_Datum]]]] = {}
        for facts in self.facts:
            self.uses[id(facts)] = [(e, self.datum(facts, e) if e.kind in ("use", "call") else None)
                                    for e in facts.events]
        self._propagate_locks()
        self._roles()
        for facts in self.facts:
            self._record(facts)
        for datum in self.data.values():
            self._judge(datum)
        out = [self._datum_entry(d) for d in self.data.values()
               if d.v.file in self.sources]
        out += self._function_entries()
        return sorted(out, key=lambda e: (e.function.file, e.function.line, e.function.kind != "datum"))

    def _propagate_locks(self) -> None:
        sites: Dict[int, List[Tuple[Facts, Optional[FrozenSet[str]]]]] = {}
        self.calls: Dict[int, List[Tuple[Event, Optional[List[Facts]]]]] = {}
        for facts in self.facts:
            resolved = []
            for event, datum in self.uses[id(facts)]:
                if event.kind == "call" and datum is None:
                    targets = self.callees(facts, event)
                    resolved.append((event, targets))
                    for target in targets or ():
                        sites.setdefault(id(target), []).append((facts, event.locks))
            self.calls[id(facts)] = resolved
        self.entry: Dict[int, Optional[FrozenSet[str]]] = {id(f): frozenset() for f in self.facts}
        eligible = [f for f in self.facts if f.function.in_unnamed_namespace or _norm(f.function.name)
                    in self.private or ("static" in f.function.specifiers and not self.owner(f.function))]
        for _ in range(10):
            changed = False
            for facts in eligible:
                here = [_combine(locks, self.entry[id(caller)]) for caller, locks in sites.get(id(facts), [])]
                value = None if None in here else frozenset.intersection(*here) if here else frozenset()
                if value != self.entry[id(facts)]:
                    self.entry[id(facts)], changed = value, True
            if not changed:
                break

    def _shared(self, datum: Optional[_Datum]) -> bool:
        return datum is not None and not datum.atomic and "thread_local" not in datum.v.specifiers

    def _init(self, facts: Facts, event: Event, datum: _Datum) -> bool:
        f = facts.function
        return "init" in event.flags or (
            f.kind in ("constructor", "destructor") and datum.v.storage == "member"
            and self.owner(f) is not None and datum.v.name.startswith(self.owner(f) + "::")
            and not facts.this_escapes)

    @staticmethod
    def _publishes(event: Event) -> bool:
        return event.access == "write" or event.op in _PUBLISH

    @staticmethod
    def _acquires(event: Event) -> bool:
        return event.access == "read" or event.op in _OBSERVE

    def _roles(self) -> None:
        """An atomic publishes or guards data when it holds a pointer, when a function
        writes shared data and then stores it, or tests it in a condition and then
        accesses shared data. A counter (fetch_add, ++, ...) never does."""
        for facts in self.facts:
            uses = [(e, d) for e, d in self.uses[id(facts)] if d is not None and e.kind == "use"]
            for k, (event, datum) in enumerate(uses):
                if datum.atomic and ((self._publishes(event) and any(
                        self._shared(d) and e.access != "read" for e, d in uses[:k])) or (
                        self._acquires(event) and "condition" in event.flags
                        and any(self._shared(d) for e, d in uses[k + 1:]))):
                    datum.publication = True

    def _record(self, facts: Facts) -> None:
        uses = [(e, d) for e, d in self.uses[id(facts)] if d is not None]
        published = [(k, e, d) for k, (e, d) in enumerate(uses) if d.atomic and d.publication]
        for k, (event, datum) in enumerate(uses):
            locks = _combine(event.locks, self.entry[id(facts)])
            if locks is not None and self._shared(datum):
                locks = locks | {"atomic:" + d.v.name.rsplit("::", 1)[-1] for j, e, d in published
                                 if (j > k and self._publishes(e)) or (j < k and self._acquires(e))}
            access = event.access
            if "decays" in event.flags and "array" in datum.v.specifiers:
                access = "escape"           # `return buffer_;` from a function returning a pointer
            elif access == "call" and datum.v.storage == "member" and "mutable" not in datum.v.specifiers \
                    and "const" in facts.function.specifiers:
                access = "read"             # a member is const in a const member function
            datum.accesses.append(_Access(facts, event, access, locks, self._init(facts, event, datum)))

    def _judge(self, d: _Datum) -> None:
        live = [a for a in d.accesses if not a.init]
        spec = d.v.specifiers
        if "thread_local" in spec:
            escaped = [a for a in live if a.access == "escape"]
            d.sync, d.note = ("unknown", "the address of a thread_local escapes") if escaped else (
                "not-needed", "thread_local")
            d.offending = set(map(id, escaped))
            return
        if d.atomic:
            orders = sorted({o for a in live for o in self._orders(a.event)})
            d.sync = "atomic:" + ",".join(orders) if live else "not-needed"
            d.note = "publication or guard" if d.publication else ""
            return
        if not live:
            d.note = "initialised only" if d.accesses else "not accessed in the analysed set"
            return
        unknown = [a for a in live if a.locks is None]
        if unknown:
            d.sync, d.note = "unknown", "lockset unknown at line %d" % unknown[0].event.line
            d.offending = set(map(id, unknown))
            return
        writes = [a for a in live if a.access in ("write", "rmw")]
        maybe = [a for a in live if a.access in ("call", "escape")]
        bases = [{n.replace("(shared)", "") for n in a.locks} for a in live]
        common = set.intersection(*bases)
        const_writes = [a for a in writes if "mutable" in spec and "const" in a.facts.function.specifiers
                        and not a.locks]
        shared_writes = [a for a in writes + maybe if a.locks and all("(shared)" in n for n in a.locks)]
        escapes = [a for a in maybe if a.access == "escape" and a.locks]
        real = sorted(n for n in common if not n.startswith("atomic:"))
        locked = ", ".join((["lock:" + ",".join(real)] if real else []) + sorted(common - set(real)))
        if const_writes:
            d.sync, d.finding, d.offending = "missing", "const-writes-mutable", set(map(id, const_writes))
        elif shared_writes:
            d.sync, d.finding, d.offending = locked, "write-under-shared-lock", set(map(id, shared_writes))
        elif common:
            d.sync = locked
            if escapes:
                d.finding, d.offending = "reference-escapes-lock", set(map(id, escapes))
        elif not writes and not maybe:
            d.note = "read-only in the analysed set"
        elif all(not a.locks for a in live):
            if d.v.storage == "member":
                d.sync = "caller-must-synchronize"
            elif writes:
                d.sync, d.finding, d.offending = "missing", "unsynchronized", set(map(id, live))
            else:
                d.sync, d.note = "unknown", "passed on or returned by reference; no write seen"
                d.offending = set(map(id, maybe))
        else:
            d.sync, d.finding = "inconsistent", "inconsistent-locking"
            d.offending = set(map(id, [a for a in live if not a.locks] or live))

    def _orders(self, event: Event) -> List[str]:
        """Effective memory orders of one atomic access: (writer, reader) parts."""
        if event.access != "atomic":
            return ["seq_cst"] if event.access in ("read", "write", "rmw") else []
        at = _ORDER_AT.get(event.op, 1)
        given = [(event.orders[i] or "?") if i < len(event.orders) else None for i in (at, at + 1)]
        first = given[0] or "seq_cst"
        if event.op.startswith("compare_exchange"):
            failure = given[1] or {"acq_rel": "acquire", "release": "relaxed"}.get(first, first)
            return [first, failure]
        return [first]

    def _judge_atomic(self, a: _Access, d: _Datum, fenced: bool) -> Tuple[str, str]:
        """(finding, reason) of one atomic access, or ("", "")."""
        event = a.event
        orders = self._orders(event)
        if "?" in orders:
            return "unknown", "memory order of %s is not a literal" % event.op
        op = event.op or {"read": "load", "write": "store", "rmw": "fetch_add"}.get(event.access, "")
        if op.startswith("compare_exchange") and orders[1] in ("release", "acq_rel"):
            return "invalid-order", "%s failure order %s" % (op, orders[1])
        if orders and orders[0] in _INVALID.get(op, ()):
            return "invalid-order", "%s(%s)" % (op, orders[0])
        if not d.publication or fenced or not orders:
            return "", ""
        writer = op in _WRITER and orders[0] in ("relaxed", "acquire", "consume")
        reader_order = orders[-1] if op.startswith("compare_exchange") else orders[0]
        reader = op in _READER and op not in ("store", "clear") and reader_order in ("relaxed", "release")
        if (writer and op not in ("load", "test", "wait")) or (reader and not a.locks):
            return "relaxed-publication", "%s(%s) on %s, which publishes or guards data" % (
                op, ",".join(orders), d.v.name)
        return "", ""

    # -- entries
    def _datum_entry(self, d: _Datum) -> Entry:
        v = d.v
        record = Function(v.name, "datum", v.file, v.line, v.start_line, v.line, v.line, 0, frozenset(),
                          v.in_class_body, v.file.endswith((".h", ".hh", ".hpp", ".hxx", ".inl", ".ipp", ".tcc")),
                          v.in_unnamed_namespace, (-1, -1), ())
        metrics = dict.fromkeys(FINDINGS, 0)
        if d.finding:
            metrics[d.finding] = 1
        metrics["unknown"] = int(d.sync == "unknown")
        notes = tuple(Note(a.event.line, "access", 1, "%s %s %s in %s%s" % (
            a.access, _locks(a.locks), "init" if a.init else "", a.facts.function.name,
            " (lambda)" if "lambda" in a.event.flags else "")) for a in d.accesses)
        accesses = "; ".join("%d %s%s %s%s" % (a.event.line, a.access, "" if a.init else " " + _locks(a.locks),
                                                a.facts.function.name.rsplit("::", 1)[-1],
                                                " (init)" if a.init else "") for a in d.accesses)
        label = "%s %s: synchronization %s%s%s%s" % (
            v.storage, v.type, d.sync, ", " + d.finding if d.finding else "",
            " (%s)" % d.note if d.note else "", "; accesses: " + accesses if accesses else "")
        return Entry(d.source, record, metrics, notes, label)

    def _function_entries(self) -> List[Entry]:
        own: Dict[int, List[Tuple[str, str]]] = {}
        findings: Dict[int, List[Tuple[str, int, str]]] = {}
        flags: Dict[int, Set[str]] = {}
        streams: Dict[int, int] = {}
        for facts in self.facts:
            key, mine, found, marks = id(facts), [], [], set()
            uses = self.uses[key]
            atomic_ops = any(e.access == "atomic" or (d is not None and d.atomic) for e, d in uses)
            fenced = any(e.kind == "fence" for e, _ in uses)
            by_event = {id(a.event): a for d in {id(d): d for _, d in uses if d}.values()
                        for a in d.accesses if a.facts is facts}
            for event, datum in uses:
                where = event.line
                if datum is not None:
                    access = by_event[id(event)]
                    if access.init:
                        continue
                    value = self._contribution(access, datum, fenced, found)
                    mine.append((value, "" if datum.atomic else "%s line %d: %s" % (
                        datum.v.name, where, datum.finding or datum.note or datum.sync)))
                    if event.kind == "call":
                        mine.append(("unknown", "indirect call through %s line %d" % (event.name, where)))
                elif event.kind == "use" and "param" in event.flags:
                    write = event.access in ("write", "rmw", "call") and "const" not in event.flags
                    mine.append(("caller-synchronized:write" if write else "caller-synchronized:read",
                                 "parameter %s line %d" % (event.name, where)))
                elif event.kind == "lock-not-held":
                    found.append(("lock-not-held", where, "`%s` holds no lock" % event.name))
                elif event.kind == "libc":
                    found.append(("mt-unsafe-call", where, "%s is not thread-safe; use %s" % (
                        event.name, MT_UNSAFE[event.name])))
                elif event.kind == "fence":
                    if atomic_ops:
                        marks.add("fence: manual review")
                    else:
                        found.append(("fence-without-atomic", where, "a fence with no atomic operation "
                                      "orders nothing: make the data std::atomic or lock it"))
                elif event.kind == "effect":
                    marks.add("process-global-effect")
                elif event.kind == "stream":
                    streams[key] = streams.get(key, 0) + event.arity
            for event, targets in self.calls[key]:
                if targets is None:
                    what = "indirect call through" if event.access == "indirect" else "call to"
                    mine.append(("unknown", "%s %s line %d (not in the analysed set)" % (what, event.name, event.line)))
            for kind, where, reason in found:
                mine.append(("thread-hostile" if kind != "unknown" else "unknown", reason))
            marks |= self._atomicity(uses)
            own[key], findings[key], flags[key] = mine, found, marks
        sharing = {key: _join(*(v for v, _ in values)) for key, values in own.items()}
        writer = {key: streams.get(key, 0) > 0 for key in own}
        for _ in range(len(self.facts) + 1):
            changed = False
            for facts in self.facts:
                key = id(facts)
                targets = [t for _, ts in self.calls[key] for t in ts or ()]
                value = _join(sharing[key], *(sharing[id(t)] for t in targets))
                stream = writer[key] or any(writer[id(t)] for t in targets)
                if value != sharing[key] or stream != writer[key]:
                    sharing[key], writer[key], changed = value, stream, True
            if not changed:
                break
        # A message built from several output calls can interleave between threads: count
        # the function's own calls and its calls to functions that make exactly one.
        single = {id(f) for f in self.facts if streams.get(id(f), 0) == 1 and not any(
            writer[id(t)] for _, ts in self.calls[id(f)] for t in ts or ())}
        out, self.summary = [], {}
        for facts in self.facts:
            key = id(facts)
            stream_calls = streams.get(key, 0) + sum(1 for _, ts in self.calls[key]
                                                     if ts and any(id(t) in single for t in ts))
            if stream_calls >= 2:
                flags[key].add("shared-stream")
            metrics = dict.fromkeys(FINDINGS, 0)
            for kind, _, _ in findings[key]:
                metrics[kind] += kind != "unknown"
            metrics["unknown"] = int(sharing[key] == "unknown")
            reasons = list(dict.fromkeys(r for v, r in own[key] if v in ("unknown", "thread-hostile") and r))
            if sharing[key] != _join(*(v for v, _ in own[key])):
                reasons.append("through a callee")
            label = "sharing %s%s%s" % (sharing[key], "; flags: " + ", ".join(sorted(flags[key])) if flags[key] else "",
                                        "; " + "; ".join(reasons[:4]) + (" ..." if len(reasons) > 4 else "")
                                        if reasons else "")
            self.summary[facts.function.name] = (sharing[key], frozenset(flags[key]))
            notes = tuple(Note(line, kind, 1, reason) for kind, line, reason in findings[key])
            out.append(Entry(self.sources[facts.function.file], facts.function, metrics, notes, label))
        return out

    def _contribution(self, access: _Access, datum: _Datum, fenced: bool, found: list) -> str:
        event = access.event
        if datum.atomic:
            kind, reason = self._judge_atomic(access, datum, fenced)
            if kind:
                found.append((kind, event.line, reason))
            return "thread-hostile" if kind and kind != "unknown" else kind or "self-synchronized(unverified)"
        if datum.sync == "not-needed":     # a member is still the caller's object (C1)
            return "caller-synchronized:read" if datum.v.storage == "member" else "no-shared-state"
        if access.locks is None or (datum.sync == "unknown" and id(access) in datum.offending):
            return "unknown"
        if datum.finding and id(access) in datum.offending:
            return "thread-hostile"
        if access.locks:
            return "self-synchronized(unverified)"
        if datum.v.storage == "member":
            return "caller-synchronized:read" if access.access == "read" else "caller-synchronized:write"
        return "unknown"

    def _atomicity(self, uses) -> Set[str]:
        """C8: a plain store and a load of one atomic in one statement (`n = n + 1`)."""
        seen: Dict[Tuple[int, int], Set[str]] = {}
        for event, datum in uses:
            if datum is not None and datum.atomic:
                kind = "store" if event.access == "write" or event.op == "store" else (
                    "load" if event.access == "read" or event.op == "load" else "")
                seen.setdefault((id(datum), event.statement), set()).add(kind)
        return {"atomicity-suspect"} if any({"store", "load"} <= kinds for kinds in seen.values()) else set()
