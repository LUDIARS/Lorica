// C3 (f03, f04): a const static local is initialised thread-safely; a mutable one
// written on every call is shared state.
struct T { int x; T() { x = 42; } };
const T& inst() { static const T t; return t; }
int next_id() { static int counter = 0; return ++counter; }
// expect: datum T::x not-needed
// expect: datum next_id::counter missing
// expect: finding unsynchronized next_id::counter
// expect: sharing inst no-shared-state
// expect: sharing next_id thread-hostile
// tsan: clean | sink(inst().x) | sink(inst().x)
// tsan: race | sink(next_id()) | sink(next_id())
