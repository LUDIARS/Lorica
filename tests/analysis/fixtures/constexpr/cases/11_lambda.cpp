CX int f(int a){ auto l=[a](int b){return a+b;}; return l(1);}
#ifdef WITNESS
static_assert(f(1)==2,"");
#endif
