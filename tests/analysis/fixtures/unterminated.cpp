// The closing brace of first() is missing: everything after it is unparsed,
// no later function is reported with shifted lines.
int first(int a) {
    if (a) return 1;

int second(int a) { return a; }
int third(int a) { return a; }
