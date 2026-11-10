# Checked integers, bounded text and byte reading

Three headers of `Lorica::boundary` for the defects that most often turn hostile
input into memory corruption: integer overflow and truncation before a size is
used (CWE-190, CWE-191, CWE-197), unbounded string copies and formats (CWE-120,
CWE-134, CWE-170) and pointer arithmetic over untrusted bytes (CWE-125, CWE-130).
They are the replacements `lorica_deprecate_unsafe_apis` points to
([SPEC-LR-UNSAFE-API](security-contracts.md#SPEC-LR-UNSAFE-API)).

Language: C++20 is the minimum (concepts, `std::in_range`, `std::span`, ranges).
Newer library features are used when the library announces them, with the same
results otherwise: C++26 saturation arithmetic (`std::add_sat`, `std::saturate_cast`).
`format_into` exists only where the library defines `__cpp_lib_format`
(libstdc++ 13, libc++ 19, the MSVC STL); libc++ 18 ships `<format>` without it. Each header
stops compilation with an `#error` under an older standard instead of compiling
differently. The C++17 headers (`checked_size`, `byte_view`, `input_budget`) are
unchanged and independent of these.

Errors are values: every function returns an empty `std::optional` (or a clamped
value for the saturating forms) and is `noexcept`, except `format_into`, through
which a formatter may throw (`std::format_error` for a negative dynamic width,
`std::bad_alloc` where the library formats through a heap buffer, or a user
formatter's exception); the destination then holds an empty string, and nothing
was written past it. No other function allocates, and none aborts or keeps state
beyond its arguments.

## Integers {#SPEC-LR-INTEGER}

`<lorica/checked_integer.hpp>`. `checked_integral` is every integer type except
`bool` and the character types, whose arithmetic is almost always a defect.

- `narrow<To>(value)`: the value in `To`, or empty when it is not representable.
- `checked_add`, `checked_subtract`, `checked_multiply`, `checked_divide`: the exact
  result, or empty on overflow, a zero divisor and `MIN / -1`. Each check runs
  before the operation, so no intermediate value overflows, including small
  unsigned types that promote to `int` (`65535 * 65535`).
- `saturating_add`, `saturating_subtract`, `saturating_multiply`, `saturate_cast`:
  the result clamped to the type's range.

The two operands of every binary function have one `checked_integral` type, found
by deduction: a call with mixed types, with `bool` or character operands, or with
explicit template arguments (`checked_add<std::size_t>(size, -1)`) does not
compile, so `-1` is never converted silently to a huge unsigned value; convert
with `narrow` first. A deleted overload takes those calls, so this also holds next
to the converting `size_t` overloads of `<lorica/checked_size.hpp>` (which
`<lorica/byte_view.hpp>` includes); those still serve two `size_t` operands, with
the same results.

## Bounded text {#SPEC-LR-TEXT}

`<lorica/bounded_text.hpp>`. A destination is a contiguous, sized range of
writable characters (`char`, `wchar_t`, `char8_t`, `char16_t`, `char32_t`) that
outlives the call: an lvalue array or container, or a view such as `std::span`.
A temporary or read-only destination does not compile, since the result would be
lost.

- `copy_string(destination, source)` replaces `strcpy`/`wcscpy`/`strncpy`.
- `append_string(destination, source)` replaces `strcat`/`wcscat`, appending to the
  C string already in the destination.
- `format_into(destination, format, args...)` replaces `sprintf`/`snprintf` for
  `char`: `std::format` syntax, with the format string checked at compile time, so
  no runtime value becomes a format string unless the caller opts in with C++26
  `std::runtime_format` (which stays type-safe: a bad string throws).

Sources: a character array (a buffer or a literal) is read up to its first
terminator, which must lie inside the array; an array without one, such as a
fixed field filled to its last byte, is rejected, not read past its end. A string,
view or other value convertible to a string view is taken whole and must not hold
a terminator, which would silently shorten the C string. A pointer is measured as
`strlen` measures it, so it must point to a terminated string. A source may be a
view into the destination; the copy is correct either way.

Each writes the whole text and a terminator inside the destination and returns its
length. Text that does not fit, a rejected source and, for `append_string`, a
destination holding no terminator leave an empty string and return empty: a
cut-off value is never presented as complete. An empty destination is left
untouched.

## Byte reading {#SPEC-LR-READER}

`<lorica/byte_reader.hpp>`. `byte_reader` is a cursor over a
`std::span<const std::byte>` for packets and file records, replacing pointer
arithmetic plus `memcpy`/`reinterpret_cast`.

- `take(n)` gives the next `n` bytes as a view; `skip(n)` passes over them.
- `read<T, std::endian::big|little>()`, `read_big_endian<T>()`,
  `read_little_endian<T>()` assemble an integer byte by byte, independent of the
  host's byte order and of alignment.
- `read_prefixed<Length, Order>()` reads a length and then that many bytes. A
  negative length, one that does not fit `size_t` and one past the end fail.

Every read checks what remains first; a failed read, including either part of a
prefixed field, consumes nothing. Like `byte_view`, the reader is non-owning: the
caller supplies a live span and keeps it unchanged for the reader's lifetime. It
checks offsets against the span's size, not whether the span describes valid
memory, and it is not thread-safe.

Verification: [SPEC-LR-VERIFY](../test/verification.md).
