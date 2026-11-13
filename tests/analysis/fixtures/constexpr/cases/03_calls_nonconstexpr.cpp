int ext(int);
CX int f(int a){return ext(a);}
#ifdef WITNESS
static_assert(f(1)>=0||true,"");
#endif
