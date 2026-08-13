from pathlib import Path
import json
import py_compile

root = Path(__file__).parent

for rel in [
    "backend/build_manager.py",
    "backend/config_manager.py",
    "backend/protocol.py",
    "backend/server.py",
    "backend/tomcat_manager.py",
]:
    py_compile.compile(str(root / rel), doraise=True)

pkg = json.loads((root / "package.json").read_text(encoding="utf-8"))
commands = {c["command"] for c in pkg["contributes"]["commands"]}

required = {
    "javaRun.buildInstall",
    "javaRun.buildClean",
    "javaRun.buildCleanInstall",
    "javaRun.buildInstallAll",
    "javaRun.buildCleanAll",
    "javaRun.buildCleanInstallAll",
    "javaRun.deploy",
    "javaRun.undeploy",
}
missing = required - commands
assert not missing, f"Missing commands: {sorted(missing)}"

assert (root / "resources" / "java-run.svg").is_file()
print("Backend syntax: OK")
print("Required commands: OK")
print("Activity-bar icon resource: OK")
