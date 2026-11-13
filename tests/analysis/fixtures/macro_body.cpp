// A macro that opens and closes a function body: unparsed, never a guessed function.
#define BEGIN_FN(name) int name(int a) {
#define END_FN }

BEGIN_FN(macro_opened)
    if (a > 0) return 1;
    return 0;
END_FN

int after_macro(int a) { return a; }
