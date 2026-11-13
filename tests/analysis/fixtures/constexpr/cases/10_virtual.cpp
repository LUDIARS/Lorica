struct B{ CX virtual int f() const {return 1;} };
#ifdef WITNESS
constexpr B b{};
static_assert(b.f()==1,"");
#endif
