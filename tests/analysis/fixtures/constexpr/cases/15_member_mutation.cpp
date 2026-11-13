struct C{int v; CX void inc(){++v;} CX int get() const {return v;}};
#ifdef WITNESS
constexpr int w(){ C c{1}; c.inc(); return c.get(); }
static_assert(w()==2,"");
#endif
