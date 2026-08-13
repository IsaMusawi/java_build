import json
import os
import re
import shutil
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from config import ConfigManager
from path import tools_dir


class BuildManagerApp:
    """
    Standalone Maven Build Manager.

    Configuration is workspace-scoped through ConfigManager:

        <workspace>/
            project.code-workspace
            .sm-devops/
                devops_settings.json
                tomcat-instances/
                    Tomcat-1/
                    Tomcat-2/

    Tomcat architecture is intentionally shared:

        tomcat_home = CATALINA_HOME (one Tomcat distribution)
        deploy_map[instance].catalina_base = CATALINA_BASE per instance

    This class does not modify CATALINA_HOME. Instance-specific Tomcat
    configuration belongs to TomcatPanel and its CATALINA_BASE.
    """

    MAVEN_OPTIONS = [
        "-Dmaven.javadoc.skip=true",
        "-DskipTests",
        "-DPROJECT_ENV=LOCAL",
    ]

    TARGET_IGNORE_DIRS = {
        "classes",
        "test-classes",
        "maven-archiver",
        "maven-status",
        "surefire-reports",
    }

    def __init__(self, root):
        self.root = root
        self.root.title("SM Build Manager V2.3 (Workspace Scoped)")
        self.root.geometry("900x750")

        self.config = ConfigManager()
        self.projects = []
        self.vars = []
        self.build_running = False

        self.setup_ui()

        # Workspace is selected explicitly. This avoids the old global
        # build_manager_settings.json collision between workspaces.
        self.root.withdraw()
        if not self.select_workspace():
            self.root.destroy()
            return
        self.root.deiconify()

        self.load_initial_settings()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def setup_ui(self):
        frame_config = tk.LabelFrame(
            self.root,
            text="Configuration & Health Check",
            padx=10,
            pady=10,
        )
        frame_config.pack(fill=tk.X, padx=10, pady=5)

        tk.Label(
            frame_config,
            text="Workspace File (.code-workspace):",
        ).grid(row=0, column=0, sticky="w")

        self.entry_workspace = tk.Entry(frame_config, width=70)
        self.entry_workspace.grid(row=0, column=1, padx=5)

        tk.Button(
            frame_config,
            text="Browse...",
            command=self.browse_workspace,
        ).grid(row=0, column=2)

        tk.Label(
            frame_config,
            text="Java 8 Home Path:",
        ).grid(row=1, column=0, sticky="w")

        self.entry_java = tk.Entry(frame_config, width=70)
        self.entry_java.grid(row=1, column=1, padx=5)

        tk.Button(
            frame_config,
            text="Browse...",
            command=self.browse_java,
        ).grid(row=1, column=2)

        tk.Label(
            frame_config,
            text="Maven Home:",
        ).grid(row=2, column=0, sticky="w")

        self.entry_maven = tk.Entry(frame_config, width=70)
        self.entry_maven.grid(row=2, column=1, padx=5)

        tk.Button(
            frame_config,
            text="Browse...",
            command=self.browse_maven,
        ).grid(row=2, column=2)

        tk.Label(
            frame_config,
            text="Shared Tomcat Home:",
        ).grid(row=3, column=0, sticky="w")

        self.entry_tomcat = tk.Entry(frame_config, width=70)
        self.entry_tomcat.grid(row=3, column=1, padx=5)

        tk.Button(
            frame_config,
            text="Browse...",
            command=self.browse_tomcat,
        ).grid(row=3, column=2)

        self.lbl_tomcat_info = tk.Label(
            frame_config,
            text="CATALINA_HOME: not configured",
            anchor="w",
            fg="#555555",
        )
        self.lbl_tomcat_info.grid(
            row=4,
            column=1,
            sticky="w",
            padx=5,
            pady=(2, 0),
        )

        frame_actions = tk.Frame(frame_config)
        frame_actions.grid(row=5, column=1, sticky="w", pady=10)

        tk.Button(
            frame_actions,
            text="🔄 Reload Projects",
            command=self.load_projects_from_workspace,
            bg="#f0f0f0",
        ).pack(side=tk.LEFT, padx=(0, 10))

        tk.Button(
            frame_actions,
            text="🩺 Check Dependencies",
            command=self.run_dependency_check_ui,
            bg="#e3f2fd",
        ).pack(side=tk.LEFT)

        lbl_list = tk.Label(
            self.root,
            text="Select Projects to Build:",
            font=("Arial", 11, "bold"),
        )
        lbl_list.pack(pady=(5, 0))

        frame_list = tk.Frame(self.root, bd=1, relief="sunken")
        frame_list.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        canvas = tk.Canvas(frame_list, bg="white")
        scrollbar = ttk.Scrollbar(
            frame_list,
            orient="vertical",
            command=canvas.yview,
        )
        self.scrollable_frame = tk.Frame(canvas, bg="white")

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )

        canvas.create_window(
            (0, 0),
            window=self.scrollable_frame,
            anchor="nw",
        )
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        frame_btn = tk.Frame(self.root)
        frame_btn.pack(pady=10)

        tk.Button(
            frame_btn,
            text="Select All",
            command=self.select_all,
        ).pack(side=tk.LEFT, padx=5)

        tk.Button(
            frame_btn,
            text="Clear All",
            command=self.clear_all,
        ).pack(side=tk.LEFT, padx=5)

        self.btn_build = tk.Button(
            frame_btn,
            text="BUILD SELECTED 🚀",
            bg="green",
            fg="white",
            font=("Arial", 10, "bold"),
            command=self.start_build_thread,
        )
        self.btn_build.pack(side=tk.LEFT, padx=20)

        self.log_area = scrolledtext.ScrolledText(
            self.root,
            height=12,
            state="disabled",
            bg="black",
            fg="#00FF00",
            font=("Consolas", 9),
        )
        self.log_area.pack(fill=tk.X, padx=10, pady=(0, 10))

    # ------------------------------------------------------------------
    # Workspace / configuration
    # ------------------------------------------------------------------

    def select_workspace(self):
        filename = filedialog.askopenfilename(
            parent=self.root,
            title="Select VS Code Workspace",
            filetypes=[
                ("VS Code Workspace", "*.code-workspace"),
                ("All Files", "*.*"),
            ],
        )

        if not filename:
            return False

        try:
            self.config.switch_workspace(filename)
            return True
        except Exception as exc:
            messagebox.showerror(
                "Workspace",
                f"Gagal membuka workspace:\n\n{exc}",
                parent=self.root,
            )
            return False

    def load_initial_settings(self):
        self.entry_workspace.delete(0, tk.END)
        self.entry_workspace.insert(0, self.config.get("workspace_path", ""))

        self.entry_java.delete(0, tk.END)
        self.entry_java.insert(0, self.config.get("java_home", ""))

        self.entry_maven.delete(0, tk.END)
        self.entry_maven.insert(0, self.config.get("maven_home", ""))

        self.entry_tomcat.delete(0, tk.END)
        self.entry_tomcat.insert(0, self.config.get_tomcat_home())

        self.update_tomcat_info()

        if self.config.get("workspace_path"):
            self.load_projects_from_workspace()

    def browse_workspace(self):
        filename = filedialog.askopenfilename(
            filetypes=[
                ("VS Code Workspace", "*.code-workspace"),
                ("All Files", "*.*"),
            ]
        )

        if not filename:
            return

        try:
            self.config.switch_workspace(filename)
            self.load_initial_settings()
        except Exception as exc:
            messagebox.showerror(
                "Workspace",
                f"Gagal membuka workspace:\n\n{exc}",
            )

    def browse_java(self):
        directory = filedialog.askdirectory()
        if not directory:
            return

        self.entry_java.delete(0, tk.END)
        self.entry_java.insert(0, directory)
        self.config.set("java_home", directory)

    def browse_maven(self):
        directory = filedialog.askdirectory(title="Select Maven Home")
        if not directory:
            return

        mvn_cmd = os.path.join(directory, "bin", "mvn.cmd")
        mvn_bat = os.path.join(directory, "bin", "mvn.bat")

        if not (os.path.exists(mvn_cmd) or os.path.exists(mvn_bat)):
            messagebox.showerror(
                "Maven",
                "Folder yang dipilih bukan Maven Home.\n\n"
                "Pastikan terdapat:\n"
                "<Maven Home>\\bin\\mvn.cmd",
            )
            return

        self.entry_maven.delete(0, tk.END)
        self.entry_maven.insert(0, directory)
        self.config.set("maven_home", directory)

        self.log(f"[MAVEN] Maven Home set to: {directory}")

    def browse_tomcat(self):
        directory = filedialog.askdirectory(title="Select Shared Tomcat Home")
        if not directory:
            return

        if not self.is_valid_tomcat_home(directory):
            messagebox.showerror(
                "Tomcat",
                "Folder yang dipilih bukan Tomcat Home yang valid.\n\n"
                "Pastikan terdapat:\n"
                "<Tomcat Home>\\bin\\catalina.bat\n"
                "<Tomcat Home>\\conf\\server.xml",
            )
            return

        self.entry_tomcat.delete(0, tk.END)
        self.entry_tomcat.insert(0, directory)
        self.config.set_tomcat_home(directory)
        self.update_tomcat_info()

        self.log(
            "[TOMCAT] Shared CATALINA_HOME set to: "
            f"{directory}"
        )
        self.log(
            "[TOMCAT] Per-instance CATALINA_BASE is managed separately "
            "under .sm-devops/tomcat-instances/."
        )

    def update_tomcat_info(self):
        tomcat_home = self.config.get_tomcat_home()
        if tomcat_home:
            self.lbl_tomcat_info.config(
                text=f"CATALINA_HOME: {tomcat_home} | CATALINA_BASE: per instance"
            )
        else:
            self.lbl_tomcat_info.config(
                text="CATALINA_HOME: not configured | CATALINA_BASE: per instance"
            )

    def detect_java8_path(self):
        user_home = os.path.expanduser("~")
        specific_path = os.path.join(
            user_home,
            "Documents",
            "SM_TOOLS",
            "java",
            "jdk8u452-b09",
        )
        if os.path.exists(specific_path):
            return specific_path

        env_java = os.environ.get("JAVA_HOME", "")
        if env_java and ("1.8" in env_java or "jdk8" in env_java.lower()):
            return env_java

        common_roots = [
            r"C:\Program Files\Java",
            r"C:\Program Files (x86)\Java",
        ]
        for root in common_roots:
            if os.path.exists(root):
                try:
                    for folder in os.listdir(root):
                        if "jdk1.8" in folder or "jdk-8" in folder:
                            return os.path.join(root, folder)
                except OSError:
                    pass

        return ""

    # ------------------------------------------------------------------
    # Maven
    # ------------------------------------------------------------------

    def get_mvn_command(self):
        """Configured Maven -> portable Maven -> system Maven."""
        configured = self.entry_maven.get().strip()
        if configured:
            mvn_cmd = os.path.join(configured, "bin", "mvn.cmd")
            mvn_bat = os.path.join(configured, "bin", "mvn.bat")
            if os.path.isfile(mvn_cmd):
                return mvn_cmd, "Configured"
            if os.path.isfile(mvn_bat):
                return mvn_bat, "Configured"

        tdir = tools_dir()
        if tdir.exists():
            try:
                for folder in sorted(os.listdir(str(tdir))):
                    if folder.startswith("apache-maven"):
                        mvn_bin = os.path.join(
                            str(tdir),
                            folder,
                            "bin",
                            "mvn.cmd",
                        )
                        if os.path.isfile(mvn_bin):
                            return mvn_bin, "Portable"
            except OSError:
                pass

        system_maven = shutil.which("mvn")
        if system_maven:
            return system_maven, "System"

        return None, None

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def check_prerequisites(self):
        errors = []

        mvn_cmd, source = self.get_mvn_command()
        if not mvn_cmd:
            errors.append(
                "❌ Maven not found! (Configured, portable, and System PATH checked)"
            )
        else:
            self.log(f"[CHECK] Using {source} Maven: {mvn_cmd}")

        java_home = self.entry_java.get().strip()
        if not java_home or not os.path.isdir(java_home):
            errors.append("❌ Java Path is empty or does not exist.")
        else:
            java_exe = os.path.join(java_home, "bin", "java.exe")
            javac_exe = os.path.join(java_home, "bin", "javac.exe")

            if not os.path.exists(java_exe):
                errors.append(f"❌ java.exe not found in {java_exe}")
            elif not os.path.exists(javac_exe):
                self.log(
                    "[WARN] javac.exe not found. "
                    "Is this a JRE? JDK is recommended for Maven."
                )
            else:
                self.log(
                    f"[CHECK] Java binaries verified at: {java_home}"
                )

        tomcat_home = self.entry_tomcat.get().strip()
        if tomcat_home:
            if self.is_valid_tomcat_home(tomcat_home):
                self.log(
                    "[CHECK] Shared Tomcat CATALINA_HOME verified: "
                    f"{tomcat_home}"
                )
                self.log(
                    "[CHECK] Tomcat instances use isolated CATALINA_BASE "
                    "under the selected workspace."
                )
            else:
                errors.append(
                    "❌ Shared Tomcat Home is invalid. "
                    "Expected bin\\catalina.bat and conf\\server.xml."
                )

        return errors

    @staticmethod
    def is_valid_tomcat_home(path):
        if not path or not os.path.isdir(path):
            return False

        return (
            os.path.isfile(os.path.join(path, "bin", "catalina.bat"))
            and os.path.isfile(os.path.join(path, "conf", "server.xml"))
        )

    def run_dependency_check_ui(self):
        self.log("\n--- Running Dependency Check ---")
        errors = self.check_prerequisites()
        if errors:
            for err in errors:
                self.log(err)
            messagebox.showerror(
                "Dependency Missing",
                "\n".join(errors),
            )
        else:
            self.log("✅ All System Dependencies are OK!")
            messagebox.showinfo(
                "System Check",
                "All dependencies are ready for build!",
            )

    # ------------------------------------------------------------------
    # Workspace projects
    # ------------------------------------------------------------------

    def load_projects_from_workspace(self):
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()

        self.projects = []
        self.vars = []

        workspace_file = self.config.get("workspace_path", "")
        if not workspace_file or not os.path.isfile(workspace_file):
            self.log("[INFO] Select a valid workspace file.")
            return

        try:
            project_list = self.config.get_projects_from_workspace()

            for name, full_path in project_list:
                var = tk.IntVar()
                tk.Checkbutton(
                    self.scrollable_frame,
                    text=full_path,
                    variable=var,
                    anchor="w",
                    bg="white",
                ).pack(fill="x", padx=5, pady=2)

                self.projects.append(full_path)
                self.vars.append(var)

            self.log(f"[INFO] Loaded {len(self.projects)} projects.")

        except Exception as exc:
            self.log(f"[ERROR] Load failed: {exc}")

    def select_all(self):
        for var in self.vars:
            var.set(1)

    def clear_all(self):
        for var in self.vars:
            var.set(0)

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def start_build_thread(self):
        if self.build_running:
            self.log("[WARN] Build is already running.")
            return

        errors = self.check_prerequisites()
        if errors:
            messagebox.showerror(
                "Pre-Build Check Failed",
                "\n".join(errors),
            )
            return

        selected_indices = [
            i for i, var in enumerate(self.vars)
            if var.get() == 1
        ]

        if not selected_indices:
            messagebox.showwarning(
                "Build",
                "Pilih minimal satu project.",
            )
            return

        self.build_running = True
        self.btn_build.config(
            state="disabled",
            text="Building... ⏳",
        )

        threading.Thread(
            target=self.run_builds,
            args=(selected_indices,),
            daemon=True,
        ).start()

    def run_builds(self, selected_indices):
        java_home = self.entry_java.get().strip()
        mvn_cmd_path, mvn_source = self.get_mvn_command()

        if not mvn_cmd_path:
            self.finish_build()
            self.show_error_async("Error", "Maven not found!")
            return

        my_env = os.environ.copy()
        my_env["JAVA_HOME"] = java_home
        my_env["PATH"] = (
            f"{java_home}\\bin;"
            + my_env.get("PATH", "")
        )

        comspec = os.environ.get(
            "ComSpec",
            r"C:\Windows\System32\cmd.exe",
        )

        base_cmd = [
            mvn_cmd_path,
            "clean",
            "install",
            *self.MAVEN_OPTIONS,
        ]

        self.log("\n" + "=" * 60)
        self.log("STARTING BUILD SEQUENCE")
        self.log(f"[MAVEN] {mvn_cmd_path} ({mvn_source})")
        self.log("[WORKSPACE] " + self.config.get("workspace_path", ""))
        self.log("=" * 60)

        for idx in selected_indices:
            project_path = self.projects[idx]
            folder_name = os.path.basename(
                os.path.normpath(project_path)
            )

            self.log(f"\n>>> Building: {folder_name} ...")

            if not os.path.isdir(project_path):
                self.log(
                    "❌ [CRITICAL] Project folder not found: "
                    f"{project_path}"
                )
                self.finish_build()
                return

            if not os.path.isfile(os.path.join(project_path, "pom.xml")):
                self.log("[SKIP] No pom.xml")
                continue

            try:
                if base_cmd[0].lower().endswith((".cmd", ".bat")):
                    cmdline = [comspec, "/c", *base_cmd]
                else:
                    cmdline = base_cmd

                self.log(
                    f"[DEBUG] cmd={cmdline[0]} | cwd={project_path}"
                )

                process = subprocess.Popen(
                    cmdline,
                    cwd=project_path,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    env=my_env,
                    universal_newlines=True,
                )

                for line in process.stdout:
                    line = line.rstrip()
                    if any(
                        marker in line
                        for marker in (
                            "[INFO]",
                            "[ERROR]",
                            "[WARNING]",
                            "BUILD",
                        )
                    ):
                        self.log(line)

                process.wait()

                if process.returncode == 0:
                    self.log(f"✅ [SUCCESS] {folder_name}")
                    self.copy_ws_properties(project_path)
                else:
                    self.log(
                        f"❌ [FAILURE] {folder_name} "
                        f"(exit={process.returncode})"
                    )
                    self.show_error_async(
                        "Build Failed",
                        f"Failed to build {folder_name}",
                    )
                    self.finish_build()
                    return

            except FileNotFoundError as exc:
                self.log(f"❌ [CRITICAL] FileNotFoundError: {exc}")
                self.log(f"[DEBUG] cmdline={cmdline}")
                self.log(f"[DEBUG] cwd={project_path}")
                self.finish_build()
                return

            except Exception as exc:
                self.log(f"[CRITICAL ERROR] {exc}")
                self.finish_build()
                return

        self.log("\n" + "=" * 60)
        self.log("🎉 ALL DONE!")
        self.log("=" * 60)

        self.finish_build()
        self.show_info_async("Done", "Build Completed!")

    # ------------------------------------------------------------------
    # ws.properties patch
    # ------------------------------------------------------------------

    def copy_ws_properties(self, project_path):
        """
        Copy ws.properties from source into the project's exploded web
        artifact after a successful Maven build.

        This is deliberately generic. There is NO dependency on a project
        named 'dfms-web'.

        Source:
            <project>/src/main/webapp/WEB-INF/ws.properties

        Destination:
            <project>/target/<exploded-artifact>/WEB-INF/ws.properties

        The exploded artifact is detected by looking for target directories
        that contain WEB-INF. Maven's common metadata directories are ignored.
        """
        src = os.path.join(
            project_path,
            "src",
            "main",
            "webapp",
            "WEB-INF",
            "ws.properties",
        )

        if not os.path.isfile(src):
            # Not every project is a web project, so this is normal.
            self.log(
                "   └── [PATCH] ws.properties not present; skipped."
            )
            return False

        target_dir = os.path.join(project_path, "target")
        if not os.path.isdir(target_dir):
            self.log(
                "   └── [PATCH] target directory not found; skipped."
            )
            return False

        candidates = self.find_exploded_web_artifacts(target_dir)

        if not candidates:
            self.log(
                "   └── [PATCH] No exploded web artifact found in target; skipped."
            )
            return False

        copied = 0

        for artifact_dir in candidates:
            destination_dir = os.path.join(
                artifact_dir,
                "WEB-INF",
            )

            try:
                os.makedirs(destination_dir, exist_ok=True)
                shutil.copy2(src, destination_dir)
                copied += 1

                artifact_name = os.path.basename(artifact_dir)
                self.log(
                    "   └── [PATCH] ws.properties copied to "
                    f"target/{artifact_name}/WEB-INF/"
                )

            except Exception as exc:
                self.log(
                    "   └── [ERROR] Copy failed for "
                    f"{artifact_dir}: {exc}"
                )

        return copied > 0

    def find_exploded_web_artifacts(self, target_dir):
        """
        Return exploded web artifact directories under target/.

        A valid candidate must be a direct child of target/ and contain a
        WEB-INF directory. This avoids accidentally copying into Maven's
        classes, status, or report directories.
        """
        candidates = []

        try:
            for item in sorted(os.listdir(target_dir)):
                if item in self.TARGET_IGNORE_DIRS:
                    continue

                candidate = os.path.join(target_dir, item)

                if not os.path.isdir(candidate):
                    continue

                web_inf = os.path.join(candidate, "WEB-INF")
                if os.path.isdir(web_inf):
                    candidates.append(candidate)

        except OSError as exc:
            self.log(
                f"   └── [WARN] Cannot inspect target directory: {exc}"
            )

        return candidates

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------

    def set_build_button_state(self, state, text=None):
        def update():
            try:
                self.btn_build.config(
                    state=state,
                    text=text or "BUILD SELECTED 🚀",
                )
            except tk.TclError:
                pass

        try:
            self.root.after(0, update)
        except tk.TclError:
            pass

    def finish_build(self):
        self.build_running = False
        self.set_build_button_state(
            "normal",
            "BUILD SELECTED 🚀",
        )

    def show_error_async(self, title, message):
        try:
            self.root.after(
                0,
                lambda: messagebox.showerror(title, message),
            )
        except tk.TclError:
            pass

    def show_info_async(self, title, message):
        try:
            self.root.after(
                0,
                lambda: messagebox.showinfo(title, message),
            )
        except tk.TclError:
            pass

    def log(self, message):
        def write():
            try:
                self.log_area.config(state="normal")
                self.log_area.insert(tk.END, str(message) + "\n")
                self.log_area.see(tk.END)
                self.log_area.config(state="disabled")
            except tk.TclError:
                pass

        try:
            self.root.after(0, write)
        except tk.TclError:
            pass


if __name__ == "__main__":
    root = tk.Tk()
    app = BuildManagerApp(root)
    root.mainloop()
