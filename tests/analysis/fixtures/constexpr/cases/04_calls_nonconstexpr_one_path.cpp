int ext(int);
CX int f(int a){return a>0 ? a : ext(a);}
#ifdef WITNESS
static_assert(f(1)==1,"");
#endif
