int g;
CX int f(){return g;}
#ifdef WITNESS
static_assert(f()==0,"");
#endif
