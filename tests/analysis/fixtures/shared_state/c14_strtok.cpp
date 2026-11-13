// C14 (f21): an MT-Unsafe C library function: thread-hostile by knowledge.
#include <cstring>
int count(char* s) { int n = 0; for (char* t = std::strtok(s, " "); t; t = std::strtok(nullptr, " ")) ++n; return n; }
// expect: finding mt-unsafe-call count
// expect: sharing count thread-hostile
// tsan: not-observable(libc is not instrumented; f21 reported 0 races while 2,550 of 400,000 results were wrong)
