CX int f(int i){ static constexpr int t[]={1,2,3}; return t[i]; }
#ifdef WITNESS
static_assert(f(1)==2,"");
#endif
