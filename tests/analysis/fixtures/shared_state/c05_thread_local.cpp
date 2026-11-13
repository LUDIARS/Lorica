// C5 (f06, f06b, f20): a thread_local is not shared unless its address escapes;
// errno is thread-local (a macro, never a datum here).
#include <cerrno>
#include <cstdlib>
int bump() { thread_local int n = 0; return ++n; }
int* slot() { thread_local int s = 0; return &s; }
long parse(const char* text) { errno = 0; long v = std::strtol(text, nullptr, 10); return errno ? -1 : v; }
// expect: datum bump::n not-needed
// expect: datum slot::s unknown
// expect: finding unknown slot::s
// expect: finding unknown slot
// expect: sharing bump no-shared-state
// expect: sharing slot unknown
// expect: sharing parse no-shared-state
// setup: int* p = slot();
// tsan: clean | sink(bump()) | sink(bump())
// tsan: race | ++*p | ++*p
// tsan: clean | sink(parse("99999999999999999999999")) | sink(parse("12"))
