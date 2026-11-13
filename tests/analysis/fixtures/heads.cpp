// Head classification: one case per rule. Not compiled.
#define API
#define NOEXCEPT noexcept
#define TEST(suite, name) void suite##_##name()
#define EXPORT_CLASS
#define BEGIN_NS namespace ns {
#define END_NS }

struct Widget {
    int a_ = 0, b_{1};
    int bits : 3;
    int z = {5};
    Widget() : a_{1}, b_(2) {}
    explicit Widget(int x) try : a_(x) { if (x < 0) throw 1; } catch (...) { a_ = 0; }
    ~Widget() { a_ = 0; }
    operator bool() const { return a_ != 0; }
    bool operator()(int x, int y) const { return x < y && y < a_; }
    auto operator<=>(const Widget& other) const { return a_ <=> other.a_; }
    Widget& operator<<(int v) { if (v) a_ += v; return *this; }
    void f(int x = int{3}, int y = {1}) { if (x) a_ = y; }
    template <class T> requires requires(T t) { t.size(); }
    int g(T&& t) { return t.size() > 3 ? 1 : 0; }
    int h() const requires (sizeof(int) == 4) { return a_ ? 1 : 2; }
    auto t() -> decltype(a_) { return a_; }
    void m() & {}
    void n() && noexcept {}
    static constexpr int s() noexcept { return 1; }
    virtual int v() const { return 2; }
    bool operator== [[nodiscard]] (const Widget&) const { return true; }
};

long double operator""_km(long double x) { return x * 1000; }

API int after_macro(int a) NOEXCEPT {
    return a;
}

TEST(Suite, Name) {
    int x = 1;
    if (x) x = 2;
}

class EXPORT_CLASS Exported {
public:
    int get() const { return 1; }
};

EXPORT_CLASS namespace prefixed {
inline int inside() { return 1; }
}

namespace {
int hidden(int a, int b, int c) { return a + b + c; }
}

namespace outer::inner {
template <typename T, typename U>
constexpr T Widget2_convert(U u) noexcept(noexcept(T(u))) { return T(u); }
}

auto lambda_at_scope = [](int a) { return a ? 1 : 2; };

int Widget3_out_of_line();
int ::global_qualified() { return 0; }
