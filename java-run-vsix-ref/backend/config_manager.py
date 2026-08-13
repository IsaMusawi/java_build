import copy
import json
import os
import shutil
import sys
from pathlib import Path


DEFAULT_PORTS = {
    "http": 8080,
    "https": 8443,
    "ajp": 8009,
    "shutdown": 8005,
    "debug": 8000,
}


class ConfigManager:
    DEFAULTS = {
        "workspace_path": "",
        "java_home": "",
        "maven_home": "",
        "tomcat_home": "",
        "vscode_path": "",
        "active_tabs": [],
        "deploy_map": {},
        # Kept as the global/default value for backward compatibility.
        "tomcat_startup_timeout": 450,
    }

    DEBUG_CONFIG_PREFIX = "SM Debug | "

    def __init__(self):
        self.workspace_path = ""
        self.config_file = ""
        self.data = copy.deepcopy(self.DEFAULTS)

    def get_config_file(self):
        return self.config_file

    def get_config_dir(self):
        return (
            os.path.join(os.path.dirname(self.workspace_path), ".sm-devops")
            if self.workspace_path else ""
        )

    def get_instance_runtime_dir(self):
        return (
            os.path.join(self.get_config_dir(), "tomcat-instances")
            if self.workspace_path else ""
        )

    def switch_workspace(self, workspace_path):
        workspace_path = os.path.abspath(os.path.normpath(workspace_path or ""))
        if not os.path.isfile(workspace_path):
            raise FileNotFoundError(f"Workspace tidak ditemukan: {workspace_path}")
        if not workspace_path.lower().endswith(".code-workspace"):
            raise ValueError("File yang dipilih harus berekstensi .code-workspace.")

        self.workspace_path = workspace_path
        self.config_file = os.path.join(self.get_config_dir(), "devops_settings.json")
        self.data = copy.deepcopy(self.DEFAULTS)
        self.data["workspace_path"] = workspace_path
        self.load()

    def load(self):
        if self.config_file and os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as fh:
                    loaded = json.load(fh)
                if isinstance(loaded, dict):
                    self.data.update(loaded)
            except Exception as exc:
                print(f"[WARN] Error loading config: {exc}", file=sys.stderr)

        self.data["workspace_path"] = self.workspace_path
        self.data.setdefault("active_tabs", [])
        self.data.setdefault("deploy_map", {})
        self._migrate_deploy_map()

        if not self.data.get("java_home"):
            self.data["java_home"] = self.detect_java8()

        self.save()

    def save(self):
        if not self.config_file:
            return False
        Path(self.config_file).parent.mkdir(parents=True, exist_ok=True)
        temp = self.config_file + ".tmp"
        with open(temp, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, indent=4, ensure_ascii=False)
            fh.write("\n")
        os.replace(temp, self.config_file)
        return True

    def get(self, key, default=""):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()

    def _load_workspace(self, workspace_path):
        with open(workspace_path, "r", encoding="utf-8-sig") as fh:
            lines = [
                line for line in fh.read().splitlines()
                if not line.strip().startswith("//")
            ]
        data = json.loads("\n".join(lines))
        if not isinstance(data, dict):
            raise ValueError("Format .code-workspace tidak valid.")
        return data

    def get_projects_from_workspace(self):
        if not self.workspace_path or not os.path.isfile(self.workspace_path):
            return []

        data = self._load_workspace(self.workspace_path)
        ws_dir = os.path.dirname(self.workspace_path)
        folders = data.get("folders", [])
        priority = ["common-lib", "bom", "api", "web"]
        folders = sorted(
            folders,
            key=lambda x: next(
                (i for i, k in enumerate(priority) if k in x.get("path", "")),
                99,
            ),
        )

        result = []
        for item in folders:
            raw = item.get("path", "")
            if not raw:
                continue
            path = os.path.normpath(
                raw if os.path.isabs(raw) else os.path.join(ws_dir, raw)
            )
            result.append({"name": os.path.basename(path), "path": path})
        return result

    def get_tomcat_home(self):
        return self.data.get("tomcat_home", "")

    def set_tomcat_home(self, path):
        self.data["tomcat_home"] = (
            os.path.abspath(os.path.normpath(path)) if path else ""
        )
        self.save()

    @staticmethod
    def _safe_instance_name(name):
        value = str(name or "").strip() or "Tomcat"
        return "".join(
            c if c.isalnum() or c in "._-" else "_" for c in value
        ) or "Tomcat"

    def _ensure_instance(self, name):
        name = str(name or "").strip()
        if not name:
            raise ValueError("Tomcat instance name tidak boleh kosong.")

        deploy_map = self.data.setdefault("deploy_map", {})
        server = deploy_map.get(name)

        # Migrate an older 'instances' structure if one exists.
        if not isinstance(server, dict):
            old_instances = self.data.get("instances") or {}
            old = old_instances.get(name) if isinstance(old_instances, dict) else None
            server = copy.deepcopy(old) if isinstance(old, dict) else {}

        server.setdefault("deployments", {})
        if not isinstance(server["deployments"], dict):
            server["deployments"] = {}

        server.setdefault("startup_timeout", self.get_tomcat_startup_timeout())
        server.setdefault("catalina_base", self.get_instance_base(name))

        old_home = server.pop("tomcat_home", "")
        if old_home and not self.data.get("tomcat_home"):
            self.data["tomcat_home"] = old_home

        deploy_map[name] = server
        return server

    def add_instance(self, name):
        name = self._safe_instance_name(name)
        if name in self.get_active_tabs():
            raise ValueError(f"Tomcat instance sudah ada: {name}")

        deploy_map = self.data.setdefault("deploy_map", {})
        if name in deploy_map:
            raise ValueError(f"Tomcat instance sudah ada: {name}")

        deploy_map[name] = {
            "deployments": {},
            "catalina_base": os.path.join(self.get_instance_runtime_dir(), name),
            "ports": {},
            "startup_timeout": self.get_tomcat_startup_timeout(),
        }
        self.data.setdefault("active_tabs", []).append(name)
        self.save()
        return name

    def remove_instance(self, name):
        name = str(name or "").strip()
        if name not in self.get_active_tabs() and name not in self.data.get("deploy_map", {}):
            raise ValueError(f"Tomcat instance tidak ditemukan: {name}")

        self.data.setdefault("deploy_map", {}).pop(name, None)
        self.data["active_tabs"] = [x for x in self.get_active_tabs() if x != name]
        self.save()
        return True

    def get_instance(self, name):
        deploy_map = self.data.get("deploy_map") or {}
        if isinstance(deploy_map, dict) and isinstance(deploy_map.get(name), dict):
            return deploy_map[name]

        instances = self.data.get("instances") or {}
        if isinstance(instances, dict) and isinstance(instances.get(name), dict):
            return instances[name]

        raise ValueError(f"Tomcat instance tidak ditemukan: {name}")

    def get_instance_base(self, name):
        server = self.data.get("deploy_map", {}).get(name, {})
        if isinstance(server, dict) and server.get("catalina_base"):
            return os.path.abspath(os.path.normpath(server["catalina_base"]))

        return (
            os.path.join(self.get_instance_runtime_dir(), self._safe_instance_name(name))
            if self.get_instance_runtime_dir() else ""
        )

    def set_instance_base(self, name, base):
        server = self._ensure_instance(name)
        server["catalina_base"] = os.path.abspath(os.path.normpath(base))
        self.save()

    def get_active_tabs(self):
        return list(self.data.get("active_tabs", []))

    def save_active_tabs(self, names):
        self.data["active_tabs"] = list(names)
        self.save()

    def rename_instance(self, old, new):
        old = str(old or "").strip()
        new = self._safe_instance_name(new)
        if old == new:
            return
        deploy_map = self.data.setdefault("deploy_map", {})
        if old in deploy_map:
            deploy_map[new] = deploy_map.pop(old)
        self.data["active_tabs"] = [new if x == old else x for x in self.get_active_tabs()]
        self.save()

    def get_instance_ports(self, name):
        instance = self.get_instance(name)
        ports = dict(DEFAULT_PORTS)
        configured = instance.get("ports") or {}
        for key in ports:
            value = configured.get(key)
            if isinstance(value, int):
                ports[key] = value
            elif isinstance(value, str) and value.isdigit():
                ports[key] = int(value)
        return ports

    def set_instance_ports(self, name, ports):
        instance = self._ensure_instance(name)
        normalized = {}
        for key in DEFAULT_PORTS:
            value = ports.get(key)
            if value in (None, ""):
                continue
            try:
                value = int(value)
            except (TypeError, ValueError):
                raise ValueError(f"Port {key} harus berupa angka.")
            if not 1 <= value <= 65535:
                raise ValueError(f"Port {key} harus berada pada 1-65535.")
            normalized[key] = value

        instance["ports"] = normalized
        self.save()
        return self.get_instance_ports(name)

    def get_tomcat_startup_timeout(self):
        try:
            value = int(self.data.get("tomcat_startup_timeout", 450))
        except (TypeError, ValueError):
            value = 450
        return max(1, value)

    def set_tomcat_startup_timeout(self, seconds):
        try:
            value = int(seconds)
        except (TypeError, ValueError):
            raise ValueError("Tomcat startup timeout harus berupa angka.")
        if value < 1:
            raise ValueError("Tomcat startup timeout minimal 1 detik.")
        self.data["tomcat_startup_timeout"] = value
        self.save()
        return value

    def get_instance_startup_timeout(self, name):
        instance = self._ensure_instance(name)
        try:
            value = int(instance.get("startup_timeout", self.get_tomcat_startup_timeout()))
        except (TypeError, ValueError):
            value = self.get_tomcat_startup_timeout()
        return max(1, value)

    def set_instance_startup_timeout(self, name, seconds):
        try:
            value = int(seconds)
        except (TypeError, ValueError):
            raise ValueError("Tomcat startup timeout harus berupa angka.")
        if value < 1:
            raise ValueError("Tomcat startup timeout minimal 1 detik.")
        self._ensure_instance(name)["startup_timeout"] = value
        self.save()
        return value

    @staticmethod
    def normalize_context(value):
        return str(value or "").strip().strip("/")

    def get_instance_deployments(self, name):
        return dict(self._ensure_instance(name).get("deployments", {}))

    def set_instance_deployment(self, name, context, project, target):
        context = self.normalize_context(context)
        if not context:
            raise ValueError("Context name cannot be empty.")
        self._ensure_instance(name)["deployments"][context] = {
            "project": project,
            "target": target,
        }
        self.save()

    def remove_instance_deployment(self, name, context):
        self._ensure_instance(name)["deployments"].pop(
            self.normalize_context(context), None
        )
        self.save()

    def _migrate_deploy_map(self):
        deploy_map = self.data.get("deploy_map", {})
        if not isinstance(deploy_map, dict):
            deploy_map = {}
            self.data["deploy_map"] = deploy_map

        shared_home = self.data.get("tomcat_home", "")
        old_instances = self.data.get("instances") or {}

        # Migrate old top-level instance storage into the current deploy_map.
        if isinstance(old_instances, dict):
            for name, value in old_instances.items():
                if name not in deploy_map and isinstance(value, dict):
                    deploy_map[name] = copy.deepcopy(value)
                if name not in self.data.setdefault("active_tabs", []):
                    self.data["active_tabs"].append(name)

        for name, value in deploy_map.items():
            if not isinstance(value, dict):
                deploy_map[name] = {}
                value = deploy_map[name]

            old_home = value.get("tomcat_home", "")
            if not shared_home and old_home:
                shared_home = old_home

            if not isinstance(value.get("deployments"), dict):
                project = value.get("project", "")
                target = value.get("target", "")
                deployments = {}
                context = self.normalize_context(target)
                if context:
                    deployments[context] = {"project": project, "target": target}
                value["deployments"] = deployments
                value.pop("project", None)
                value.pop("target", None)

            value.pop("tomcat_home", None)
            value.setdefault("catalina_base", self.get_instance_base(name))
            value.setdefault("startup_timeout", self.get_tomcat_startup_timeout())

        if shared_home:
            self.data["tomcat_home"] = shared_home

    def detect_java8(self):
        user_home = os.path.expanduser("~")
        specific = os.path.join(
            user_home,
            "Documents",
            "SM_TOOLS",
            "java",
            "jdk8u452-b09",
        )
        if os.path.isdir(specific):
            return specific
        env_java = os.environ.get("JAVA_HOME", "")
        return env_java if os.path.isdir(env_java) else ""

    def update_workspace_debug_config(self, instance_name, debug_port, workspace_file=""):
        """Create/update a Java attach configuration in the active .code-workspace.

        This extension is designed around a multi-root VS Code workspace. The
        workspace file is therefore the single source of truth for Java debug
        configurations. Existing configurations are preserved; only the
        configuration belonging to this Tomcat instance is inserted or updated.
        """
        port = int(debug_port)
        if not 1 <= port <= 65535:
            raise ValueError("Debug port harus berada antara 1-65535.")

        # switchWorkspace() already records the active .code-workspace path.
        # Prefer an explicitly supplied file, but never fall back to a project
        # folder or create .vscode/launch.json.
        workspace_path = os.path.abspath(
            os.path.normpath(workspace_file or self.workspace_path or "")
        )
        if not workspace_path or not os.path.isfile(workspace_path):
            raise ValueError(
                "File .code-workspace aktif tidak ditemukan untuk konfigurasi Debug."
            )
        if not workspace_path.lower().endswith(".code-workspace"):
            raise ValueError(
                "Konfigurasi Debug harus menggunakan file .code-workspace aktif."
            )

        data = self._load_workspace(workspace_path)
        if not isinstance(data, dict):
            raise ValueError("Format .code-workspace tidak valid.")

        launch = data.get("launch")
        if not isinstance(launch, dict):
            launch = {
                "version": "0.2.0",
                "configurations": [],
            }

        launch["version"] = "0.2.0"
        configurations = launch.get("configurations")
        if not isinstance(configurations, list):
            configurations = []

        config_name = f"{self.DEBUG_CONFIG_PREFIX}{instance_name}"
        debug_config = {
            "type": "java",
            "name": config_name,
            "request": "attach",
            "hostName": "localhost",
            "port": port,
        }

        # Update only our configuration. Preserve all user/other-extension
        # configurations such as "SM Debug | SERVERS".
        updated = False
        normalized = []
        for item in configurations:
            if isinstance(item, dict) and item.get("name") == config_name:
                if not updated:
                    normalized.append(debug_config)
                    updated = True
                # Drop duplicate entries of the same generated configuration.
                continue
            normalized.append(item)

        if not updated:
            normalized.append(debug_config)

        launch["configurations"] = normalized
        data["launch"] = launch

        self._backup_workspace(workspace_path)
        self._save_workspace(workspace_path, data)
        return {
            **debug_config,
            "workspaceFile": workspace_path,
        }

    @staticmethod
    def _load_jsonc(path):
        with open(path, "r", encoding="utf-8-sig") as fh:
            lines = [
                line for line in fh.read().splitlines()
                if not line.strip().startswith("//")
            ]
        return json.loads("\n".join(lines))

    def _save_workspace(self, path, data):
        temp = path + ".tmp"
        with open(temp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh, indent=4, ensure_ascii=False)
            fh.write("\n")
        os.replace(temp, path)

    def _backup_workspace(self, path):
        backup = path + ".bak"
        try:
            shutil.copy2(path, backup)
        except OSError:
            pass

    def summary(self):
        return {
            "workspace": self.workspace_path,
            "configFile": self.config_file,
            "javaHome": self.get("java_home", ""),
            "mavenHome": self.get("maven_home", ""),
            "tomcatHome": self.get_tomcat_home(),
            "instances": self.get_active_tabs(),
        }
