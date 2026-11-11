#include <vector>

#if defined(_LIBCPP_HARDENING_MODE_FAST) && defined(LORICA_EXPECT_FAST)
static_assert(_LIBCPP_HARDENING_MODE == _LIBCPP_HARDENING_MODE_FAST);
#endif
#if defined(_LIBCPP_VERSION) && defined(LORICA_EXPECT_EXTENSIVE)
static_assert(_LIBCPP_HARDENING_MODE == _LIBCPP_HARDENING_MODE_EXTENSIVE);
#endif
#ifdef LORICA_EXPECT_FORTIFY_3
static_assert(__USE_FORTIFY_LEVEL == 3);
#endif

int main() {
    const std::vector<int> values{0};
    return values.front();
}
