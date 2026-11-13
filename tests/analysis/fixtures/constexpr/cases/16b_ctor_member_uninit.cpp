struct Q{int x; int y; CX Q(int a):x(a){} };
#ifdef WITNESS
constexpr int w(){ Q q{1}; return q.x; }
static_assert(w()==1,"");
#endif
