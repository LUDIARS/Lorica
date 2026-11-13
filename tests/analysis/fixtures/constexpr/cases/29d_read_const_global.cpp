const int g = 7;
CX int f(){return g;}
#ifdef WITNESS
static_assert(f()==7,"");
#endif
