// C8 (f22): `n = n + 1` on an atomic is two atomic operations: lost updates, no
// data race. A flag, not a finding.
#include <atomic>
std::atomic<long> n{0};
void inc() { n = n + 1; }
// expect: datum n atomic:seq_cst
// expect: sharing inc self-synchronized(unverified)
// expect: flag inc atomicity-suspect
// tsan: not-observable(an atomicity violation is not a data race; f22 lost 148,495 of 400,000 updates with 0 reports)
