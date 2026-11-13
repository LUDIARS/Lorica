// Adversarial constructs from the parsing review (fx/hard.cpp). Not compiled.
#include <cassert>
#include <cstdlib>
#include <mutex>
#include <vector>
#include <string>
#include <utility>
#define DEFINE_GETTER(T, n) T get_##n() const { return n##_; }
#define BEGIN_FN(name) int name(int a) {
#define END_FN }
#define FOREACH(x, c) for (auto& x : c)
#define API
#define NOEXCEPT noexcept

struct Widget {
    int a_ = 0, b_{1};
    DEFINE_GETTER(int, a)
    DEFINE_GETTER(int, b)
    Widget() : a_{1}, b_(2) {}
    explicit Widget(int x) try : a_(x) { if (x < 0) throw 1; } catch (...) { std::abort(); }
    operator bool() const { return a_ != 0; }
    bool operator()(int x, int y) const { return x < y && y < a_; }
    auto operator<=>(const Widget&) const = default;
    Widget& operator<<(int v) { if (v) a_ += v; return *this; }
    void f(int x = int{3}, std::vector<int> v = {1, 2, 3}) { if (x) v.clear(); }
    template <class T> requires requires(T t) { t.size(); }
    int g(T&& t) { return t.size() > 3 ? 1 : 0; }
    int h() const requires (sizeof(int) == 4) { return a_ ? 1 : 2; }
};

BEGIN_FN(macro_opened)
    if (a > 0) return 1;
    return 0;
END_FN

API int after_macro(int a) NOEXCEPT {
    assert(a > 0);
    return a;
}

int uniform_or_shift(int i, int first, int last) {
    if (first != last)
        for (int k = first; k != last; ++k) {
            if (i != k) ++i;
        }
    return i;
}

template <class T, class U>
auto fwd(T&& t, U&& u) -> decltype(std::forward<T>(t) + std::forward<U>(u)) {
    auto&& r = std::forward<T>(t);
    return static_cast<T&&>(r) + std::forward<U&&>(u);
}

int loops(std::vector<int>& c, std::mutex& m) {
    int n = 0;
    FOREACH(x, c) { if (x) ++n; }
    if (std::lock_guard<std::mutex> g{m}; n > 2) { n = 0; }
    switch (int k = n; k) { case 0: n = 1; break; case 1: [[fallthrough]]; default: n = 2; }
    auto cmp = [&](int a, int b) { return a < b || (a == b && n); };
    do { --n; } while (n > 0 && cmp(n, 1));
    return n > 0 ? n : -n;
}

int kr(a, b) int a; int b; { return a && b; }

#ifdef SOMETHING
int split_head(int a) {
#else
int split_head(long a) {
#endif
    if (a) return 1;
    return 0;
}

int recursion_overload(int x);
int recursion_overload(long x) { return recursion_overload(static_cast<int>(x)); }
const char* raw = R"x(
int not_a_function(int a) { if (a) { return 1; } }
)x";
int digits() { return 1'000'000 + '{' + '\'' ; }
int labels(int a) { again: if (a-- > 0) goto again; return a; }
struct S2 { int x : 3; int y{4}; int z = {5}; int arr[2] = {1, 2}; void m() & {} void n() && noexcept {} };
int (*returns_fp(int a))(int) { return nullptr; }
auto lam = [](int a) { return a ? 1 : 2; };
int braced(int i, int first, int last) {
    if (first != last) {
        for (int k = first; k != last; ++k) {
            if (i != k) ++i;
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
