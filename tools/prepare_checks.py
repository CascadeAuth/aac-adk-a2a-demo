#!/usr/bin/env python3
"""Install committed package fixtures for tenant-free PR/fork checks.

Downloads public Python dependencies only. Does not create a demo run selection.
"""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import components

SELECTION = ROOT / "tests/fixtures/components.json"


def prepare():
    if sys.prefix == sys.base_prefix:
        raise ValueError("activate your test virtual environment first")
    record = components.load_selection(SELECTION)
    specs = [components.package_spec(name, record["packages"][name]) for name in components.PACKAGES]
    subprocess.run([sys.executable, "-m", "pip", "install", *specs,
                    "-r", str(ROOT / "tests/requirements.txt")], check=True)


if __name__ == "__main__":
    if sys.argv[1:] == ["--invoke-version"]:
        print(components.load_selection(SELECTION)["packages"]["aac-invoke-auth"]["version"])
    elif not sys.argv[1:]:
        prepare()
    else:
        raise SystemExit("Use prepare_checks.py [--invoke-version]")
