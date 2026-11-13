struct NL{ NL(); ~NL(); int v;};
CX int f(const NL& n){return n.v;}
#ifdef WITNESS
extern NL g;
static_assert(f(g)==0,"");
#endif
