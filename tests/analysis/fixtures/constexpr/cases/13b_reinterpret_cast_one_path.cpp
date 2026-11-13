CX const char* f(const int* p, bool raw){ if (raw) return reinterpret_cast<const char*>(p); return nullptr;}
#ifdef WITNESS
static_assert(f(nullptr,false)==nullptr,"");
#endif
