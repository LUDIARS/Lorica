// Shadowing: a parameter or a local of the same name is not the global; the local
// ends with its block.
int counter = 0;
int by_parameter(int counter) { return ++counter; }
int by_local() { int counter = 0; return ++counter; }
void after_block() { { int counter = 1; (void)counter; } ++counter; }
// expect: datum counter missing
// expect: finding unsynchronized counter
// expect: sharing by_parameter no-shared-state
// expect: sharing by_local no-shared-state
// expect: sharing after_block thread-hostile
// tsan: clean | sink(by_parameter(i)) | sink(by_local())
// tsan: race | after_block() | after_block()
