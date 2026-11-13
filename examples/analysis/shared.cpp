// Request accounting shared by worker threads; stands for a consumer's code.
#include <atomic>
#include <mutex>
#include <string>

std::atomic<long> served{0};    // atomic: a relaxed counter is enough
long failures = 0;              // written by every worker without a lock
thread_local int depth = 0;     // one per thread
const int max_retries = 3;      // const: not shared state
int port = 8080;                // only read in this file

class registry {
    std::mutex m_;
    std::string name_;          // always under m_
    int hits_ = 0;              // under m_ in add(), not in peek()
    int size_ = 0;              // never locked: callers must synchronise
    int total_ = 0;             // written after unlock(): lockset unknown
public:
    void rename(const std::string& name) { std::lock_guard<std::mutex> g(m_); name_ = name; }
    std::string name() { std::lock_guard<std::mutex> g(m_); return name_; }
    void add() { std::lock_guard<std::mutex> g(m_); ++hits_; }
    int peek() const { return hits_; }
    void grow() { ++size_; }
    void reset() { std::unique_lock<std::mutex> g(m_); g.unlock(); total_ = 0; }
};

int configured_port() { return port; }

void serve(bool ok) {
    served.fetch_add(1, std::memory_order_relaxed);
    ++depth;
    if (!ok) ++failures;
    --depth;
}
