#include <lorica/contracts.hpp>

#ifdef _WIN32
#define MODULE_EXPORT __declspec(dllexport)
#else
#define MODULE_EXPORT __attribute__((visibility("default")))
#endif

namespace LORICA_TEST_MODULE {
using namespace lorica::contracts;

MODULE_EXPORT violation_handler set(violation_handler handler) noexcept {
    return set_violation_handler(handler);
}

MODULE_EXPORT violation_handler get() noexcept {
    return get_violation_handler();
}

MODULE_EXPORT void violate() {
    LORICA_CONTRACT_ASSERT(false);
}
}
