struct NC{ int size_nc() const; };
template<class T> CX int f(T t){ return t.size_nc(); }
int use(){ return f(NC{}); }
#ifdef WITNESS
static_assert(f(NC{})==0,"");
#endif
