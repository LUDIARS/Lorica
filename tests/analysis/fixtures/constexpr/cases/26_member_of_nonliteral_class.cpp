struct NL{ NL(); ~NL(); int v; CX int get() const {return v;} };
#ifdef WITNESS
extern NL g;
static_assert(g.get()==0,"");
#endif
