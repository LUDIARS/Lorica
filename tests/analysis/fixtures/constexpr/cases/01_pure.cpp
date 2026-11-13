CX int f(int a,int b){return a+b;}
#ifdef WITNESS
static_assert(f(1,2)==3,"");
#endif
