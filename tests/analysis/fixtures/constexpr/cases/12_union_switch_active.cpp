union U{int i; float f;};
CX int f(){ U u{}; u.f=1.0f; return 1; }
#ifdef WITNESS
static_assert(f()==1,"");
#endif
