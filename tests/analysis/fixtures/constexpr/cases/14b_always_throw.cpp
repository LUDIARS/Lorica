CX int f(int){ throw 1; }
#ifdef WITNESS
static_assert(f(1)==1,"");
#endif
