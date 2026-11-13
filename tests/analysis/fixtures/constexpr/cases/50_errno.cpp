#include <cerrno>
CX int f(){ return errno; }
#ifdef WITNESS
static_assert(f()==0,"");
#endif
