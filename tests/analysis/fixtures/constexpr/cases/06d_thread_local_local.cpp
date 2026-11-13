CX int f(){ thread_local int n=0; return n; }
#ifdef WITNESS
static_assert(f()==0,"");
#endif
