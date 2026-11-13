int f(int);
CX int f(int a){return a;}
#ifdef WITNESS
static_assert(f(1)==1,"");
#endif
