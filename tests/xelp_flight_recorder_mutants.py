#!/usr/bin/env python3
"""Prove that real recorder tests reject two plausible semantic regressions."""
from pathlib import Path
import resource
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "WhateverXe/kern_xelp_flight_recorder.hpp"
TEST = ROOT / "tests/xelp_flight_recorder.cpp"


def main():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    source = HEADER.read_text()
    test = TEST.read_text().replace(
        '#include "../WhateverXe/kern_xelp_flight_recorder.hpp"',
        '#include "kern_xelp_flight_recorder.hpp"')
    mutations = (
        ("(next_ + Capacity - count_ + index) % Capacity", "index",
         "event.sequence == 3"),
        ("!enabled_ || frozen_ || !valid(kind)", "!enabled_ || !valid(kind)",
         "!recorder.record(Kind::Recovery, 3)"),
    )
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / TEST.name).write_text(test)
        for original, changed, expected in mutations:
            if source.count(original) != 1:
                raise RuntimeError("mutation site changed; review contract")
            (root / HEADER.name).write_text(source.replace(original, changed))
            executable = root / "mutant"
            subprocess.run(["clang++", "-std=c++17", "-O1", str(root / TEST.name),
                            "-o", str(executable)], check=True, timeout=60)
            result = subprocess.run([str(executable)], cwd=root, capture_output=True,
                                    text=True, timeout=10)
            if result.returncode == 0 or expected not in result.stderr:
                raise RuntimeError("semantic regression did not fail its expected assertion")
    print("PASS: chronological-read and freeze semantic regressions rejected")


if __name__ == "__main__":
    main()
