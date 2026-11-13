struct V{ int x; };
V operator+(V a, V b);            // not constexpr: a hidden call behind '+'
CX V f(V a, V b){ return a + b; }
#ifdef WITNESS
static_assert(f(V{1},V{2}).x==3,"");
#endif
