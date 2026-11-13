struct NL{ NL(); ~NL(); int v;};
CX int f(NL n){return n.v;}
#ifdef WITNESS
static_assert(f(NL{})==0,"");
#endif
