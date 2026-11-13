// C2 (f01): a const member function writes a mutable member without a lock.
struct Cache {
    int v = 3;
    mutable int cache = 0;
    int get() const { if (!cache) cache = v * 2; return cache; }
};
// expect: datum Cache::v not-needed
// expect: datum Cache::cache missing
// expect: finding const-writes-mutable Cache::cache
// expect: sharing Cache::get thread-hostile
// setup: Cache c;
// tsan: race | sink(c.get()) | sink(c.get())
