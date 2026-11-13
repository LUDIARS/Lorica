int ext(int);
template<class T> CX int f(T){ return ext(1); }
int use(){ return f(0); }
#ifdef WITNESS
static_assert(f(0)==0,"");
#endif
