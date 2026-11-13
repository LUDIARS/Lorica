struct S{ int get() const; int v; };
CX int f(const S& s){return s.get();}
#ifdef WITNESS
constexpr S s{1};
static_assert(f(s)==1,"");
#endif
