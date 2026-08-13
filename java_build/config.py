import copy
import json
import os
import shutil
from pathlib import Path


class ConfigManager:
    """
    Workspace-scoped configuration.

    One workspace owns one shared Tomcat distribution (CATALINA_HOME).
    Each logical Tomcat instance owns its own CATALINA_BASE.

    Default layout:

        <workspace>/
            project.code-workspace
            .sm-devops/
                devops_settings.json
                tomcat-instances/
                    Tomcat-1/
                    Tomcat-2/

    This allows multiple DevOps Dashboard processes/workspaces to run at
    the same time without sharing a global JSON configuration.
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
        self.workspace_path = ""
        self.config_file = None
        self.data = copy.deepcopy(self.DEFAULTS)

    # ------------------------------------------------------------------
    # Workspace-scoped configuration
    # ------------------------------------------------------------------

    def get_config_file(self):
        return self.config_file or ""

    def get_config_dir(self):
        if not self.workspace_path:
            return ""

        return os.path.join(
            os.path.dirname(self.workspace_path),
            ".sm-devops",
        )

    def get_instance_runtime_dir(self):
        config_dir = self.get_config_dir()
        if not config_dir:
            return ""

        return os.path.join(
            config_dir,
            "tomcat-instances",
        )

    def switch_workspace(self, workspace_path):
        if not workspace_path:
            raise ValueError("Workspace path tidak boleh kosong.")

        workspace_path = os.path.abspath(
            os.path.normpath(workspace_path)
        )

        if not os.path.isfile(workspace_path):
            raise FileNotFoundError(
                f"Workspace tidak ditemukan: {workspace_path}"
            )

        if not workspace_path.lower().endswith(".code-workspace"):
            raise ValueError(
                "File yang dipilih harus berekstensi .code-workspace."
            )

        self.workspace_path = workspace_path
        self.config_file = os.path.join(
            self.get_config_dir(),
            "devops_settings.json",
        )

        self.data = copy.deepcopy(self.DEFAULTS)
        self.data["workspace_path"] = workspace_path

        self.load()

    def load(self):
        if not self.config_file:
            return

        if os.path.exists(self.config_file):
            try:
                with open(
                    self.config_file,
                    "r",
                    encoding="utf-8",
                ) as f:
                    loaded = json.load(f)

                if isinstance(loaded, dict):
                    self.data.update(loaded)

            except Exception as exc:
                print(f"Error loading config: {exc}")

        self.data["workspace_path"] = self.workspace_path

        self._migrate_deploy_map()

        if not self.data.get("java_home"):
            self.data["java_home"] = self.detect_java8()

        self.save()

    def save(self):
        if not self.config_file:
            return False

        try:
            Path(self.config_file).parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            with open(
                self.config_file,
                "w",
                encoding="utf-8",
            ) as f:
                json.dump(
                    self.data,
                    f,
                    indent=4,
                    ensure_ascii=False,
                )

            return True

        except Exception as exc:
            print(f"Error saving config: {exc}")
            return False

    def get(self, key, default=""):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()

    # ------------------------------------------------------------------
    # Workspace
    # ------------------------------------------------------------------

    def get_projects_from_workspace(self):
        ws_path = self.workspace_path or self.get("workspace_path")
        if not ws_path or not os.path.exists(ws_path):
            return []

        try:
            data = self._load_workspace(ws_path)

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
    # Shared Tomcat / per-instance CATALINA_BASE
    # ------------------------------------------------------------------

    def get_tomcat_home(self):
        """Return the shared Tomcat distribution (CATALINA_HOME)."""
        return self.data.get("tomcat_home", "")

    def set_tomcat_home(self, tomcat_home):
        self.data["tomcat_home"] = (
            os.path.abspath(os.path.normpath(tomcat_home))
            if tomcat_home
            else ""
        )
        self.save()

    def get_instance_home(self, instance_name):
        """
        Backward-compatible alias.

        The Tomcat HOME is now shared by all instances in this workspace.
        """
        return self.get_tomcat_home()

    def set_instance_home(self, instance_name, tomcat_home):
        """
        Backward-compatible alias.

        Setting HOME changes the workspace-wide CATALINA_HOME instead of
        creating a different Tomcat distribution for every instance.
        """
        self.set_tomcat_home(tomcat_home)

    @staticmethod
    def _safe_instance_name(instance_name):
        value = str(instance_name or "").strip()

        if not value:
            return "Tomcat"

        # Keep the generated directory Windows-safe.
        safe = "".join(
            char if char.isalnum() or char in "._-" else "_"
            for char in value
        )

        return safe or "Tomcat"

    def get_instance_base(self, instance_name):
        """
        Return CATALINA_BASE for one logical Tomcat instance.

        The path is persisted so renaming an instance does not unexpectedly
        move its runtime data.
        """
        server = self.data.get("deploy_map", {}).get(instance_name, {})

        if isinstance(server, dict):
            base = server.get("catalina_base", "")
            if base:
                return os.path.abspath(os.path.normpath(base))

        runtime_dir = self.get_instance_runtime_dir()

        if not runtime_dir:
            return ""

        return os.path.join(
            runtime_dir,
            self._safe_instance_name(instance_name),
        )

    def set_instance_base(self, instance_name, catalina_base):
        server = self._ensure_instance(instance_name)

        server["catalina_base"] = (
            os.path.abspath(os.path.normpath(catalina_base))
            if catalina_base
            else ""
        )

        self.save()

    def ensure_instance_base(self, instance_name):
        """
        Return a stable per-instance CATALINA_BASE path.

        The directory itself is created by TomcatPanel because it must also
        bootstrap the Tomcat conf directory from CATALINA_HOME.
        """
        base = self.get_instance_base(instance_name)

        if not base:
            raise ValueError(
                "Workspace belum dipilih sehingga CATALINA_BASE tidak dapat dibuat."
            )

        self.set_instance_base(
            instance_name,
            base,
        )

        return base

    def rename_instance(self, old_name, new_name):
        if old_name == new_name:
            return

        deploy_map = self.data.setdefault("deploy_map", {})
        old_server = deploy_map.pop(old_name, None)

        if old_server is not None:
            deploy_map[new_name] = old_server

        active_tabs = self.data.get("active_tabs", [])
        self.data["active_tabs"] = [
            new_name if name == old_name else name
            for name in active_tabs
        ]

        self.save()

    # ------------------------------------------------------------------
    # Tabs / deployment API
    # ------------------------------------------------------------------

    def get_active_tabs(self):
        return self.data.get("active_tabs", [])

    def save_active_tabs(self, tab_list):
        self.data["active_tabs"] = list(tab_list)
        self.save()

    def _ensure_instance(self, instance_name):
        deploy_map = self.data.setdefault("deploy_map", {})

        server = deploy_map.get(instance_name)

        if not isinstance(server, dict):
            server = {}

        deployments = server.get("deployments")

        if not isinstance(deployments, dict):
            deployments = {}

        server["deployments"] = deployments

        # Migrate old per-instance tomcat_home to workspace-wide home if
        # needed. The first valid old value wins.
        old_home = server.get("tomcat_home", "")
        if old_home and not self.data.get("tomcat_home"):
            self.data["tomcat_home"] = old_home

        # The old field is no longer authoritative. Remove it after the
        # migration so future saves have one source of truth.
        server.pop("tomcat_home", None)

        deploy_map[instance_name] = server
        return server

    def get_instance_deployments(self, instance_name):
        server = self._ensure_instance(instance_name)
        return dict(server.get("deployments", {}))

    def get_instance_deploy(self, instance_name):
        deployments = self.get_instance_deployments(instance_name)

        if not deployments:
            return {"project": "", "target": ""}

        first = next(iter(deployments.values()))

        return {
            "project": first.get("project", ""),
            "target": first.get("target", ""),
        }

    def set_instance_deploy(
        self,
        instance_name,
        project_path,
        target_name,
    ):
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

    def remove_instance_deployment(
        self,
        instance_name,
        context_name,
    ):
        context = self.normalize_context(context_name)

        server = self.data.get(
            "deploy_map",
            {},
        ).get(
            instance_name,
            {},
        )

        if isinstance(server, dict):
            deployments = server.get(
                "deployments",
                {},
            )

            if isinstance(deployments, dict):
                deployments.pop(
                    context,
                    None,
                )

        self.save()

    def clear_instance_deployments(self, instance_name):
        server = self._ensure_instance(instance_name)
        server["deployments"] = {}
        self.save()

    @staticmethod
    def normalize_context(context_name):
        return str(
            context_name or ""
        ).strip().strip("/")

    # ------------------------------------------------------------------
    # Migration
    # ------------------------------------------------------------------

    def _migrate_deploy_map(self):
        """
        Migrate previous configurations.

        Old:
            "Tomcat-1": {
                "tomcat_home": "...",
                "deployments": {...}
            }

        New:
            "Tomcat-1": {
                "catalina_base": "...",
                "deployments": {...}
            }

        The first old tomcat_home becomes the workspace-wide shared
        CATALINA_HOME.
        """
        deploy_map = self.data.get(
            "deploy_map",
            {},
        )

        if not isinstance(deploy_map, dict):
            self.data["deploy_map"] = {}
            return

        shared_home = self.data.get(
            "tomcat_home",
            "",
        )

        for instance_name, value in list(
            deploy_map.items()
        ):
            if not isinstance(value, dict):
                continue

            old_home = value.get(
                "tomcat_home",
                "",
            )

            if not shared_home and old_home:
                shared_home = old_home

            if isinstance(
                value.get("deployments"),
                dict,
            ):
                # Already using the multi-deployment format.
                value.pop(
                    "tomcat_home",
                    None,
                )
                continue

            project = value.get(
                "project",
                "",
            )

            target = value.get(
                "target",
                "",
            )

            deployments = {}

            if project or target:
                context = self.normalize_context(
                    target
                )

                if context:
                    deployments[context] = {
                        "project": project,
                        "target": target,
                    }

            value["deployments"] = deployments
            value.pop(
                "project",
                None,
            )
            value.pop(
                "target",
                None,
            )
            value.pop(
                "tomcat_home",
                None,
            )

        if shared_home:
            self.data["tomcat_home"] = shared_home

        # Do not generate base directories during configuration migration.
        # TomcatPanel creates them lazily when the instance is opened.
        for instance_name, value in deploy_map.items():
            if not isinstance(value, dict):
                continue

            value.setdefault(
                "catalina_base",
                self.get_instance_base(instance_name),
            )

    # ------------------------------------------------------------------
    # Java / VS Code
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

        env_java = os.environ.get(
            "JAVA_HOME",
            "",
        )

        if env_java and os.path.exists(env_java):
            return env_java

        return ""

    def get_vscode_path(self):
        return self.get(
            "vscode_path",
            "",
        )

    def set_vscode_path(self, path):
        self.set(
            "vscode_path",
            path,
        )

    # ------------------------------------------------------------------
    # Workspace Debug Configuration
    # ------------------------------------------------------------------

    def update_workspace_debug_config(
        self,
        instance_name,
        debug_port,
    ):
        workspace_path = self.get(
            "workspace_path"
        )

        if not workspace_path:
            raise ValueError(
                "Workspace path belum dikonfigurasi."
            )

        if not os.path.isfile(
            workspace_path
        ):
            raise FileNotFoundError(
                f"Workspace tidak ditemukan: {workspace_path}"
            )

        try:
            debug_port = int(
                debug_port
            )
        except (
            TypeError,
            ValueError,
        ):
            raise ValueError(
                f"Debug port tidak valid: {debug_port}"
            )

        if not 1 <= debug_port <= 65535:
            raise ValueError(
                f"Debug port harus berada antara 1-65535: {debug_port}"
            )

        data = self._load_workspace(
            workspace_path
        )

        launch = data.get(
            "launch"
        )

        if not isinstance(
            launch,
            dict,
        ):
            launch = {}

        launch["version"] = "0.2.0"

        configurations = launch.get(
            "configurations"
        )

        if not isinstance(
            configurations,
            list,
        ):
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

        filtered = []

        for configuration in configurations:
            if not isinstance(
                configuration,
                dict,
            ):
                filtered.append(
                    configuration
                )
                continue

            if configuration.get(
                "name",
                "",
            ) == config_name:
                continue

            filtered.append(
                configuration
            )

        filtered.append(
            new_configuration
        )

        launch["configurations"] = filtered
        data["launch"] = launch

        self._backup_workspace(
            workspace_path
        )

        self._save_workspace(
            workspace_path,
            data,
        )

        return new_configuration

    def remove_workspace_debug_config(
        self,
        instance_name,
    ):
        workspace_path = self.get(
            "workspace_path"
        )

        if not workspace_path:
            return False

        if not os.path.isfile(
            workspace_path
        ):
            return False

        data = self._load_workspace(
            workspace_path
        )

        launch = data.get(
            "launch"
        )

        if not isinstance(
            launch,
            dict,
        ):
            return False

        configurations = launch.get(
            "configurations"
        )

        if not isinstance(
            configurations,
            list,
        ):
            return False

        config_name = (
            f"{self.DEBUG_CONFIG_PREFIX}{instance_name}"
        )

        filtered = []
        removed = False

        for configuration in configurations:
            if not isinstance(
                configuration,
                dict,
            ):
                filtered.append(
                    configuration
                )
                continue

            if configuration.get(
                "name"
            ) == config_name:
                removed = True
                continue

            filtered.append(
                configuration
            )

        if not removed:
            return False

        launch["configurations"] = filtered

        if not filtered:
            data.pop(
                "launch",
                None,
            )
        else:
            data["launch"] = launch

        self._backup_workspace(
            workspace_path
        )

        self._save_workspace(
            workspace_path,
            data,
        )

        return True

    def _load_workspace(self, workspace_path):
        """
        Load JSON from a .code-workspace file.

        VS Code permits // comments, so full-line comments are ignored.
        """
        with open(
            workspace_path,
            "r",
            encoding="utf-8-sig",
        ) as f:
            content = f.read()

        clean_lines = []

        for line in content.splitlines():
            if line.strip().startswith("//"):
                continue

            clean_lines.append(line)

        data = json.loads(
            "\n".join(clean_lines)
        )

        if not isinstance(
            data,
            dict,
        ):
            raise ValueError(
                "Format .code-workspace tidak valid."
            )

        return data

    def _save_workspace(
        self,
        workspace_path,
        data,
    ):
        temp_path = (
            f"{workspace_path}.tmp"
        )

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
            if os.path.exists(
                temp_path
            ):
                try:
                    os.remove(
                        temp_path
                    )
                except OSError:
                    pass

            raise

    def _backup_workspace(
        self,
        workspace_path,
    ):
        backup_path = (
            f"{workspace_path}.bak"
        )

        shutil.copy2(
            workspace_path,
            backup_path,
        )

    # ------------------------------------------------------------------
    # Maven
    # ------------------------------------------------------------------

    def get_maven_home(self):
        return self.get(
            "maven_home",
            "",
        )

    def set_maven_home(self, path):
        self.set(
            "maven_home",
            path,
        )
