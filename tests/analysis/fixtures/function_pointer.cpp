// A function returning a function pointer: unparsed, not guessed.
int (*returns_fp(int a))(int) { return nullptr; }
int after(int a) { return a; }
