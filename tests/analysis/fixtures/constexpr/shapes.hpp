// Locator shapes for the constexpr subcommand, many taken from Lorica's headers.
#pragma once
#define LORICA_API __attribute__((visibility("default")))

[[nodiscard]] LORICA_API const char* to_string(int kind) noexcept;
[[noreturn]] inline void trap() noexcept { __builtin_trap(); }
constexpr int already(int a) { return a; }

class sealed {
public:
    explicit sealed(int value) : value_(value) {}
    int load() const noexcept { return value_; }
    static int limit() noexcept { return 8; }
    friend bool same(const sealed& a, const sealed& b) { return a.value_ == b.value_; }
private:
    int value_;
};

struct literal {
    constexpr literal(int v) : v_(v) {}
    explicit operator bool() const { return v_ != 0; }
    virtual int twice() const { return 2 * v_; }
    int get() const;
    int v_;
};
inline int literal::get() const { return v_; }

struct plain {
    int v;
    int get() const { return v; }
};

template <class T>
class guard {
public:
    explicit guard(T value) : value_(value) {}
    ~guard() noexcept(false) {}
    T value_;
};

template <class T>
    requires(sizeof(T) > 1)
[[nodiscard]] T read() { return T{}; }

auto twice = [](int x) { return 2 * x; };

int quiet(int a) { return a; } // lorica-analyze: ignore(constexpr) kept as a run-time function
int unexplained(int a) { return a; } // lorica-analyze: ignore(constexpr)
int one() { return 1; } int two() { return 2; }
