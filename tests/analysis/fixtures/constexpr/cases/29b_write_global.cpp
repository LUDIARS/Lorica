int g;
CX void f(){ g = 1; }
#ifdef WITNESS
static_assert((f(),true),"");
#endif
