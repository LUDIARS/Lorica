// A function the extractor cannot read (here a K&R definition) is an unparsed
// region: its write is not in the table, and the run says so.
int shared = 0;
int old_style(a) int a; { shared = a; return a; }
int read_shared() { return shared; }
// expect: datum shared not-needed
// expect: sharing read_shared no-shared-state
// tsan: not-observable(not C++; the point is the unparsed report)
