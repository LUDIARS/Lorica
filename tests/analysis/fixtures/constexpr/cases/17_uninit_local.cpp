CX int f(int a){ int r; r=a; return r; }
#ifdef WITNESS
static_assert(f(1)==1,"");
#endif
