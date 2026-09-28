"""Build the Moneykeeper desktop application as a Windows executable."""

from __future__ import annotations

import subprocess
import sys
import shutil
import argparse
from importlib.util import find_spec
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--installer",
        action="store_true",
        help="compile Moneykeeper.iss after building the executable",
    )
    arguments = parser.parse_args()

    pyinstaller = (
        [sys.executable, "-m", "PyInstaller"]
        if find_spec("PyInstaller")
        else [shutil.which("pyinstaller") or "pyinstaller"]
    )
    command = pyinstaller + [
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        "Moneykeeper",
        "--icon",
        str(ROOT / "moneykeeper.ico"),
        "--distpath",
        str(ROOT / "dist"),
        "--workpath",
        str(ROOT / "build"),
        "--specpath",
        str(ROOT / "build"),
        str(ROOT / "moneykeeper.pyw"),
    ]
    result = subprocess.call(command, cwd=ROOT)
    if result != 0 or not arguments.installer:
        return result

    iscc = shutil.which("ISCC.exe") or shutil.which("iscc")
    if not iscc:
        for candidate in (
            Path("C:/Program Files (x86)/Inno Setup 6/ISCC.exe"),
            Path("C:/Program Files/Inno Setup 6/ISCC.exe"),
        ):
            if candidate.exists():
                iscc = str(candidate)
                break
    if not iscc:
        print("Inno Setup compiler not found. Install Inno Setup 6 and retry.")
        return 1
    return subprocess.call([iscc, str(ROOT / "Moneykeeper.iss")], cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())