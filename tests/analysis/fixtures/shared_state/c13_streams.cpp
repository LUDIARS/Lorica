// C13 (f19, f19c): each stdio call or synchronised iostream call is data-race-free;
// a message built from several calls can interleave: a flag, not a race.
#include <cstdio>
#include <iostream>
void say(int i) { std::cout << "a" << i << '\n'; }
void put(int i) { std::fprintf(stdout, "b%d\n", i); }
void put_twice(int i) { put(i); std::fputs("\n", stdout); }
// expect: sharing say no-shared-state
// expect: flag say shared-stream
// expect: flag put_twice shared-stream
// tsan: clean | say(i) | put_twice(i)
