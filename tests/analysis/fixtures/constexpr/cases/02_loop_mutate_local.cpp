CX int f(int n){int s=0; for(int i=0;i<n;++i) s+=i; return s;}
#ifdef WITNESS
static_assert(f(4)==6,"");
#endif
