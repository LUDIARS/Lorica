struct G{ int* p; CX G(int* q):p(q){} CX ~G(){ *p=1; } };
#ifdef WITNESS
constexpr int w(){ int x=0; { G g(&x); } return x; }
static_assert(w()==1,"");
#endif
