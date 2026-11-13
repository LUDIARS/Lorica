CX double f(double a,double b){ return a/b; }
#ifdef WITNESS
static_assert(f(1.0,2.0)==0.5,"");
#endif
