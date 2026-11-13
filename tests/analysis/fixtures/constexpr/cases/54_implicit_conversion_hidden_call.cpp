struct W{ W(int); int x; };       // non-constexpr converting constructor
CX int f(int a){ W w = a; return w.x; }
#ifdef WITNESS
static_assert(f(1)==1,"");
#endif
