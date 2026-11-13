union U{int i; float f;};
CX int f(float x){ U u{}; u.f=x; return u.i; }
#ifdef WITNESS
static_assert(f(0.0f)==0,"");
#endif
