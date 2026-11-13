// C10 (f17): the getter locks, then returns a reference: the caller reads unlocked.
#include <mutex>
#include <vector>
class Box {
    mutable std::mutex m_;
    std::vector<int> v_{1, 2, 3};
public:
    const std::vector<int>& items() const { std::lock_guard<std::mutex> g(m_); return v_; }
    std::size_t size() const { std::lock_guard<std::mutex> g(m_); return v_.size(); }
    void add(int x) { std::lock_guard<std::mutex> g(m_); v_.push_back(x); }
};
// expect: datum Box::v_ lock:m_
// expect: finding reference-escapes-lock Box::v_
// expect: sharing Box::size self-synchronized(unverified)
// setup: Box b;
// tsan: race | sink(b.items().size()) | b.add(i)
// tsan: clean | sink(b.size()) | b.add(i)
