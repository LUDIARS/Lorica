// C1 (f15, f15b): a const getter reads a plain member. The same function races or
// not depending only on the caller: the class is caller-synchronized.
class Cfg {
    int level_ = 5;
public:
    int level() const { return level_; }
    void set_level(int v) { level_ = v; }
};
// expect: datum Cfg::level_ caller-must-synchronize
// expect: sharing Cfg::level caller-synchronized:read
// expect: sharing Cfg::set_level caller-synchronized:write
// setup: Cfg c;
// tsan: race | sink(c.level()) | c.set_level(i)
// tsan: clean | sink(c.level()) | sink(c.level())
