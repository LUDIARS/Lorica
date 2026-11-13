CX int f(const void* p){ return *static_cast<const int*>(p);}
#ifdef WITNESS
constexpr int g=4;
static_assert(f(&g)==4,"");
#endif
