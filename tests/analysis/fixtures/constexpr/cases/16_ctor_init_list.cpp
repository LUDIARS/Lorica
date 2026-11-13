struct P{int x,y; CX P(int a,int b):x(a),y(b){} };
#ifdef WITNESS
constexpr P p{1,2};
static_assert(p.y==2,"");
#endif
