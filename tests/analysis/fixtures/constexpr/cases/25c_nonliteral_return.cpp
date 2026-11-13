struct NL{ NL(); ~NL(); int v;};
NL make();
CX NL f(){return make();}
#ifdef WITNESS
static_assert((f(),true),"");
#endif
