CX int f(int i){ static const int k=3; return k+i; }
#ifdef WITNESS
static_assert(f(1)==4,"");
#endif
