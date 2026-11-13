CX int f(int a){ if(a) goto done; a=1; done: return a; }
#ifdef WITNESS
static_assert(f(0)==1,"");
#endif
