CX void set(int* p,int v){*p=v;}
#ifdef WITNESS
constexpr int w(){ int x=0; set(&x,3); return x; }
static_assert(w()==3,"");
#endif
