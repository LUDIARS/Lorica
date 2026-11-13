"""Compiler side of the constexpr subcommand: GCC and Clang only. @implements SPEC-LR-ANALYZE

A compiler is started without a shell, with standard input closed and a timeout,
only by this subcommand and only when asked (--compiler or --compile-commands).
MSVC (cl, clang-cl) is refused: no MSVC path exists or is validated.

Every compile is syntax-only under the strict flags, appended after the
database's own flags so that they win: -pedantic-errors (no C++20/23 constructs
accepted as extensions), -Werror=invalid-constexpr (GCC otherwise downgrades a
call to a non-constexpr function to a warning, or says nothing in C++23), -H (the
headers read, to prove that the copy was compiled), and for Clang
-Wno-error=#pragma-messages (the canary stays a warning under -Werror). Flags that
would defeat them are removed and recorded: -fpermissive, -w, -fimplicit-constexpr,
-Wno-error, and -Wno-[error=]invalid-constexpr, -pedantic, c++NN-extensions, gnu*.
-std=gnu++NN becomes -std=c++NN; output, dependency and -c flags are dropped.
"""
import json
import os
import re
import shlex
import subprocess
from typing import List, NamedTuple, Optional, Set, Tuple

STRICT = ("-fsyntax-only", "-pedantic-errors", "-Werror=invalid-constexpr", "-H",
          "-fdiagnostics-color=never")
_CLANG = ("-Wno-error=#pragma-messages",)
_DEFEATING = frozenset(("-fpermissive", "-w", "-fimplicit-constexpr", "-Wno-error"))
_DEFEATING_WARNING = re.compile(r"-Wno-(?:error=)?(?:invalid-constexpr|pedantic|c\+\+\w*-extensions|gnu[\w-]*)$")
_DROP_WITH_VALUE = frozenset(("-o", "-MF", "-MT", "-MQ"))
_DROP = frozenset(("-c", "-S", "-E", "-M", "-MM", "-MD", "-MMD", "-MP", "-fsyntax-only", "-H"))
_PATH_OPTIONS = ("-isystem", "-idirafter", "-iquote", "-include", "-imacros", "-I")
_MSVC = frozenset(("cl", "cl.exe", "clang-cl", "clang-cl.exe"))
_WRAPPERS = frozenset(("ccache", "sccache", "distcc"))
_STANDARDS = {"98": "98", "03": "03", "0x": "11", "11": "11", "1y": "14", "14": "14", "1z": "17",
              "17": "17", "2a": "20", "20": "20", "2b": "23", "23": "23", "2c": "26", "26": "26"}
RANK = {"98": 1998, "03": 2003, "11": 2011, "14": 2014, "17": 2017, "20": 2020, "23": 2023, "26": 2026}
_SOURCE_EXTENSIONS = frozenset((".cc", ".cpp", ".cxx", ".c++", ".cp", ".ixx", ".cppm"))


class ToolError(Exception):
    pass


class Toolchain(NamedTuple):
    command: str
    family: str             # "gcc" or "clang"
    version: str
    default_std: str        # "17" for -std=gnu++17

    @property
    def label(self) -> str:
        return "%s %s" % (os.path.basename(self.command), self.version)


class Unit(NamedTuple):
    compiler: str
    directory: str
    file: str               # absolute, normalised
    arguments: Tuple[str, ...]  # without the compiler
    std: Optional[str]      # its own -std, or None for the compiler default


class Diagnostic(NamedTuple):
    file: str
    line: int
    message: str
    related: Tuple[Tuple[str, int, str], ...]  # (file, line, message) of its notes and contexts


class Output(NamedTuple):
    errors: List[Diagnostic]
    probes: Set[int]
    headers: List[str]
    text: str


def execute(argv: List[str], cwd: Optional[str], timeout: float) -> Tuple[Optional[int], str]:
    """(exit status or None when it could not finish, standard output and error)."""
    environment = dict(os.environ, LC_ALL="C", LANG="C")    # plain quotes in diagnostics
    try:
        done = subprocess.run(list(argv), cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=timeout, shell=False, env=environment)
    except subprocess.TimeoutExpired:
        return None, "%s: timed out after %g s" % (argv[0], timeout)
    except OSError as error:
        return None, "%s: %s" % (argv[0], error.strerror or error)
    return done.returncode, (done.stdout + done.stderr).decode("utf-8", errors="replace")


def detect(command: str, timeout: float) -> Toolchain:
    if os.path.basename(command).lower() in _MSVC:
        raise ToolError("%s: MSVC is not supported; GCC and Clang only" % command)
    status, out = execute([command, "--version"], None, timeout)
    if status != 0:
        raise ToolError("%s: cannot run it (%s)" % (command, (out.strip().splitlines() or ["no output"])[0]))
    lower = out.lower()
    family = "clang" if "clang" in lower else "gcc" if "free software foundation" in lower else None
    if family is None:
        raise ToolError("%s: neither GCC nor Clang (--version: %s)" % (command, out.strip().splitlines()[0]))
    version = re.search(r"\d+\.\d+(?:\.\d+)?", out.splitlines()[0]) or re.search(r"\d+\.\d+(?:\.\d+)?", out)
    status, out = execute([command, "-x", "c++", "-E", "-dM", os.devnull], None, timeout)
    value = re.search(r"#define __cplusplus (\d+)L", out) if status == 0 else None
    if value is None:
        raise ToolError("%s: cannot read its default standard (__cplusplus)" % command)
    number = int(value.group(1))   # GCC 13 says 202100 for C++23
    default = next((s for s, least in (("23", 202003), ("20", 202002), ("17", 201703), ("14", 201402),
                                       ("11", 201103)) if number >= least), "98")
    return Toolchain(command, family, version.group(0) if version else "unknown", default)


def standard(arguments) -> Optional[str]:
    """The standard of the last -std= among arguments ("17"), or None."""
    found = None
    for argument in arguments:
        match = re.match(r"--?std=(?:c|gnu)\+\+(\w+)$", argument)
        if match:
            found = _STANDARDS.get(match.group(1), found)
    return found


def database_units(path: str) -> List[Unit]:
    """C++ translation units of a compilation database (C files are skipped)."""
    try:
        with open(path, encoding="utf-8") as stream:
            entries = json.load(stream)
        units = []
        for entry in entries:
            argv = list(entry["arguments"]) if "arguments" in entry else shlex.split(entry["command"])
            while argv and os.path.basename(argv[0]) in _WRAPPERS:
                argv = argv[1:]
            directory = entry.get("directory") or os.path.dirname(os.path.abspath(path))
            file = os.path.normpath(os.path.join(directory, entry["file"]))
            if argv and os.path.splitext(file)[1].lower() in _SOURCE_EXTENSIONS:
                units.append(Unit(argv[0], directory, file, tuple(argv[1:]), standard(argv[1:])))
        return units
    except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError) as error:
        raise ToolError("%s: not a readable compilation database (%s)" % (path, error))


def include_directories(unit: Unit) -> List[str]:
    out, args = [], unit.arguments
    for k, argument in enumerate(args):
        for option in ("-I", "-iquote", "-isystem", "-idirafter"):
            if argument == option and k + 1 < len(args):
                out.append(os.path.normpath(os.path.join(unit.directory, args[k + 1])))
            elif argument.startswith(option) and len(argument) > len(option) and option == "-I":
                out.append(os.path.normpath(os.path.join(unit.directory, argument[2:])))
    return out


def strict_command(toolchain: Toolchain, unit: Unit, std: str, to_copy, source: Optional[str] = None
                   ) -> Tuple[List[str], List[str]]:
    """(argv, removed flags): the unit's command with paths mapped and the strict flags."""
    def path(value: str) -> str:
        return to_copy(os.path.normpath(os.path.join(unit.directory, value)))

    argv, removed, args, k = [toolchain.command], [], unit.arguments, 0
    while k < len(args):
        argument = args[k]
        k += 1
        if argument in _DROP_WITH_VALUE:
            k += 1
        elif argument in _DROP or argument.startswith(("-std=", "--std=")):
            pass
        elif argument in _DEFEATING or _DEFEATING_WARNING.match(argument):
            removed.append(argument)
        elif argument in _PATH_OPTIONS and k < len(args):
            argv += [argument, path(args[k])]
            k += 1
        elif argument.startswith(_PATH_OPTIONS) and not argument.startswith("-include-pch"):
            option = next(o for o in _PATH_OPTIONS if argument.startswith(o))
            argv.append(option + path(argument[len(option):]))
        elif not argument.startswith("-") and os.path.normpath(os.path.join(unit.directory, argument)) == unit.file:
            argv.append(source or to_copy(unit.file))
        else:
            argv.append(argument)
    argv += ["-std=c++" + std] + list(STRICT) + (list(_CLANG) if toolchain.family == "clang" else [])
    return argv, removed


_PROBE = re.compile(r"lorica-probe:(\d+)")
_HEADER = re.compile(r"^\.+ (\S.*)$")
_LOCATION = re.compile(r"^(?P<file>[^\s:][^:]*):(?P<line>\d+):(?:\d+:)?\s*"
                       r"(?:(?P<severity>fatal error|error|warning|note): )?(?P<message>.*)$")


def parse(text: str, cwd: str) -> Output:
    """Errors (with their notes and instantiation contexts), canaries seen, headers read."""
    errors, probes, headers, context = [], set(), [], []
    for raw in text.splitlines():
        probe = _PROBE.search(raw)
        if probe:
            probes.add(int(probe.group(1)))
            continue
        header = _HEADER.match(raw)
        if header:
            headers.append(os.path.normpath(os.path.join(cwd, header.group(1))))
            continue
        found = _LOCATION.match(raw)
        if not found or raw.startswith("In file included from") or found.group("file").startswith("<"):
            continue                    # Clang's "<scratch space>" for the canary's _Pragma
        file = found.group("file")
        place = (file if file == "lorica-witness" else os.path.normpath(os.path.join(cwd, file)), int(found.group("line")),
                 found.group("message").strip())
        severity = found.group("severity")
        if severity in ("error", "fatal error"):
            errors.append(Diagnostic(place[0], place[1], place[2], tuple(context)))
            context = []
        elif severity == "note" and errors:
            last = errors[-1]
            errors[-1] = last._replace(related=last.related + (place,))
        elif severity is None:
            context.append(place)       # "required from here": belongs to the next error
    return Output(errors, probes, headers, text)
