CX int f(){ static int n=0; return ++n; }
#ifdef WITNESS
static_assert(f()==1,"");
#endif
