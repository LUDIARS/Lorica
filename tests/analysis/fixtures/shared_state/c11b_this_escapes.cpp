// C11: a constructor that passes `this` on is not exempt: its write counts.
#include <mutex>
struct Node;
void enrol(Node* node);
struct Node {
    std::mutex m;
    int value;
    Node() { enrol(this); value = 1; }
    int get() { std::lock_guard<std::mutex> g(m); return value; }
};
// expect: datum Node::value inconsistent
// expect: finding inconsistent-locking Node::value
// expect: sharing Node::Node thread-hostile
// tsan: not-observable(needs a second thread that reaches the object through enrol)
