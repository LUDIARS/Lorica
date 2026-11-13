// Complexity fixtures; expected values are derived by hand in test_complexity.py.
// Compiles as C++20 (clang-tidy cross-check); every function body is braced.
#include <utility>

int f2(int a, int b) { return a + b; }

int else_if_chain(int a) {
    if (a == 0) { return 0; }
    else if (a == 1) { return 1; }
    else if (a == 2) { return 2; }
    else { return 3; }
}

int do_while(int n) {
    do {
        --n;
    } while (n > 0);
    return n;
}

int ternaries(int a, int b) {
    return f2(a ? 1 : 2, b ? (a ? 3 : 4) : 5);
}

bool mixed(bool a, bool b, bool c) { return a && b || c; }

bool grouped(bool a, bool b, bool c) { return a && (b && c); }

bool alternating(bool a, bool b, bool c, bool d) { return a || b && c || d; }

int lambda_nesting(int n) {
    auto f = [&](int x) {
        if (x > n) { return 1; }
        return 0;
    };
    return f(n);
}

int switcher(int k) {
    switch (k) {
    case 0: return 1;
    case 1:
    case 2: return 2;
    default: return 3;
    }
}

int catcher(int k) {
    try {
        if (k) { throw k; }
    } catch (int e) {
        if (e) { return e; }
    } catch (...) {
        return -1;
    }
    return 0;
}

int jumper(int a) {
again:
    if (a-- > 0) { goto again; }
    return a;
}

int braced(int i, int first, int last) {
    if (first != last) {
        for (int k = first; k != last; ++k) {
            if (i != k) { ++i; }
        }
    }
    return i;
}

int unbraced(int i, int first, int last) {
    if (first != last)
        for (int k = first; k != last; ++k)
            if (i != k) ++i;
    return i;
}

template <class T, class U>
auto forwarding(T&& t, U&& u) -> decltype(t + u) {
    auto&& r = static_cast<T&&>(t);
    return r + static_cast<U&&>(std::forward<U&&>(u));
}

template <class... B>
bool all_of(B... b) { return (... && b); }

int ternary_in_else_if(int a, int b) {
    if (a) { return 1; }
    else if (b ? 1 : 0) { return 2; }
    else { return 3; }
}

int with_initializer(int n) {
    if (int k = n * 2; k > 3) { return k; }
    if constexpr (sizeof(int) == 4) { return 1; } else { return 2; }
}

int searching(const int* p, int n, int v) {
    int i = 0;
    while (i < n && p[i] != v) {
        for (int j = 0; j < i; ++j) {
            if (p[j] == v || p[j] < 0) { return j; }
        }
        ++i;
    }
    return -1;
}

int else_nesting(int a, int b) {
    if (a) {
        return 1;
    } else {
        if (b) { return 2; }
    }
    return 0;
}

int ternary_chain(int a, int b) { return a ? 1 : b ? 2 : 3; }

int local_class(int n) {
    struct guard {
        int* p;
        ~guard() { if (p) { *p = 0; } }
    };
    guard g{&n};
    return n;
}

template <class T>
int requires_in_body(const T& t) {
    if constexpr (requires { t.size(); }) { return 1; }
    return 0;
}

int range_for(const int (&values)[4]) {
    int sum = 0;
    for (int v : values) {
        sum += v > 0 ? v : 0;
    }
    return sum;
}
