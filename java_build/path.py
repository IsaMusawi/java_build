from pathlib import Path
import sys

def app_dir() -> Path:
    """
    Returns the folder where the app is running from.
    - In dev: folder of this file.
    - In frozen exe: folder of the exe.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent

def tools_dir() -> Path:
    return app_dir() / "tools"