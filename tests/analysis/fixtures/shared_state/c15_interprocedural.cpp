// C15 (f27, f28, f28b): the forwarder inherits its callee's sharing; a reference
// parameter is the caller's; unresolved calls are unknown; recursion terminates;
// an overload set joins.
int counter = 0;
void bump_impl() { ++counter; }
void bump() { bump_impl(); }
void add(int& out, int v) { out += v; }
void external();
void calls_out() { external(); }
int depth(int n) { return n ? depth(n - 1) : 0; }
void h(int) { ++counter; }
void h(double) {}
void calls_h() { h(1.0); }
// expect: datum counter missing
// expect: finding unsynchronized counter
// expect: finding unknown calls_out
// expect: sharing bump thread-hostile
// expect: sharing add caller-synchronized:write
// expect: sharing calls_out unknown
// expect: sharing depth no-shared-state
// expect: sharing calls_h thread-hostile
// setup: int x = 0, y = 0;
// tsan: race | bump() | bump()
// tsan: race | add(x, 1) | add(x, 1)
// tsan: clean | add(x, 1) | add(y, 1)
