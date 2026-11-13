"""A full copy of the analysed tree, where the constexpr subcommand mutates. @implements SPEC-LR-ANALYZE

Nothing is ever written inside the analysed tree. Every regular file under the
root (dot-directories and CMake build trees, i.e. directories holding a
CMakeCache.txt, skipped) is copied into a fresh temporary directory, so a relative
`#include "x.hpp"` next to a mutated header resolves to the copy as well. Paths
under the root that the copy holds are mapped to it; everything else (system
headers, build trees) is read where it is. The compiler's -H output is then checked:
a unit that read an original of a copied file is a tool error, never a result. The
copy is removed when the overlay is closed, whatever happened.
"""
import os
import shutil
import tempfile
from typing import Set

from .constexpr_compiler import ToolError

MAX_FILES = 50000
MAX_BYTES = 512 * 1024 * 1024


def _inside(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


class Overlay:
    def __init__(self, root: str, max_files: int = MAX_FILES, max_bytes: int = MAX_BYTES) -> None:
        self.root = os.path.realpath(root)
        if not os.path.isdir(self.root):
            raise ToolError("%s: the root to copy is not a directory" % root)
        self.directory = tempfile.mkdtemp(prefix="lorica-constexpr-")
        self.tree = os.path.join(self.directory, "tree")
        self._tree_real = os.path.join(os.path.realpath(self.directory), "tree")
        self.copied: Set[str] = set()
        try:
            if _inside(os.path.realpath(self.directory), self.root):
                raise ToolError("the temporary directory %s is inside the analysed tree %s; set TMPDIR "
                                "elsewhere" % (self.directory, self.root))
            self._copy(max_files, max_bytes)
        except BaseException:
            self.close()
            raise

    def _copy(self, max_files: int, max_bytes: int) -> None:
        count = size = 0
        for directory, subdirectories, files in os.walk(self.root):
            subdirectories[:] = [d for d in subdirectories if not d.startswith(".")
                                 and not os.path.isfile(os.path.join(directory, d, "CMakeCache.txt"))]
            target = os.path.join(self.tree, os.path.relpath(directory, self.root))
            os.makedirs(target, exist_ok=True)
            for name in files:
                source = os.path.join(directory, name)
                if not os.path.isfile(source):
                    continue
                count, size = count + 1, size + os.path.getsize(source)
                if count > max_files or size > max_bytes:
                    raise ToolError("%s holds more than %d files or %d MiB to copy; name a smaller --root"
                                    % (self.root, max_files, max_bytes >> 20))
                shutil.copyfile(source, os.path.join(target, name))
                self.copied.add(os.path.normpath(source))

    def to_copy(self, path: str) -> str:
        """The copy of path when the copy holds it, else path unchanged."""
        real = os.path.realpath(path)
        if _inside(real, self.root):
            mapped = os.path.join(self.tree, os.path.relpath(real, self.root))
            if os.path.exists(mapped):
                return os.path.normpath(mapped)
        return path

    def to_original(self, path: str) -> str:
        for tree in (self.tree, self._tree_real):
            if _inside(path, tree):
                return os.path.normpath(os.path.join(self.root, os.path.relpath(path, tree)))
        return path

    def is_original(self, path: str) -> bool:
        """True when path is the original of a copied file (the copy was bypassed)."""
        return os.path.normpath(path) in self.copied or os.path.realpath(path) in self.copied

    def write(self, original: str, text: str) -> None:
        target = self.to_copy(original)
        if target == original:
            raise ToolError("%s: not inside the copied root %s" % (original, self.root))
        with open(target, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)

    def close(self) -> None:
        shutil.rmtree(self.directory, ignore_errors=True)

    def __enter__(self) -> "Overlay":
        return self

    def __exit__(self, *_) -> None:
        self.close()
