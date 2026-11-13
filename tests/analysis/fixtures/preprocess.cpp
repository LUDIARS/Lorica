// Conditional groups the pre-pass must resolve. Not compiled.
#ifdef WIDE
int split_head(long a) {
#else
int split_head(int a) {
#endif
    if (a) return 1;
    return 0;
}

void split_arguments(int a, int b) {
    consume(a,
#if MODERN
            forward(b));
#else
            b);
#endif
    if (a) consume(b);
}

int split_else(int a) {
#if FAST
    if (a > 0)
        return a;
    else
    {
#endif
    a += 1;
#if FAST
    }
#endif
    return a;
}

#if 0
int disabled( {
#endif

int balanced_in_body(int a) {
#if FAST
    if (a > 0) return a;
#else
    for (; a < 0; ++a) {}
#endif
    return a;
}

int after_all(int a) { return a ? 1 : 0; }
