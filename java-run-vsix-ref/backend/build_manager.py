import os
import shutil
import subprocess
import time


class BuildManager:
    """Run Maven builds for one or all workspace projects sequentially."""

    # Existing project-level actions. Keep these names stable.
    ACTIONS = {
        "install": ["install"],
        "clean": ["clean"],
        "clean_install": ["clean", "install"],
    }

    # Additive all-project actions. They never replace project-level actions.
    ALL_ACTIONS = {
        "install_all": "install",
        "clean_all": "clean",
        "clean_install_all": "clean_install",
    }

    BASE_OPTIONS = [
        "-B",
        "-Dmaven.javadoc.skip=true",
        "-DskipTests",
        "-DPROJECT_ENV=LOCAL",
    ]

    INCREMENTAL_COMPILER_OPTION = (
        "-Dmaven.compiler.useIncrementalCompilation=false"
    )

    # Java web projects may use the normal Maven layout or a legacy webapp
    # directory. The important invariant is that ws.properties lives under
    # WEB-INF, never under a project/artifact-specific hardcoded path.
    WEBAPP_SOURCE_ROOTS = (
        ("src", "main", "webapp"),
        ("webapp",),
    )

    def __init__(self, config, emit):
        self.config = config
        self.emit = emit
        self.running = False

    def log(self, message):
        self.emit({"type": "log", "message": message})

    def maven_command(self):
        home = self.config.get("maven_home", "")
        candidates = []

        if home:
            candidates.extend([
                os.path.join(home, "bin", "mvn.cmd"),
                os.path.join(home, "bin", "mvn.bat"),
                os.path.join(home, "bin", "mvn"),
            ])

        candidates.extend(["mvn.cmd", "mvn.bat", "mvn"])

        for candidate in candidates:
            if os.path.isabs(candidate):
                if os.path.isfile(candidate):
                    return os.path.abspath(candidate)
            else:
                found = shutil.which(candidate)
                if found:
                    return os.path.abspath(found)

        return None

    @staticmethod
    def _project_info(project):
        if isinstance(project, dict):
            path = project.get("path", "")
            name = project.get("name") or os.path.basename(os.path.normpath(path))
        else:
            path = str(project)
            name = os.path.basename(os.path.normpath(path))

        return os.path.abspath(os.path.normpath(path)), name

    def _normalize_action(self, action):
        if action in self.ACTIONS:
            return action, False
        if action in self.ALL_ACTIONS:
            return self.ALL_ACTIONS[action], True
        raise ValueError(f"Unknown Maven action: {action}")

    def _build_options(self, action):
        options = list(self.BASE_OPTIONS)
        if action == "install":
            options.append(self.INCREMENTAL_COMPILER_OPTION)
        return options

    @staticmethod
    def _format_duration(seconds):
        if seconds < 60:
            return f"{seconds:.1f}s"
        minutes = int(seconds // 60)
        return f"{minutes}m {seconds - (minutes * 60):.1f}s"

    def _environment(self, java):
        env = os.environ.copy()
        env["JAVA_HOME"] = java
        java_bin = os.path.join(java, "bin")
        env["PATH"] = java + os.pathsep + java_bin + os.pathsep + env.get("PATH", "")
        return env

    def _command(self, mvn, goals, options):
        command = [mvn, *goals, *options]
        if mvn.lower().endswith((".cmd", ".bat")):
            return [os.environ.get("ComSpec", "cmd.exe"), "/c", *command]
        return command

    def _find_ws_properties(self, project_path):
        """
        Find the project-local ws.properties without knowing the project name.

        Supported layouts:
          <project>/src/main/webapp/WEB-INF/ws.properties
          <project>/webapp/WEB-INF/ws.properties

        WEB-INF is the invariant; dfms-web/gass-web/etc. are not.
        """
        for root_parts in self.WEBAPP_SOURCE_ROOTS:
            source = os.path.join(
                project_path,
                *root_parts,
                "WEB-INF",
                "ws.properties",
            )
            if os.path.isfile(source):
                return os.path.abspath(source)
        return None

    @staticmethod
    def _find_exploded_web_artifacts(project_path):
        """
        Return Maven-produced exploded web artifacts.

        An artifact is considered exploded-web only when:
            <project>/target/<artifact>/WEB-INF/

        WAR files are deliberately ignored because deployment is directory based.
        """
        target_root = os.path.join(project_path, "target")
        if not os.path.isdir(target_root):
            return []

        artifacts = []
        for name in sorted(os.listdir(target_root), key=str.lower):
            artifact = os.path.join(target_root, name)
            web_inf = os.path.join(artifact, "WEB-INF")
            if os.path.isdir(artifact) and os.path.isdir(web_inf):
                artifacts.append((name, artifact, web_inf))
        return artifacts

    def _copy_ws_properties(self, project_path):
        """
        Synchronize project-local ws.properties into every exploded web artifact.

        This is intentionally generic:
          source = <project>/.../WEB-INF/ws.properties
          target = <project>/target/<artifact>/WEB-INF/ws.properties

        Nothing is copied for projects that do not provide ws.properties.
        """
        source = self._find_ws_properties(project_path)
        if not source:
            self.log(
                "[WEBAPP] ws.properties not found under project WEB-INF; "
                "copy skipped."
            )
            return 0

        artifacts = self._find_exploded_web_artifacts(project_path)
        if not artifacts:
            self.log(
                "[WEBAPP] No exploded web artifact found under target; "
                "ws.properties copy skipped."
            )
            return 0

        copied = 0
        for artifact_name, _, web_inf in artifacts:
            destination = os.path.join(web_inf, "ws.properties")

            # Avoid an unnecessary copy when source and destination happen to
            # resolve to the same file.
            if os.path.abspath(source) != os.path.abspath(destination):
                shutil.copy2(source, destination)

            if not os.path.isfile(destination):
                raise RuntimeError(
                    "ws.properties copy failed:\n"
                    f"Source: {source}\n"
                    f"Target: {destination}"
                )

            copied += 1
            self.log(
                f"[WEBAPP] ws.properties synchronized: "
                f"{artifact_name}/WEB-INF/ws.properties"
            )

        return copied

    def _run_project(self, action, project, index, total, mvn, env):
        path, name = self._project_info(project)

        if not os.path.isdir(path):
            raise FileNotFoundError(f"Project folder not found: {path}")

        if not os.path.isfile(os.path.join(path, "pom.xml")):
            self.log(f"[SKIP] {name} (No pom.xml)")
            return {
                "name": name,
                "path": path,
                "status": "skipped",
                "elapsed": 0.0,
                "wsPropertiesCopied": 0,
            }

        goals = self.ACTIONS[action]
        options = self._build_options(action)
        command = self._command(mvn, goals, options)

        self.log("")
        self.log(f"[{index}/{total}] >>> Maven {action}: {name}")
        self.log(f"[DIR] {path}")
        self.log(f"[GOALS] {' '.join(goals)}")
        self.log(f"[OPTIONS] {' '.join(options)}")
        self.log(f"[CMD] {' '.join(command)}")

        started = time.perf_counter()
        proc = subprocess.Popen(
            command,
            cwd=path,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        self.log(f"[PROCESS] Maven PID={proc.pid}")
        assert proc.stdout is not None

        for line in proc.stdout:
            line = line.rstrip()
            if line:
                self.log(line)

        rc = proc.wait()
        elapsed = time.perf_counter() - started
        duration = self._format_duration(elapsed)

        if rc != 0:
            self.log(f"❌ [{index}/{total}] {name} FAILED (exit={rc}, {duration})")
            raise RuntimeError(
                f"Maven {action} failed for {name} "
                f"(exit={rc}, elapsed={duration})"
            )

        # Only install phases can produce the final exploded web artifact.
        # Clean alone must never create/copy deployment resources.
        copied_ws = (
            self._copy_ws_properties(path)
            if action in {"install", "clean_install"}
            else 0
        )

        self.log(f"✅ [{index}/{total}] {name} SUCCESS ({duration})")
        return {
            "name": name,
            "path": path,
            "status": "success",
            "elapsed": elapsed,
            "wsPropertiesCopied": copied_ws,
        }

    def build(self, action, projects=None):
        if self.running:
            raise RuntimeError("Maven build sedang berjalan.")

        normalized_action, is_all = self._normalize_action(action)

        if is_all:
            projects = self.config.get_projects_from_workspace()
        else:
            projects = list(projects or [])

        if not projects:
            raise ValueError("Tidak ada Maven project yang tersedia.")

        java = self.config.get("java_home", "")
        if not java or not os.path.isdir(java):
            raise ValueError("Java Home tidak valid.")

        mvn = self.maven_command()
        if not mvn:
            raise FileNotFoundError("Maven executable tidak ditemukan.")

        maven_bin = os.path.dirname(mvn)
        if os.path.basename(maven_bin).lower() == "bin":
            self.config.set("maven_home", os.path.dirname(maven_bin))

        self.running = True
        started_all = time.perf_counter()
        results = []

        try:
            goals = self.ACTIONS[normalized_action]
            options = self._build_options(normalized_action)
            scope = "ALL PROJECTS" if is_all else "PROJECT"

            self.log("")
            self.log("=" * 78)
            self.log(f"STARTING MAVEN {normalized_action.upper()} [{scope}]")
            self.log(f"[PROJECTS] {len(projects)}")
            self.log(f"[MAVEN] {mvn}")
            self.log(f"[JAVA] {java}")
            self.log(f"[GOALS] {' '.join(goals)}")
            self.log(f"[OPTIONS] {' '.join(options)}")
            self.log("=" * 78)

            env = self._environment(java)

            # Deliberately sequential. Workspace projects may have dependencies.
            for index, project in enumerate(projects, start=1):
                results.append(
                    self._run_project(
                        normalized_action,
                        project,
                        index,
                        len(projects),
                        mvn,
                        env,
                    )
                )

            elapsed_all = time.perf_counter() - started_all
            success = sum(r["status"] == "success" for r in results)
            skipped = sum(r["status"] == "skipped" for r in results)
            ws_copied = sum(r.get("wsPropertiesCopied", 0) for r in results)

            self.log("")
            self.log("=" * 78)
            self.log(f"✅ MAVEN {normalized_action.upper()} COMPLETE")
            self.log(
                f"Success={success} Skipped={skipped} Failed=0 "
                f"Total={len(projects)} Completed={len(results)}"
            )
            self.log(f"Elapsed={self._format_duration(elapsed_all)}")
            if ws_copied:
                self.log(
                    f"[WEBAPP] ws.properties synchronized to "
                    f"{ws_copied} exploded artifact(s)."
                )
            self.log("[BUILD SUMMARY]")
            for result in results:
                self.log(
                    f"  {result['name']}: {result['status'].upper()} "
                    f"({self._format_duration(result['elapsed'])})"
                )
            self.log("=" * 78)

            return {
                "action": action,
                "success": success,
                "skipped": skipped,
                "failed": 0,
                "total": len(projects),
                "completed": len(results),
                "elapsed": elapsed_all,
                "wsPropertiesCopied": ws_copied,
                "results": results,
            }

        except Exception:
            elapsed_all = time.perf_counter() - started_all
            self.log(
                f"❌ MAVEN {normalized_action.upper()} FAILED "
                f"after {self._format_duration(elapsed_all)}"
            )
            raise
        finally:
            self.running = False
