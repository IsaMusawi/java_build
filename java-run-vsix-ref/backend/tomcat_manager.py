import html
import json
import os
import re
import shutil
import socket
import subprocess
import threading
import time


class TomcatManager:
    CONTEXT_RE = re.compile(r"^[A-Za-z0-9._-]+$")
    PORT_KEYS = ("http", "https", "ajp", "shutdown", "debug")

    def __init__(self, config, emit):
        self.config = config
        self.emit = emit
        self.processes = {}
        self.lock = threading.Lock()

    def configured_ports(self, name):
        return self.config.get_instance_ports(name)

    def _auto_ports(self, name):
        names = self.config.get_active_tabs()
        if name not in names:
            names.append(name)
        offset = names.index(name)
        return {
            "shutdown": 8005 + offset,
            "http": 8080 + offset,
            "https": 8443 + offset,
            "ajp": 8009 + offset,
            "debug": 8000 + offset,
        }

    def log(self, instance, message):
        self.emit({"type": "log", "instance": instance, "message": f"[{instance}] {message}"})

    def instance(self, name):
        self.config._ensure_instance(name)
        return {
            "name": name,
            "home": self.config.get_tomcat_home(),
            "base": self.config.get_instance_base(name),
            "deployments": self.config.get_instance_deployments(name),
            "running": self.is_running(name),
            "ports": self.read_ports(name),
            "startupTimeout": self.config.get_instance_startup_timeout(name),
        }

    def ensure_runtime(self, name):
        home = self.config.get_tomcat_home()
        base = self.config.get_instance_base(name)
        if not home or not os.path.isdir(home):
            raise ValueError("Tomcat Home tidak valid.")
        if not base:
            raise ValueError("CATALINA_BASE belum ditentukan.")
        for directory in ("logs", "temp", "webapps", "work", "conf", "bin"):
            os.makedirs(os.path.join(base, directory), exist_ok=True)
        server_xml = os.path.join(base, "conf", "server.xml")
        if not os.path.isfile(server_xml):
            source_conf = os.path.join(home, "conf")
            if not os.path.isdir(source_conf):
                raise ValueError("Tomcat conf directory tidak ditemukan.")
            for item in os.listdir(source_conf):
                src, dst = os.path.join(source_conf, item), os.path.join(base, "conf", item)
                if os.path.isdir(src): shutil.copytree(src, dst, dirs_exist_ok=True)
                else: shutil.copy2(src, dst)
            self.initialize_ports(name)
        self.config.set_instance_base(name, base)
        return home, base

    def initialize_ports(self, name):
        names = self.config.get_active_tabs()
        if name not in names:
            names.append(name)
        offset = names.index(name)
        if offset <= 0:
            return
        base = self.config.get_instance_base(name)
        path = os.path.join(base, "conf", "server.xml")
        with open(path, "r", encoding="utf-8") as fh: content = fh.read()
        ports = {"shutdown": 8005 + offset, "http": 8080 + offset, "ajp": 8009 + offset}
        content = re.sub(r'(<Server[^>]*port=")[0-9]+(")', rf'\g<1>{ports["shutdown"]}\g<2>', content, count=1)
        content = re.sub(r'(<Connector[^>]*protocol=["\']HTTP/[^"\']*["\'][^>]*port=")[0-9]+(")', rf'\g<1>{ports["http"]}\g<2>', content, count=1)
        content = re.sub(r'(<Connector[^>]*port=")[0-9]+("[^>]*protocol=["\']HTTP)', rf'\g<1>{ports["http"]}\g<2>', content, count=1)
        content = re.sub(r'(<Connector[^>]*protocol=["\']AJP/[^"\']*["\'][^>]*port=")[0-9]+(")', rf'\g<1>{ports["ajp"]}\g<2>', content, count=1)
        content = re.sub(r'(<Connector[^>]*port=")[0-9]+("[^>]*protocol=["\']AJP)', rf'\g<1>{ports["ajp"]}\g<2>', content, count=1)
        with open(path, "w", encoding="utf-8") as fh: fh.write(content)
        self.write_debug_port(name, 8000 + offset)
        self.log(name, f"[TOMCAT] Auto-assigned ports: HTTP={ports['http']}, AJP={ports['ajp']}, Shutdown={ports['shutdown']}, Debug={8000 + offset}")

    def read_ports(self, name):
        base = self.config.get_instance_base(name)
        result = {"shutdown": None, "http": None, "https": None, "ajp": None, "debug": None}
        server = os.path.join(base, "conf", "server.xml")
        if os.path.isfile(server):
            with open(server, "r", encoding="utf-8") as fh:
                content = fh.read()
            match = re.search(r'<Server[^>]*port=["\'](\d+)', content, flags=re.IGNORECASE)
            result["shutdown"] = int(match.group(1)) if match else None
            for connector in re.findall(r'<Connector\b[^>]*>', content, flags=re.IGNORECASE):
                port_match = re.search(r'\bport=["\'](\d+)', connector, flags=re.IGNORECASE)
                if not port_match:
                    continue
                port = int(port_match.group(1))
                protocol = re.search(r'\bprotocol=["\']([^"\']+)', connector, flags=re.IGNORECASE)
                protocol_value = protocol.group(1).lower() if protocol else ""
                ssl_enabled = re.search(r'\bsslenabled=["\']true["\']', connector, flags=re.IGNORECASE)
                if ssl_enabled:
                    result["https"] = port
                elif "ajp" in protocol_value:
                    result["ajp"] = port
                elif result["http"] is None:
                    result["http"] = port
        setenv = os.path.join(base, "bin", "setenv.bat")
        if os.path.isfile(setenv):
            with open(setenv, "r", encoding="utf-8") as fh:
                content = fh.read()
            match = re.search(r'JPDA_ADDRESS=([^\r\n]+)', content)
            if match and match.group(1).strip().isdigit():
                result["debug"] = int(match.group(1).strip())
        return result

    def save_ports(self, name, ports):
        self.ensure_runtime(name)
        base = self.config.get_instance_base(name)
        server = os.path.join(base, "conf", "server.xml")
        with open(server, "r", encoding="utf-8") as fh:
            content = fh.read()
        replacements = [
            (r'(<Server[^>]*port=")[0-9]+(")', ports.get("shutdown")),
            (r'(<Connector[^>]*protocol=["\']HTTP/[^"\']*["\'][^>]*port=")[0-9]+(")', ports.get("http")),
            (r'(<Connector[^>]*port=")[0-9]+("[^>]*protocol=["\']HTTP)', ports.get("http")),
            (r'(<Connector[^>]*protocol=["\']AJP/[^"\']*["\'][^>]*port=")[0-9]+(")', ports.get("ajp")),
            (r'(<Connector[^>]*port=")[0-9]+("[^>]*protocol=["\']AJP)', ports.get("ajp")),
            (r'(<Connector[^>]*port=")[0-9]+("[^>]*SSLEnabled=["\']true["\'])', ports.get("https")),
            (r'(<Connector[^>]*SSLEnabled=["\']true["\'][^>]*port=")[0-9]+(")', ports.get("https")),
        ]
        for pattern, value in replacements:
            if value not in (None, ""):
                content = re.sub(pattern, rf'\g<1>{int(value)}\g<2>', content, count=1)
        with open(server, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)
        if ports.get("debug") not in (None, ""):
            self.write_debug_port(name, int(ports["debug"]))
        self.config.set_instance_ports(name, ports)
        if ports.get("startupTimeout") not in (None, ""):
            self.config.set_instance_startup_timeout(name, ports["startupTimeout"])
        return {"ports": self.read_ports(name), "startupTimeout": self.config.get_instance_startup_timeout(name)}

    def write_debug_port(self, name, port):
        base = self.config.get_instance_base(name)
        path = os.path.join(base, "bin", "setenv.bat")
        content = ""
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as fh: content = fh.read()
        if "JPDA_ADDRESS" in content: content = re.sub(r"(JPDA_ADDRESS=)[^\r\n]+", rf"\g<1>{port}", content)
        else: content += f"\nset JPDA_ADDRESS={port}"
        if "JPDA_TRANSPORT" not in content: content += "\nset JPDA_TRANSPORT=dt_socket"
        else: content = re.sub(r"(JPDA_TRANSPORT=)[^\r\n]+", r"\g<1>dt_socket", content)
        with open(path, "w", encoding="utf-8") as fh: fh.write(content)

    def _processes(self):
        command = ["powershell.exe", "-NoProfile", "-Command", "Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name,CommandLine | ConvertTo-Json -Compress"]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=5)
            if result.returncode != 0 or not result.stdout.strip(): return []
            data = json.loads(result.stdout)
            if isinstance(data, dict): data = [data]
            return [{"pid": int(x.get("ProcessId")), "parent": int(x.get("ParentProcessId")), "name": x.get("Name", ""), "cmd": x.get("CommandLine", "") or ""} for x in data if x.get("ProcessId") is not None]
        except Exception:
            return []

    def find_pid(self, name):
        home = os.path.normcase(os.path.abspath(self.config.get_tomcat_home())).replace("\\", "/")
        base = os.path.normcase(os.path.abspath(self.config.get_instance_base(name))).replace("\\", "/")
        for p in self._processes():
            if p["name"].lower() not in ("java.exe", "javaw.exe"): continue
            cmd = p["cmd"].lower().replace('"', '').replace('\\', '/')
            if "org.apache.catalina.startup.bootstrap" in cmd and f"-dcatalina.home={home}" in cmd and f"-dcatalina.base={base}" in cmd:
                return p["pid"]
        return None

    def is_running(self, name):
        pid = self.find_pid(name)
        if pid:
            with self.lock: self.processes[name] = pid
            return True
        with self.lock: self.processes.pop(name, None)
        return False

    def _debug_port_available(self, host, port):
        """Return True when a TCP listener is already occupying the port."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        try:
            return sock.connect_ex((host, int(port))) == 0
        finally:
            sock.close()

    def _wait_for_debug_port(self, name, port, timeout=None):
        """Wait until the JPDA socket is accepting connections.

        Tomcat is launched asynchronously. Returning from start() before the
        socket exists creates a race with VS Code's Java attach operation.
        """
        timeout = (
            timeout
            if timeout is not None
            else self.config.get_instance_startup_timeout(name)
        )
        deadline = time.time() + timeout
        grace_deadline = time.time() + 3
        while time.time() < deadline:
            if self._debug_port_available("127.0.0.1", port):
                self.log(name, f"[JPDA] Debug listener ready on localhost:{port}")
                return

            # Give catalina.bat a short startup window before declaring the
            # process dead. On Windows the launcher and Java child process are
            # not necessarily visible to the process scanner immediately.
            if time.time() >= grace_deadline and not self.is_running(name):
                raise RuntimeError(
                    f"Tomcat {name} berhenti sebelum JPDA listener localhost:{port} aktif."
                )
            time.sleep(0.25)

        raise TimeoutError(
            f"JPDA listener localhost:{port} tidak aktif dalam {timeout} detik."
        )

    def start(self, name, debug=False, startup_timeout=None, workspace_file=''):
        home, base = self.ensure_runtime(name)

        if self.is_running(name):
            raise RuntimeError(
                f"Tomcat {name} sudah berjalan."
            )

        java = self.config.get(
            "java_home",
            "",
        )

        if not os.path.isdir(java):
            raise ValueError(
                "JAVA_HOME tidak valid."
            )

        # --------------------------------------------------------------
        # Validate application deployment BEFORE starting JVM
        # --------------------------------------------------------------

        deployments = self.validate_exploded_deployments(
            name
        )

        for deployment in deployments:
            self.log(
                name,
                (
                    "[DEPLOY] "
                    f"/{deployment['context']} "
                    f"-> {deployment['docbase']}"
                ),
            )

        # --------------------------------------------------------------
        # DEBUG / JPDA
        # --------------------------------------------------------------

        debug_port = None

        if debug:
            debug_port = (
                self.read_ports(name).get("debug")
                or self._auto_ports(name)["debug"]
            )

            if self._debug_port_available(
                "127.0.0.1",
                int(debug_port),
            ):
                raise RuntimeError(
                    f"JPDA port {debug_port} untuk "
                    f"{name} sedang digunakan proses lain."
                )

            self.write_debug_port(
                name,
                int(debug_port),
            )


        # --------------------------------------------------------------
        # ENVIRONMENT
        # --------------------------------------------------------------

        env = os.environ.copy()

        env.update(
            {
                "JAVA_HOME": java,
                "CATALINA_HOME": home,
                "CATALINA_BASE": base,
                "PROJECT_ENV": "LOCAL",
            }
        )

        env["PATH"] = (
            java
            + os.pathsep
            + os.path.join(java, "bin")
            + os.pathsep
            + env.get("PATH", "")
        )

        mode = (
            "JPDA RUN"
            if debug
            else "RUN"
        )

        self.log(
            name,
            (
                f"STARTING Tomcat "
                f"({mode}, "
                f"HTTP={self.read_ports(name).get('http') or '?'})"
            ),
        )

        threading.Thread(
            target=self._run,
            args=(
                name,
                home,
                env,
                debug,
            ),
            daemon=True,
        ).start()

        # --------------------------------------------------------------
        # DEBUG READY
        # --------------------------------------------------------------

        if debug:
            timeout = (
                self.config.get_instance_startup_timeout(name)
                if startup_timeout in (None, "")
                else int(startup_timeout)
            )
            self.config.set_instance_startup_timeout(name, timeout)
            self._wait_for_debug_port(
                name,
                int(debug_port),
                timeout=timeout,
            )

        result = {
            "instance": name,
            "debug": debug,
            "debugPort": (
                int(debug_port)
                if debug_port is not None
                else None
            ),
            "startupTimeout": self.config.get_instance_startup_timeout(name),
            "deployments": deployments,
        }

        if debug:
            result["debugConfiguration"] = self.config.update_workspace_debug_config(
                name,
                int(debug_port),
                workspace_file=workspace_file,
            )

        return result

    def _run(self, name, home, env, debug=False):
        try:
            command = (
                "catalina.bat jpda run"
                if debug
                else "catalina.bat run"
            )

            self.log(
                name,
                f"[PROCESS] Executing: {command}",
            )

            proc = subprocess.Popen(
                command,
                cwd=os.path.join(
                    home,
                    "bin",
                ),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                shell=True,
                creationflags=getattr(
                    subprocess,
                    "CREATE_NEW_PROCESS_GROUP",
                    0,
                ),
            )

            with self.lock:
                self.processes[name] = proc.pid

            self.log(
                name,
                f"[PROCESS] Launcher PID={proc.pid}",
            )

            assert proc.stdout is not None

            for line in proc.stdout:
                line = line.rstrip()

                if line:
                    self.log(
                        name,
                        line,
                    )

            rc = proc.wait()

            self.log(
                name,
                f"Tomcat stopped (exit={rc})",
            )

        except Exception as exc:
            self.log(
                name,
                f"Tomcat process error: {exc}",
            )

        finally:
            with self.lock:
                self.processes.pop(
                    name,
                    None,
                )

    def stop(self, name):
        pid = self.find_pid(name)
        if not pid: raise RuntimeError(f"Tomcat {name} tidak sedang berjalan.")
        result = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True)
        self.log(name, result.stdout.strip() or f"Stop command sent to PID={pid}")
        return {"pid": pid, "returncode": result.returncode}

    def list_exploded_artifacts(self, project):
        project = os.path.abspath(os.path.normpath(project))
        target_root = os.path.join(project, "target")
        if not os.path.isdir(target_root):
            return []
        result = []
        for name in sorted(os.listdir(target_root), key=str.lower):
            artifact = os.path.join(target_root, name)
            web_inf = os.path.join(artifact, "WEB-INF")
            if os.path.isdir(artifact) and os.path.isdir(web_inf):
                result.append({
                    "name": name,
                    "path": artifact,
                    "webInf": web_inf,
                    "wsProperties": os.path.isfile(
                        os.path.join(web_inf, "ws.properties")
                    ),
                })
        return result

    def _deployment_dir(self, base):
        directory = os.path.join(base, "conf", "Catalina", "localhost")
        os.makedirs(directory, exist_ok=True)
        return directory

    def _remove_descriptor(self, name, context):
        context = self.config.normalize_context(context)
        xml = os.path.join(self._deployment_dir(self.config.get_instance_base(name)), context + ".xml")
        if os.path.isfile(xml):
            os.remove(xml)
            return True
        return False

    def cleanup_untracked_descriptors(self, name):
        descriptor_dir = self._deployment_dir(self.config.get_instance_base(name))
        tracked = set(self.config.get_instance_deployments(name).keys())
        removed = []
        for filename in os.listdir(descriptor_dir):
            if not filename.lower().endswith(".xml"):
                continue
            context = self.config.normalize_context(os.path.splitext(filename)[0])
            if context not in tracked:
                os.remove(os.path.join(descriptor_dir, filename))
                removed.append(context)
        self.log(name, f"[DEPLOY] Removed {len(removed)} untracked descriptor(s).")
        return {"removed": removed}

    def deploy(self, name, project, target, context):
        """
        Deploy Maven exploded web application.

        Only:
            <project>/target/<target>/

        is accepted.

        WAR deployment is intentionally NOT supported.
        """

        context = self.config.normalize_context(context)

        if not self.CONTEXT_RE.fullmatch(context):
            raise ValueError(
                "Context hanya boleh berisi huruf, angka, '.', '_' atau '-'."
            )

        project = os.path.abspath(
            os.path.normpath(project)
        )

        if not os.path.isdir(project):
            raise FileNotFoundError(
                f"Project tidak ditemukan: {project}"
            )

        _, base = self.ensure_runtime(name)

        target = str(target or "").strip()

        if not target:
            raise ValueError(
                "Target Maven tidak boleh kosong."
            )
        if os.path.basename(target) != target:
            raise ValueError("Target artifact tidak valid.")

        # --------------------------------------------------------------
        # EXPLODED WEB APPLICATION
        #
        # Expected:
        #
        # project/
        # └── target/
        #     └── <target>/
        #         ├── WEB-INF/
        #         └── ...
        # --------------------------------------------------------------

        exploded_dir = os.path.abspath(
            os.path.join(
                project,
                "target",
                target,
            )
        )

        if not os.path.isdir(exploded_dir):
            war_path = os.path.join(
                project,
                "target",
                target + ".war",
            )

            if os.path.isfile(war_path):
                raise RuntimeError(
                    "WAR ditemukan, tetapi Java Run hanya mendukung "
                    "exploded web application.\n\n"
                    f"Exploded directory yang dibutuhkan:\n"
                    f"{exploded_dir}\n\n"
                    f"WAR ditemukan:\n"
                    f"{war_path}\n\n"
                    "Pastikan Maven menghasilkan exploded web application "
                    "di target/<artifact>."
                )

            raise FileNotFoundError(
                "Exploded web application tidak ditemukan:\n"
                f"{exploded_dir}\n\n"
                "Build project terlebih dahulu."
            )

        # --------------------------------------------------------------
        # BASIC WEB APP VALIDATION
        # --------------------------------------------------------------

        web_inf = os.path.join(
            exploded_dir,
            "WEB-INF",
        )

        if not os.path.isdir(web_inf):
            raise RuntimeError(
                "Target ditemukan tetapi bukan exploded web application.\n\n"
                f"Directory:\n{exploded_dir}\n\n"
                "WEB-INF tidak ditemukan."
            )

        # --------------------------------------------------------------
        # REPLACE OLD CONTEXT FOR SAME PROJECT
        # --------------------------------------------------------------

        deployments = self.config.get_instance_deployments(name)

        normalized_project = os.path.normcase(
            os.path.abspath(
                os.path.normpath(project)
            )
        )

        for old_context, deployment in list(
            deployments.items()
        ):
            old_project = os.path.normcase(
                os.path.abspath(
                    os.path.normpath(
                        deployment.get(
                            "project",
                            "",
                        )
                    )
                )
            )

            if (
                old_context != context
                and old_project == normalized_project
            ):
                self._remove_descriptor(
                    name,
                    old_context,
                )

                self.config.remove_instance_deployment(
                    name,
                    old_context,
                )

                self.log(
                    name,
                    (
                        "[DEPLOY] Replaced old context "
                        f"/{old_context} with /{context}"
                    ),
                )

        # --------------------------------------------------------------
        # CREATE TOMCAT CONTEXT DESCRIPTOR
        # --------------------------------------------------------------

        xml_dir = self._deployment_dir(base)

        xml = os.path.join(
            xml_dir,
            context + ".xml",
        )

        docbase = exploded_dir.replace(
            "\\",
            "/",
        )

        descriptor = (
            '<Context '
            f'docBase="{html.escape(docbase, quote=True)}" '
            'reloadable="true">'
            '</Context>'
        )

        with open(
            xml,
            "w",
            encoding="utf-8",
            newline="\n",
        ) as fh:
            fh.write(descriptor)

        # --------------------------------------------------------------
        # PERSIST DEPLOYMENT
        # --------------------------------------------------------------

        self.config.set_instance_deployment(
            name,
            context,
            project,
            target,
        )

        self.log(
            name,
            f"[DEPLOY] /{context} -> {exploded_dir}",
        )

        return {
            "context": context,
            "docbase": exploded_dir,
            "type": "exploded",
        }

    def undeploy(self, name, context):
        context = self.config.normalize_context(context)
        if not context or not self.CONTEXT_RE.fullmatch(context):
            raise ValueError("Context deployment tidak valid.")
        removed = self._remove_descriptor(name, context)
        self.config.remove_instance_deployment(name, context)
        self.log(name, f"[DEPLOY] Undeployed /{context} (descriptor={'removed' if removed else 'not-found'})")
        return {"context": context, "descriptorRemoved": removed}

    def validate_exploded_deployments(self, name):
        """
        Validate all tracked deployments before starting Tomcat.

        Every deployment must point to:
            <project>/target/<target>/

        WAR files are never accepted.
        """

        deployments = self.config.get_instance_deployments(
            name
        )

        if not deployments:
            self.log(
                name,
                "[DEPLOY] No tracked deployment."
            )
            return []

        validated = []

        for context, deployment in deployments.items():

            project = os.path.abspath(
                os.path.normpath(
                    deployment.get(
                        "project",
                        "",
                    )
                )
            )

            target = str(
                deployment.get(
                    "target",
                    "",
                )
            ).strip()

            if not project:
                raise RuntimeError(
                    f"Deployment /{context} memiliki project kosong."
                )

            if not target:
                raise RuntimeError(
                    f"Deployment /{context} memiliki target kosong."
                )

            exploded_dir = os.path.abspath(
                os.path.join(
                    project,
                    "target",
                    target,
                )
            )

            if not os.path.isdir(exploded_dir):
                raise RuntimeError(
                    "Exploded web application tidak ditemukan.\n\n"
                    f"Context : /{context}\n"
                    f"Expected: {exploded_dir}\n\n"
                    "Build project terlebih dahulu."
                )

            web_inf = os.path.join(
                exploded_dir,
                "WEB-INF",
            )

            if not os.path.isdir(web_inf):
                raise RuntimeError(
                    "Deployment bukan exploded web application yang valid.\n\n"
                    f"Context : /{context}\n"
                    f"Path    : {exploded_dir}\n"
                    "WEB-INF tidak ditemukan."
                )

            validated.append(
                {
                    "context": context,
                    "docbase": exploded_dir,
                }
            )

        return validated
