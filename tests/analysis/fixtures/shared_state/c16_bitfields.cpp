// C16 (f23): two bit-fields share one memory location; the tool treats the whole
// object `f` as one datum, so the race is reported.
struct F { unsigned a : 4; unsigned b : 4; } f{};
void set_a(int i) { f.a = i & 7; }
void set_b(int i) { f.b = i & 7; }
// expect: datum F::a not-needed
// expect: datum F::b not-needed
// expect: datum f missing
// expect: finding unsynchronized f
// tsan: race | set_a(i) | set_b(i)
