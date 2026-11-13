"""Compare the actual native Linux consumer commands and link state, and check configure failures."""
from collections import Counter
import json
from pathlib import Path
import shlex
import subprocess
import sys

cmake, work, generator, compiler, cxx_flags, case = sys.argv[1:]
build = Path(work) / case
source = Path(__file__).resolve().parent
optimized = {"Release", "RelWithDebInfo", "MinSizeRel"}
multi = generator == "Ninja Multi-Config"
configs = ["Release", "Debug", "RelWithDebInfo", "MinSizeRel", "Custom"] if multi else ["Release"]


def configure(config, strict=False):
    args = [cmake, "-S", str(source), "-B", str(build), "-G", generator,
            "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON", f"-DCMAKE_CXX_COMPILER={compiler}",
            f"-DCMAKE_CXX_FLAGS={cxx_flags}", f"-DCASE={case}", f"-DCMAKE_BUILD_TYPE={config}",
            f"-DREQUIRE_EXTENDED={'ON' if strict else 'OFF'}"]
    if multi:
        args.append("-DCMAKE_CONFIGURATION_TYPES=" + ";".join(configs))
    if case == "normal":
        # Earlier definitions from a consuming project must compile under -Werror.
        args.append("-DCMAKE_CXX_FLAGS_RELEASE=-O2 -Werror -D_FORTIFY_SOURCE=1 -U_GLIBCXX_ASSERTIONS"
                    " -D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_NONE")
    result = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if (result.returncode == 0) == strict:
        raise RuntimeError("configuration unexpectedly " + ("succeeded" if strict else "failed") + "\n" + result.stdout)
    return " ".join(result.stdout.split())


def libc_fortify_3():
    """Whether the compiler's own C library gives level 3 at -O2, asked without Lorica's probes."""
    result = subprocess.run([compiler, *shlex.split(cxx_flags), "-O2", "-U_FORTIFY_SOURCE", "-D_FORTIFY_SOURCE=3",
                             "-x", "c++", "-E", "-dM", "-"], input="#include <string.h>\n",
                            text=True, capture_output=True, check=True)
    return "#define __USE_FORTIFY_LEVEL 3" in result.stdout.splitlines()


def options(tokens):
    prefixes = ("-D_FORTIFY_SOURCE", "-U_FORTIFY_SOURCE", "-D_GLIBCXX_ASSERTIONS", "-U_GLIBCXX_ASSERTIONS",
                "-D_LIBCPP_HARDENING_MODE", "-U_LIBCPP_HARDENING_MODE",
                "-fstack-", "-fcf-protection", "-mbranch-protection", "-ftrivial-auto-var-init")
    return [word for word in tokens if word.startswith(prefixes)]


def inspect(config):
    commands = {}
    entries = json.loads((build / "compile_commands.json").read_text())
    for entry in entries:
        args = shlex.split(entry["command"])
        if multi and f'-DCMAKE_INTDIR="{config}"' not in args:
            continue
        parts = Path(args[args.index("-o") + 1]).parts
        target = parts[parts.index("CMakeFiles") + 1][:-len(".dir")]
        commands[target, Path(entry["file"]).suffix] = options(args)
    supported = (build / "supported.txt").read_text().splitlines()[0] == "TRUE"
    assert (("direct", ".cpp") in commands) == supported
    # Lorica's FORTIFY level, judged against the C library itself, not against the
    # probes that decide it (a broken probe must not just disable the checks).
    fortify_3 = case == "normal" and config == "Release" and libc_fortify_3()
    for (target, lang), args in commands.items():
        if target == "control":
            continue
        # Ignore caller-provided options when counting Lorica's contribution.
        flags = Counter(args) - Counter(commands["control", lang])
        assert all(n == 1 for n in flags.values()), (target, lang, flags)
        assert flags["-fstack-protector-strong"] == 1
        ext = target in ("direct", "upgrade")
        cpp = lang == ".cpp"
        mode = "EXTENSIVE" if ext else "FAST"
        assert flags[f"-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_{mode}"] == int(cpp)
        assert sum(v for k, v in flags.items() if k.startswith("-D_LIBCPP_HARDENING_MODE=")) == int(cpp)
        assert flags["-D_GLIBCXX_ASSERTIONS"] == flags["-U_GLIBCXX_ASSERTIONS"] == int(cpp)
        if cpp:
            # After the toolchain's flags, so an earlier -U cannot undo it.
            assert ["-U_GLIBCXX_ASSERTIONS", "-D_GLIBCXX_ASSERTIONS"] in [args[i:i+2] for i in range(len(args))]
        assert flags["-ftrivial-auto-var-init=zero"] == int(ext)
        if ext:
            assert flags["-fstack-clash-protection"] == 1
            assert flags["-fcf-protection=full"] + flags["-mbranch-protection=standard"] == 1
            assert flags == Counter(commands["direct", lang]) - Counter(commands["control", lang])
        if cpp and case == "missing_flag":
            assert "-fstack-clash-protection" not in flags
        fortify = [k for k in flags if k.startswith("-D_FORTIFY_SOURCE=")]
        assert len(fortify) == flags["-U_FORTIFY_SOURCE"] <= 1
        if config not in optimized or (cpp and config == "Release" and case == "unoptimized"):
            assert not fortify
        elif supported or (cpp and fortify_3):
            assert fortify == ["-D_FORTIFY_SOURCE=3"], (target, lang, fortify)
        elif cpp and config == "Release" and case == "older_libc":
            assert fortify == ["-D_FORTIFY_SOURCE=2"]
        if fortify:
            assert ["-U_FORTIFY_SOURCE", fortify[0]] in [args[i:i+2] for i in range(len(args))]
    assert ("baseline", ".cpp") in commands
    # PIC everywhere; full RELRO and NX stack for linked binaries; PIE for executables.
    relro = "-Wl,-z,relro,-z,now,-z,noexecstack"
    for line in (build / f"link-{config}.txt").read_text().splitlines():
        target, link, pic = line.split("|")
        link = link.split(";") if link else []
        if target == "control":
            assert not link, link
            continue
        assert pic == "TRUE", (target, pic)
        expected = {"static": [], "shared": [relro]}.get(target, [relro, "-pie"])
        assert sorted(link) == sorted(expected), (target, link)


for config in (["Release", "Debug", "", "RelWithDebInfo", "MinSizeRel"] if case == "normal" and not multi else ["Release"]):
    output = configure(config)
    skip = build / "skip.txt"
    if skip.exists():
        print(skip.read_text())
        sys.exit(77)
    for active in (configs if multi else [config]):
        inspect(active)
    subprocess.run([cmake, "--build", str(build), "--parallel", "2", "--config", config or "Debug"], check=True)
    if case != "normal":
        expected = {
            "missing_flag": "requires -fstack-clash-protection",
            "older_libc": "requires effective _FORTIFY_SOURCE=3",
            "unoptimized": "requires effective _FORTIFY_SOURCE=3",
            "unknown_cpu": "supports x86-64 and AArch64 only",
            "old_compiler": "needs GCC 12 or Clang 18 or newer",
            "abi32": "requires a 64-bit Linux target ABI",
            "no_stdlib": "requires libstdc++ assertions or libc++ EXTENSIVE hardening",
            "no_autoinit": "requires -ftrivial-auto-var-init=zero for CXX",
            "harness_control": "nothing is injected, so this must not be reached",
        }[case]
        assert expected in configure(config, strict=True)
        lines = (build / "supported.txt").read_text().splitlines()
        assert lines[0] == "FALSE" and expected in lines[1], lines
        if case == "missing_flag":
            assert output.count("CXX does not support -fstack-clash-protection") == 1
