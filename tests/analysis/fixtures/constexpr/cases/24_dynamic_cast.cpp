struct B{ virtual ~B()=default; }; struct D:B{};
CX bool f(const B& b){ return dynamic_cast<const D*>(&b)!=nullptr; }
#ifdef WITNESS
constexpr bool w(){ D d; return f(d); }
static_assert(w(),"");
#endif
