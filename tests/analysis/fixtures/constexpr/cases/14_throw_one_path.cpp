CX int f(int a){ if(a<0) throw 1; return a; }
#ifdef WITNESS
static_assert(f(1)==1,"");
#endif
