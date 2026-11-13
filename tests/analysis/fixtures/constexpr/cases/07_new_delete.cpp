CX int f(int a){ int* p = new int(a); int r=*p; delete p; return r; }
#ifdef WITNESS
static_assert(f(3)==3,"");
#endif
