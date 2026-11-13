// C11 (f16): the setter locks, the getter does not. Constructor writes are exempt.
#include <mutex>
class Cfg {
    mutable std::mutex m_;
    int level_;
public:
    Cfg() { level_ = 0; }
    int level() const { return level_; }
    void set_level(int v) { std::lock_guard<std::mutex> g(m_); level_ = v; }
};
// expect: datum Cfg::level_ inconsistent
// expect: finding inconsistent-locking Cfg::level_
// expect: sharing Cfg::level thread-hostile
// expect: sharing Cfg::set_level self-synchronized(unverified)
// setup: Cfg c;
// tsan: race | sink(c.level()) | c.set_level(i)
