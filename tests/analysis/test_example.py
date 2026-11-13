"""examples/analysis/README.md: every console block matches the real output."""
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

from support import ROOT

EXAMPLE = ROOT / "examples" / "analysis"
TOOL = "../../tools/lorica_analyze.py"


def sessions(markdown):
    """[(command, expected output)] from ```console blocks with `$ ` prompts."""
    steps = []
    for block in re.findall(r"```console\n(.*?)```", markdown, re.S):
        for chunk in re.split(r"^\$ ", block, flags=re.M)[1:]:
            command, _, output = chunk.partition("\n")
            steps.append((command, output))
    return steps


class ReadmeTests(unittest.TestCase):
    def test_console_blocks(self):
        steps = sessions((EXAMPLE / "README.md").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(steps), 5)
        with tempfile.TemporaryDirectory() as work:
            for source in EXAMPLE.glob("*.cpp"):
                shutil.copy(source, work)
            status = None
            for command, expected in steps:
                with self.subTest(command=command):
                    if command == "echo $?":
                        self.assertEqual("%d\n" % status, expected)
                        continue
                    argv = shlex.split(command)
                    self.assertEqual(argv[:2], ["python3", TOOL])
                    run = subprocess.run([sys.executable, str(ROOT / "tools" / "lorica_analyze.py")] + argv[2:],
                                         cwd=work, capture_output=True, text=True)
                    status = run.returncode
                    self.assertEqual(run.stdout, expected)
            # The committed baselines are what the README's commands write.
            for baseline in ("analysis-baseline.json", "shared-state-baseline.json"):
                self.assertEqual(Path(work, baseline).read_text(), (EXAMPLE / baseline).read_text())


if __name__ == "__main__":
    unittest.main()
