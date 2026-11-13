CX int f(int a){ try { return a; } catch(...) { return 0; } }
#ifdef WITNESS
static_assert(f(1)==1,"");
#endif
