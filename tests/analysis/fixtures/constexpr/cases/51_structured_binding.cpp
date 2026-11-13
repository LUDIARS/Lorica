struct P{int a,b;};
CX int f(P p){ auto [x,y]=p; return x+y; }
#ifdef WITNESS
static_assert(f(P{1,2})==3,"");
#endif
