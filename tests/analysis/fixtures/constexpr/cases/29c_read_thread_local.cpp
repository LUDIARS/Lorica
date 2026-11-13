thread_local bool flag=false;
CX bool f(){ return flag; }
#ifdef WITNESS
static_assert(!f(),"");
#endif
