"""Input selection and reading. @implements SPEC-LR-ANALYZE

select(paths, excludes, compile_commands) -> sorted file list. Directories are
walked recursively (symbolic links to directories are not followed) for C and C++
extensions; a file named explicitly is taken whatever its extension. Exclude
globs (fnmatch) are matched against the path as given, its absolute form and each
trailing part, so `*/third_party/*` and `generated_*.cpp` both work.
read(path) returns the text decoded as UTF-8 with replacement; files over
MAX_BYTES are refused. Nothing is ever executed. Both raise InputError.
"""
import fnmatch
import json
import os
from typing import Iterable, List, Optional

EXTENSIONS = frozenset((".c", ".cc", ".cpp", ".cxx", ".c++", ".h", ".hh", ".hpp", ".hxx",
                        ".h++", ".inl", ".ipp", ".tcc", ".tpp"))
MAX_BYTES = 8 * 1024 * 1024


class InputError(Exception):
    pass


def _excluded(path: str, excludes: Iterable[str]) -> bool:
    path = path.replace(os.sep, "/")
    parts = path.split("/")
    candidates = [path, os.path.abspath(path).replace(os.sep, "/")] + [
        "/".join(parts[k:]) for k in range(1, len(parts))]
    return any(fnmatch.fnmatchcase(c, g) for g in excludes for c in candidates)


def _compile_commands(path: str) -> List[str]:
    try:
        with open(path, encoding="utf-8") as stream:
            entries = json.load(stream)
        return [os.path.normpath(os.path.join(e.get("directory", ""), e["file"])) for e in entries]
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        raise InputError("%s: not a readable compilation database (%s)" % (path, error))


def select(paths: Iterable[str], excludes: Iterable[str] = (),
           compile_commands: Optional[str] = None) -> List[str]:
    excludes = list(excludes)
    found = set(_compile_commands(compile_commands)) if compile_commands else set()
    for path in paths:
        if os.path.isdir(path):
            for directory, subdirectories, files in os.walk(path):
                subdirectories[:] = [d for d in subdirectories
                                     if not _excluded(os.path.join(directory, d), excludes)]
                found.update(os.path.join(directory, f) for f in files
                             if os.path.splitext(f)[1].lower() in EXTENSIONS)
        elif os.path.isfile(path):
            found.add(path)
        else:
            raise InputError("%s: no such file or directory" % path)
    return sorted(os.path.normpath(f) for f in found if not _excluded(f, excludes))


def read(path: str) -> str:
    try:
        if os.path.getsize(path) > MAX_BYTES:
            raise InputError("%s: larger than %d bytes, not analysed" % (path, MAX_BYTES))
        with open(path, "rb") as stream:
            return stream.read().decode("utf-8", errors="replace")
    except OSError as error:
        raise InputError("%s: %s" % (path, error.strerror or error))
