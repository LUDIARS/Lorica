CX int f(int a){ if (a<0) { asm(""); } return a; }
#ifdef WITNESS
static_assert(f(1)==1,"");
#endif
