int ext(int a){ return a+1; }
CX int f(int a){return ext(a);}
#ifdef WITNESS
static_assert(f(1)==2,"");
#endif
