"""Compare the actual native Linux consumer commands and check configure failures."""
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
        args.append("-DCMAKE_CXX_FLAGS_RELEASE=-O2 -Werror -D_FORTIFY_SOURCE=1"
                    " -D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_NONE")
    result = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if (result.returncode == 0) == strict:
        raise RuntimeError(result.stdout)
    return " ".join(result.stdout.split())


def options(tokens):
    prefixes = ("-D_FORTIFY_SOURCE", "-U_FORTIFY_SOURCE", "-D_GLIBCXX_ASSERTIONS",
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
    for (target, lang), args in commands.items():
        if target == "control":
            continue
        # Ignore caller-provided options when counting Lorica's contribution.
        flags = Counter(args) - Counter(commands["control", lang])
        assert all(n == 1 for n in flags.values()), (target, lang, flags)
        assert flags["-fstack-protector-strong"] == 1
        ext = target != "baseline"
        cpp = lang == ".cpp"
        mode = "EXTENSIVE" if ext else "FAST"
        assert flags[f"-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_{mode}"] == int(cpp)
        assert sum(v for k, v in flags.items() if k.startswith("-D_LIBCPP_HARDENING_MODE=")) == int(cpp)
        assert flags["-D_GLIBCXX_ASSERTIONS"] == int(cpp)
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
        elif supported:
            assert fortify == ["-D_FORTIFY_SOURCE=3"]
        elif cpp and config == "Release" and case == "older_libc":
            assert fortify == ["-D_FORTIFY_SOURCE=2"]
        if fortify:
            assert ["-U_FORTIFY_SOURCE", fortify[0]] in [args[i:i+2] for i in range(len(args))]
    assert ("baseline", ".cpp") in commands


for config in (["Release", "Debug", ""] if case == "normal" and not multi else ["Release"]):
    output = configure(config)
    skip = build / "skip.txt"
    if skip.exists():
        print(skip.read_text())
        sys.exit(77)
    for active in (configs if multi else [config]):
        inspect(active)
    subprocess.run([cmake, "--build", str(build), "--parallel", "2", "--config", config or "Debug"], check=True)
    if case != "normal":
        lines = (build / "supported.txt").read_text().splitlines()
        expected = {
            "missing_flag": "requires -fstack-clash-protection",
            "older_libc": "requires effective _FORTIFY_SOURCE=3",
            "unoptimized": "requires effective _FORTIFY_SOURCE=3",
            "unknown_cpu": "supports x86-64 and AArch64 only",
        }[case]
        assert lines[0] == "FALSE" and expected in lines[1], lines
        assert expected in configure(config, strict=True)
        if case == "missing_flag":
            assert output.count("CXX does not support -fstack-clash-protection") == 1
