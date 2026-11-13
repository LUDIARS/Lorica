CX int f(const volatile int& v){ return v; }
#ifdef WITNESS
constexpr int g=1;
static_assert(f(g)==1,"");
#endif
