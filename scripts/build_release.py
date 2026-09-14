"""Run PyInstaller with a clean in-process DLL search path on Windows."""
import os
import argparse
from pathlib import Path
import sys


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument('--distpath', default='dist')
    args = parser.parse_args()
    destination = (root / args.distpath).resolve()
    if destination == root or not destination.is_relative_to(root):
        parser.error('Release output must be a subdirectory of the project workspace')
    os.chdir(root)
    system = Path(os.environ.get("SystemRoot", "C:/Windows"))
    # Some managed Python launchers re-inject tool paths after shell startup.
    # Set this after Python starts, before importing PyInstaller's dependency scanner.
    os.environ["PATH"] = os.pathsep.join([str(Path(sys.executable).parent), str(system / "System32"), str(system)])
    os.environ["PYINSTALLER_CONFIG_DIR"] = str(root / "build" / "pyinstaller-cache")
    from PyInstaller.__main__ import run
    run(["--noconfirm", "--clean", "--windowed", "--name", "AI Video to Sprite", "--paths", str(root), "--distpath", str(destination),
         "--add-data", "app/i18n/zh_CN.json;app/i18n", "--add-data", "app/i18n/en_US.json;app/i18n", "app/main.py"])


if __name__ == "__main__":
    main()
