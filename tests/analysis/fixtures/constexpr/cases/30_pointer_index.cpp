CX int f(const int* p, int n){ int s=0; for(int i=0;i<n;++i) s+=p[i]; return s; }
#ifdef WITNESS
constexpr int a[]={1,2,3};
static_assert(f(a,3)==6,"");
#endif
