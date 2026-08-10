import json
import os
import shutil
from pathlib import Path
from path import app_dir


CONFIG_FILE = str(app_dir() / "devops_settings.json")


class ConfigManager:
    """
    Central configuration for the DevOps dashboard.

    New deployment model:
        deploy_map = {
            "Tomcat-1": {
                "tomcat_home": "...",
                "deployments": {
                    "email-api": {
                        "project": "...",
                        "target": "email-api"
                    },
                    "vendor-api": {
                        "project": "...",
                        "target": "vendor-api"
                    }
                }
            }
        }

    A Tomcat instance therefore owns N deployments.
    """

    DEFAULTS = {
        "workspace_path": "",
        "java_home": "",
        "maven_home": "",
        "tomcat_home": "",
        "vscode_path": "",
        "active_tabs": [],
        "deploy_map": {},
    }

    DEBUG_CONFIG_PREFIX = "SM Debug | "

    def __init__(self):
        self.data = dict(self.DEFAULTS)
        self.load()

    def load(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    self.data.update(loaded)
            except Exception as exc:
                print(f"Error loading config: {exc}")

        self._migrate_deploy_map()

        if not self.data.get("java_home"):
            self.data["java_home"] = self.detect_java8()

        self.save()

    def save(self):
        try:
            Path(CONFIG_FILE).parent.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=4)
        except Exception as exc:
            print(f"Error saving config: {exc}")

    def get(self, key, default=""):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()

    # ------------------------------------------------------------------
    # Workspace
    # ------------------------------------------------------------------

    def get_projects_from_workspace(self):
        """Return [(project_name, absolute_path), ...]."""
        ws_path = self.get("workspace_path")
        if not ws_path or not os.path.exists(ws_path):
            return []

        try:
            with open(ws_path, "r", encoding="utf-8") as f:
                content = f.read()

            # VS Code workspaces may contain // comments.
            clean_lines = [
                line for line in content.splitlines()
                if not line.strip().startswith("//")
            ]
            data = json.loads("\n".join(clean_lines))

            folders = data.get("folders", [])
            ws_dir = os.path.dirname(ws_path)

            priority = ["common-lib", "bom", "api", "web"]
            sorted_folders = sorted(
                folders,
                key=lambda item: next(
                    (
                        i
                        for i, keyword in enumerate(priority)
                        if keyword in item.get("path", "")
                    ),
                    99,
                ),
            )

            result = []
            for item in sorted_folders:
                raw_path = item.get("path", "")
                if not raw_path:
                    continue

                full_path = (
                    raw_path
                    if os.path.isabs(raw_path)
                    else os.path.join(ws_dir, raw_path)
                )
                full_path = os.path.normpath(full_path)

                name = os.path.basename(full_path)
                result.append((name, full_path))

            return result

        except Exception as exc:
            print(f"Error parsing workspace: {exc}")
            return []

    # ------------------------------------------------------------------
    # Tabs / Tomcat instances
    # ------------------------------------------------------------------

    def get_active_tabs(self):
        return self.data.get("active_tabs", [])

    def save_active_tabs(self, tab_list):
        self.data["active_tabs"] = list(tab_list)
        self.save()

    def get_instance_home(self, instance_name):
        """
        Return Tomcat home for an instance.

        Existing configurations that only have global tomcat_home continue
        to work. The first instance can therefore inherit the old setting.
        """
        server = self.data.get("deploy_map", {}).get(instance_name, {})
        if isinstance(server, dict):
            home = server.get("tomcat_home", "")
            if home:
                return home

        return self.data.get("tomcat_home", "")

    def set_instance_home(self, instance_name, tomcat_home):
        server = self._ensure_instance(instance_name)
        server["tomcat_home"] = tomcat_home
        self.save()

    def rename_instance(self, old_name, new_name):
        if old_name == new_name:
            return

        deploy_map = self.data.setdefault("deploy_map", {})
        old_server = deploy_map.pop(old_name, None)

        if old_server is not None:
            deploy_map[new_name] = old_server

        active_tabs = self.data.get("active_tabs", [])
        self.data["active_tabs"] = [
            new_name if name == old_name else name for name in active_tabs
        ]

        self.save()

    # ------------------------------------------------------------------
    # Multi-deployment API
    # ------------------------------------------------------------------

    def _ensure_instance(self, instance_name):
        deploy_map = self.data.setdefault("deploy_map", {})

        server = deploy_map.get(instance_name)
        if not isinstance(server, dict):
            server = {}

        # New format.
        deployments = server.get("deployments")
        if not isinstance(deployments, dict):
            deployments = {}
        server["deployments"] = deployments

        deploy_map[instance_name] = server
        return server

    def get_instance_deployments(self, instance_name):
        server = self._ensure_instance(instance_name)
        return dict(server.get("deployments", {}))

    def get_instance_deploy(self, instance_name):
        """
        Backward-compatible helper.

        Old code expects one deployment. New code should use
        get_instance_deployments().
        """
        deployments = self.get_instance_deployments(instance_name)
        if not deployments:
            return {"project": "", "target": ""}

        first = next(iter(deployments.values()))
        return {
            "project": first.get("project", ""),
            "target": first.get("target", ""),
        }

    def set_instance_deploy(self, instance_name, project_path, target_name):
        """
        Backward-compatible single-deployment setter.

        New UI should use set_instance_deployment() so existing deployments
        are not overwritten.
        """
        context = str(target_name or "").strip().strip("/")
        self.set_instance_deployment(
            instance_name,
            context,
            project_path,
            target_name,
        )

    def set_instance_deployment(
        self,
        instance_name,
        context_name,
        project_path,
        target_name,
    ):
        context = self.normalize_context(context_name)
        if not context:
            raise ValueError("Context name cannot be empty.")

        server = self._ensure_instance(instance_name)
        server["deployments"][context] = {
            "project": project_path,
            "target": target_name,
        }
        self.save()

    def remove_instance_deployment(self, instance_name, context_name):
        context = self.normalize_context(context_name)
        server = self.data.get("deploy_map", {}).get(instance_name, {})

        if isinstance(server, dict):
            deployments = server.get("deployments", {})
            if isinstance(deployments, dict):
                deployments.pop(context, None)

        self.save()

    def clear_instance_deployments(self, instance_name):
        server = self._ensure_instance(instance_name)
        server["deployments"] = {}
        self.save()

    @staticmethod
    def normalize_context(context_name):
        return str(context_name or "").strip().strip("/")

    # ------------------------------------------------------------------
    # Migration
    # ------------------------------------------------------------------

    def _migrate_deploy_map(self):
        """
        Convert old:
            "Tomcat-1": {
                "project": "...",
                "target": "foo"
            }

        into:
            "Tomcat-1": {
                "tomcat_home": "...",
                "deployments": {
                    "foo": {
                        "project": "...",
                        "target": "foo"
                    }
                }
            }

        The migration is intentionally conservative and preserves the old
        project/target values.
        """
        deploy_map = self.data.get("deploy_map", {})
        if not isinstance(deploy_map, dict):
            self.data["deploy_map"] = {}
            return

        for instance_name, value in list(deploy_map.items()):
            if not isinstance(value, dict):
                continue

            # Already migrated.
            if isinstance(value.get("deployments"), dict):
                value.setdefault("tomcat_home", "")
                continue

            project = value.get("project", "")
            target = value.get("target", "")

            deployments = {}
            if project or target:
                context = self.normalize_context(target)
                if context:
                    deployments[context] = {
                        "project": project,
                        "target": target,
                    }

            deploy_map[instance_name] = {
                "tomcat_home": "",
                "deployments": deployments,
            }

    # ------------------------------------------------------------------
    # Java
    # ------------------------------------------------------------------

    def detect_java8(self):
        user_home = os.path.expanduser("~")
        specific = os.path.join(
            user_home,
            "Documents",
            "SM_TOOLS",
            "java",
            "jdk8u452-b09",
        )
        if os.path.exists(specific):
            return specific

        env_java = os.environ.get("JAVA_HOME", "")
        if env_java and os.path.exists(env_java):
            return env_java

        return ""

     # ------------------------------------------------------------------
    # VS Code
    # ------------------------------------------------------------------

    def get_vscode_path(self):
        return self.get("vscode_path", "")

    def set_vscode_path(self, path):
        self.set("vscode_path", path)

    # ------------------------------------------------------------------
    # Workspace Debug Configuration
    # ------------------------------------------------------------------

    def update_workspace_debug_config(
        self,
        instance_name,
        debug_port,
    ):
        """
        Add or update a VS Code Java attach configuration inside
        the .code-workspace file.

        Example configuration:

            {
                "type": "java",
                "name": "SM Debug | Tomcat-1",
                "request": "attach",
                "hostName": "localhost",
                "port": 8000
            }

        Only configurations created by this application are modified.
        Existing user configurations are preserved.
        """
        workspace_path = self.get("workspace_path")

        if not workspace_path:
            raise ValueError(
                "Workspace path belum dikonfigurasi."
            )

        if not os.path.isfile(workspace_path):
            raise FileNotFoundError(
                f"Workspace tidak ditemukan: {workspace_path}"
            )

        try:
            debug_port = int(debug_port)
        except (TypeError, ValueError):
            raise ValueError(
                f"Debug port tidak valid: {debug_port}"
            )

        if not 1 <= debug_port <= 65535:
            raise ValueError(
                f"Debug port harus berada antara 1-65535: "
                f"{debug_port}"
            )

        data = self._load_workspace(workspace_path)

        launch = data.get("launch")

        if not isinstance(launch, dict):
            launch = {}

        launch["version"] = "0.2.0"

        configurations = launch.get(
            "configurations"
        )

        if not isinstance(configurations, list):
            configurations = []

        config_name = (
            f"{self.DEBUG_CONFIG_PREFIX}{instance_name}"
        )

        new_configuration = {
            "type": "java",
            "name": config_name,
            "request": "attach",
            "hostName": "localhost",
            "port": debug_port,
        }

        # ----------------------------------------------------------
        # Remove previous configuration generated by Build Manager
        # for this Tomcat instance.
        # ----------------------------------------------------------
        filtered = []

        for configuration in configurations:
            if not isinstance(configuration, dict):
                filtered.append(configuration)
                continue

            name = configuration.get("name", "")

            if name == config_name:
                continue

            filtered.append(configuration)

        filtered.append(new_configuration)

        launch["configurations"] = filtered
        data["launch"] = launch

        self._backup_workspace(workspace_path)
        self._save_workspace(
            workspace_path,
            data,
        )

        return new_configuration

    def _load_workspace(self, workspace_path):
        """
        Load a VS Code .code-workspace file.

        Current workspace files are normally JSON, but VS Code workspace
        files may contain // comments. We therefore remove full-line
        comments before parsing.
        """
        with open(
            workspace_path,
            "r",
            encoding="utf-8-sig",
        ) as f:
            content = f.read()

        clean_lines = []

        for line in content.splitlines():
            stripped = line.strip()

            if stripped.startswith("//"):
                continue

            clean_lines.append(line)

        content = "\n".join(clean_lines)

        data = json.loads(content)

        if not isinstance(data, dict):
            raise ValueError(
                "Format .code-workspace tidak valid."
            )

        return data

    def _save_workspace(
        self,
        workspace_path,
        data,
    ):
        """
        Save VS Code workspace JSON.

        The workspace is intentionally written with standard JSON
        formatting so VS Code can parse it reliably.
        """
        temp_path = f"{workspace_path}.tmp"

        try:
            with open(
                temp_path,
                "w",
                encoding="utf-8",
                newline="\n",
            ) as f:
                json.dump(
                    data,
                    f,
                    indent=4,
                    ensure_ascii=False,
                )
                f.write("\n")

            os.replace(
                temp_path,
                workspace_path,
            )

        except Exception:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

            raise

    def _backup_workspace(self, workspace_path):
        """
        Create a backup before modifying the workspace.

        Existing .bak is overwritten intentionally so the backup always
        represents the workspace immediately before the latest change.
        """
        backup_path = f"{workspace_path}.bak"

        shutil.copy2(
            workspace_path,
            backup_path,
        )

    def remove_workspace_debug_config(
        self,
        instance_name,
    ):
        """
        Remove only the debug configuration generated by Build Manager
        for the specified Tomcat instance.
        """
        workspace_path = self.get("workspace_path")

        if not workspace_path:
            return False

        if not os.path.isfile(workspace_path):
            return False

        data = self._load_workspace(
            workspace_path
        )

        launch = data.get("launch")

        if not isinstance(launch, dict):
            return False

        configurations = launch.get(
            "configurations"
        )

        if not isinstance(configurations, list):
            return False

        config_name = (
            f"{self.DEBUG_CONFIG_PREFIX}{instance_name}"
        )

        filtered = []
        removed = False

        for configuration in configurations:
            if not isinstance(configuration, dict):
                filtered.append(configuration)
                continue

            if configuration.get("name") == config_name:
                removed = True
                continue

            filtered.append(configuration)

        if not removed:
            return False

        launch["configurations"] = filtered

        # If no configuration remains, remove launch entirely.
        if not filtered:
            data.pop("launch", None)
        else:
            data["launch"] = launch

        self._backup_workspace(workspace_path)

        self._save_workspace(
            workspace_path,
            data,
        )

        return True

    # ------------------------------------------------------------------
    # Maven
    # ------------------------------------------------------------------

    def get_maven_home(self):
        return self.get("maven_home", "")

    def set_maven_home(self, path):
        self.set("maven_home", path)
