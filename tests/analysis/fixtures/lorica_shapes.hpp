// Shapes from Lorica's headers and libstdc++ that broke earlier extractors.
// Not compiled.
#pragma once
#define LORICA_REJECT_MIXED(name) \
    template<int&..., class L, class R> \
        requires(!same_checked_integral<L, R>) \
    void name(L, R) = delete;
#define EXTERN_C_BEGIN extern "C" {
#define EXTERN_C_END }

namespace lorica {
// contracts.hpp: an #if inside a constructor's initializer list.
template <class Predicate>
class post_guard final {
public:
    post_guard(Predicate predicate, const char* comment) noexcept(
        std::is_nothrow_move_constructible_v<Predicate>)
        : predicate_(static_cast<Predicate&&>(predicate)), comment_(comment)
#if LORICA_DETAIL_CONTRACT_EXCEPTIONS
          , exceptions_on_entry_(std::uncaught_exceptions())
#endif
    {
    }
    ~post_guard() noexcept(false) {
#if LORICA_DETAIL_CONTRACT_EXCEPTIONS
        if (std::uncaught_exceptions() != exceptions_on_entry_) return;
#endif
        if (!predicate_()) fail(comment_);
    }
private:
    Predicate predicate_;
    const char* comment_;
    int exceptions_on_entry_ = 0;
};

// checked_integer.hpp: macro invocations without `;` before the next head.
LORICA_REJECT_MIXED(checked_add)
LORICA_REJECT_MIXED(checked_subtract)
#undef LORICA_REJECT_MIXED

template<int&..., class T, same_checked_integral<T> U>
[[nodiscard]] constexpr std::optional<T> checked_add(T left, U right) noexcept {
    if constexpr (std::is_signed_v<T>) {
        if ((right > 0 && left > max() - right) ||
            (right < 0 && left < min() - right)) return std::nullopt;
    } else if (left > max() - right) {
        return std::nullopt;
    }
    return static_cast<T>(left + right);
}
}  // namespace lorica

// A bare macro before a namespace and before a class head.
_GLIBCXX_BEGIN_NAMESPACE_VERSION namespace ranges {
inline int in_ranges(int a) { return a; }
}
_GLIBCXX_BEGIN_NAMESPACE_CXX11 template<typename _CharT> class basic_string {
public:
    _CharT front() const { return data_[0]; }
    _CharT* data_;
};

// A macro that opens a brace: its contents stay at file scope.
EXTERN_C_BEGIN
int c_api(int a) { return a; }
EXTERN_C_END

// A requires-expression is skipped; a requires-clause is part of the head.
template <class T>
concept sized = requires(T t) { t.size(); };
template <class T>
    requires sized<T>
int count(const T& t) requires (sizeof(T) > 0) { return t.size() ? 1 : 0; }

// Template-argument commas inside a logical sequence (tests/checked.cpp shape).
inline bool reads(reader& r) {
    return r.read_prefixed<std::uint8_t, std::endian::big>() && r.ok() && r.skip(2);
}
