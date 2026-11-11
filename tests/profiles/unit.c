#if defined(_GLIBCXX_ASSERTIONS) || defined(_LIBCPP_HARDENING_MODE)
#error C translation units must not receive C++ library options
#endif
int lorica_profile_c_unit(void) { return 0; }
