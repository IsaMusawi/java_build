import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import subprocess
import threading
import shutil

# from path import tools_dir


class BuildPanel(tk.Frame):
    """
    Maven build panel.

    Maven actions:
        Install           -> mvn install
        Clean             -> mvn clean
        Clean & Install   -> mvn clean install

    Install is intentionally the default development operation. It does not
    remove target/ before building, which makes repeated development builds
    faster and closer to the normal IDE workflow.
    """

    MAVEN_ACTIONS = {
        "install": {
            "label": "⚡ INSTALL",
            "display": "Maven Install",
            "goals": ["install"],
        },
        "clean": {
            "label": "🧹 CLEAN",
            "display": "Maven Clean",
            "goals": ["clean"],
        },
        "clean_install": {
            "label": "🔨 CLEAN & INSTALL",
            "display": "Maven Clean & Install",
            "goals": ["clean", "install"],
        },
    }

    MAVEN_OPTIONS = [
        "-Dmaven.javadoc.skip=true",
        "-DskipTests",
        "-DPROJECT_ENV=LOCAL",
    ]

    def __init__(self, parent, config, logger):
        super().__init__(parent)

        self.config = config
        self.log = logger
        self.projects = []
        self.vars = []

        self.build_running = False

        self.setup_ui()

        if self.config.get("workspace_path"):
            self.load_projects()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def setup_ui(self):
        lbl = tk.Label(
            self,
            text="🛠️ Maven Build Manager",
            font=("Arial", 12, "bold"),
            fg="blue",
        )
        lbl.pack(pady=10)

        # --------------------------------------------------------------
        # Source configuration
        # --------------------------------------------------------------
        fr = tk.LabelFrame(
            self,
            text="Source Config",
            padx=5,
            pady=5,
        )
        fr.pack(fill=tk.X, padx=5)

        tk.Label(
            fr,
            text="Workspace (.code-workspace):",
        ).pack(anchor="w")

        self.ent_ws = tk.Entry(fr)
        self.ent_ws.insert(
            0,
            self.config.get("workspace_path"),
        )
        self.ent_ws.pack(fill=tk.X)

        tk.Button(
            fr,
            text="Browse...",
            command=self.browse_ws,
            font=("Arial", 8),
        ).pack(anchor="e", pady=2)

        tk.Label(
            fr,
            text="Java 8 Home:",
        ).pack(anchor="w")

        self.ent_java = tk.Entry(fr)
        self.ent_java.insert(
            0,
            self.config.get("java_home"),
        )
        self.ent_java.pack(fill=tk.X)

        tk.Button(
            fr,
            text="Browse...",
            command=self.browse_java,
            font=("Arial", 8),
        ).pack(anchor="e", pady=2)

        tk.Label(
            fr,
            text="Maven Home:",
        ).pack(anchor="w")

        self.ent_maven = tk.Entry(fr)
        self.ent_maven.insert(
            0,
            self.config.get("maven_home"),
        )
        self.ent_maven.pack(fill=tk.X)

        tk.Button(
            fr,
            text="Browse...",
            command=self.browse_maven,
            font=("Arial", 8),
        ).pack(anchor="e", pady=2)

        # --------------------------------------------------------------
        # Project list
        # --------------------------------------------------------------
        tk.Label(
            self,
            text="Project List:",
            font=("Arial", 9, "bold"),
        ).pack(
            anchor="w",
            padx=5,
            pady=(10, 0),
        )

        list_fr = tk.Frame(
            self,
            bd=1,
            relief="sunken",
        )
        list_fr.pack(
            fill=tk.BOTH,
            expand=True,
            padx=5,
        )

        cvs = tk.Canvas(
            list_fr,
            bg="white",
        )
        scr = ttk.Scrollbar(
            list_fr,
            orient="vertical",
            command=cvs.yview,
        )

        self.scroll_frame = tk.Frame(
            cvs,
            bg="white",
        )

        self.scroll_frame.bind(
            "<Configure>",
            lambda e: cvs.configure(
                scrollregion=cvs.bbox("all")
            ),
        )

        cvs.create_window(
            (0, 0),
            window=self.scroll_frame,
            anchor="nw",
        )
        cvs.configure(
            yscrollcommand=scr.set
        )

        cvs.pack(
            side="left",
            fill="both",
            expand=True,
        )
        scr.pack(
            side="right",
            fill="y",
        )

        # --------------------------------------------------------------
        # Action buttons
        # --------------------------------------------------------------
        btn_fr = tk.Frame(self)
        btn_fr.pack(
            fill=tk.X,
            padx=5,
            pady=10,
        )

        tk.Button(
            btn_fr,
            text="Reload",
            command=self.load_projects,
        ).pack(
            side=tk.LEFT,
            padx=2,
        )

        tk.Button(
            btn_fr,
            text="All",
            command=self.select_all,
        ).pack(
            side=tk.LEFT,
            padx=2,
        )

        tk.Button(
            btn_fr,
            text="None",
            command=self.clear_all,
        ).pack(
            side=tk.LEFT,
            padx=2,
        )

        # Maven operations.
        self.btn_install = tk.Button(
            btn_fr,
            text="⚡ INSTALL",
            bg="green",
            fg="white",
            font=("Arial", 9, "bold"),
            command=lambda: self.start_thread("install"),
        )
        self.btn_install.pack(
            side=tk.LEFT,
            padx=(12, 2),
            expand=True,
            fill=tk.X,
        )

        self.btn_clean = tk.Button(
            btn_fr,
            text="🧹 CLEAN",
            bg="#ff9800",
            fg="white",
            font=("Arial", 9, "bold"),
            command=lambda: self.start_thread("clean"),
        )
        self.btn_clean.pack(
            side=tk.LEFT,
            padx=2,
            expand=True,
            fill=tk.X,
        )

        self.btn_clean_install = tk.Button(
            btn_fr,
            text="🔨 CLEAN & INSTALL",
            bg="#1565c0",
            fg="white",
            font=("Arial", 9, "bold"),
            command=lambda: self.start_thread("clean_install"),
        )
        self.btn_clean_install.pack(
            side=tk.LEFT,
            padx=2,
            expand=True,
            fill=tk.X,
        )

        # Current operation indicator.
        self.lbl_status = tk.Label(
            self,
            text="Ready",
            anchor="w",
            fg="#555555",
        )
        self.lbl_status.pack(
            fill=tk.X,
            padx=7,
            pady=(0, 5),
        )

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def browse_ws(self):
        f = filedialog.askopenfilename(
            filetypes=[
                (
                    "VS Code Workspace",
                    "*.code-workspace",
                )
            ]
        )

        if f:
            self.ent_ws.delete(0, tk.END)
            self.ent_ws.insert(0, f)

            self.config.set(
                "workspace_path",
                f,
            )

            self.load_projects()

    def browse_java(self):
        d = filedialog.askdirectory()

        if d:
            self.ent_java.delete(0, tk.END)
            self.ent_java.insert(0, d)

            self.config.set(
                "java_home",
                d,
            )

    def browse_maven(self):
        d = filedialog.askdirectory(
            title="Select Maven Home"
        )

        if not d:
            return

        mvn_cmd = os.path.join(
            d,
            "bin",
            "mvn.cmd",
        )

        mvn_bat = os.path.join(
            d,
            "bin",
            "mvn.bat",
        )

        if os.path.exists(mvn_cmd):
            maven_home = d
        elif os.path.exists(mvn_bat):
            maven_home = d
        else:
            messagebox.showerror(
                "Maven",
                "Folder yang dipilih bukan Maven Home.\n\n"
                "Pastikan terdapat:\n"
                "<Maven Home>\\bin\\mvn.cmd"
            )
            return

        self.ent_maven.delete(0, tk.END)
        self.ent_maven.insert(0, maven_home)

        self.config.set(
            "maven_home",
            maven_home,
        )

        self.log(
            f"[MAVEN] Maven Home set to: {maven_home}"
        )

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------

    def load_projects(self):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        self.projects = []
        self.vars = []

        project_list = (
            self.config.get_projects_from_workspace()
        )

        if not project_list:
            self.log(
                "[WARN] Tidak ada project yang ditemukan "
                "atau path workspace salah."
            )
            return

        for name, full_path in project_list:
            var = tk.IntVar()

            tk.Checkbutton(
                self.scroll_frame,
                text=name,
                variable=var,
                anchor="w",
                bg="white",
            ).pack(
                fill="x",
                padx=5,
            )

            self.projects.append(full_path)
            self.vars.append(var)

        self.log(
            f"[INFO] Loaded {len(project_list)} projects."
        )

    def select_all(self):
        for var in self.vars:
            var.set(1)

    def clear_all(self):
        for var in self.vars:
            var.set(0)

    # ------------------------------------------------------------------
    # Maven
    # ------------------------------------------------------------------

    def get_mvn_command(self):
        """
        Return Maven executable from configured Maven Home.
        """
        maven_home = self.config.get("maven_home", "").strip()

        if not maven_home:
            return None, None

        mvn_cmd = os.path.join(
            maven_home,
            "bin",
            "mvn.cmd",
        )

        if os.path.isfile(mvn_cmd):
            return mvn_cmd, "Configured"

        mvn_bat = os.path.join(
            maven_home,
            "bin",
            "mvn.bat",
        )

        if os.path.isfile(mvn_bat):
            return mvn_bat, "Configured"

        return None, None

    def start_thread(self, action):
        if self.build_running:
            self.log(
                "[WARN] Maven operation sedang berjalan."
            )
            return

        if action not in self.MAVEN_ACTIONS:
            self.log(
                f"[ERROR] Unknown Maven action: {action}"
            )
            return

        selected = [
            i
            for i, var in enumerate(self.vars)
            if var.get() == 1
        ]

        if not selected:
            messagebox.showwarning(
                "Maven",
                "Pilih minimal satu project.",
            )
            return

        java = self.ent_java.get().strip()

        if not java or not os.path.isdir(java):
            messagebox.showerror(
                "Maven",
                "Java 8 Home tidak valid.",
            )
            return

        maven_home = self.ent_maven.get().strip()

        if not maven_home or not os.path.isdir(maven_home):
            messagebox.showerror(
                "Maven",
                "Maven Home tidak valid.",
            )
            return

        mvn_cmd, _ = self.get_mvn_command()

        if not mvn_cmd:
            messagebox.showerror(
                "Maven",
                "Maven executable tidak ditemukan.\n\n"
                "Pastikan Maven memiliki:\n"
                "<Maven Home>\\bin\\mvn.cmd",
            )
            return
        
        self.config.set(
            "maven_home",
            maven_home,
        )
        self.build_running = True
        self.set_buttons_state("disabled")

        display = self.MAVEN_ACTIONS[action]["display"]
        self.lbl_status.config(
            text=f"Running: {display}..."
        )

        threading.Thread(
            target=self.run_maven,
            args=(action, selected, java),
            daemon=True,
        ).start()

    def run_maven(self, action, selected, java):
        """
        Execute one Maven lifecycle action for every selected project.

        The projects are processed sequentially. This is important for a
        multi-module workspace where common-lib/bom may need to be installed
        before API/web projects.
        """
        action_config = self.MAVEN_ACTIONS[action]
        goals = action_config["goals"]

        mvn_cmd, source = self.get_mvn_command()

        if not mvn_cmd:
            self.log(
                "❌ Maven not found. "
                "Please configure Maven Home."
            )
            self.finish_build()
            return

        env = os.environ.copy()
        env["JAVA_HOME"] = java
        env["PATH"] = (
            f"{java}\\bin;"
            + env.get("PATH", "")
        )

        comspec = os.environ.get(
            "ComSpec",
            r"C:\Windows\System32\cmd.exe",
        )

        base_cmd = [
            mvn_cmd,
            *goals,
            *self.MAVEN_OPTIONS,
        ]

        self.log("")
        self.log("=" * 70)
        self.log(
            f"STARTING {action_config['display'].upper()} "
            f"({len(selected)} Projects)"
        )
        self.log(
            f"[MAVEN] {mvn_cmd} ({source})"
        )
        self.log(
            f"[GOALS] {' '.join(goals)}"
        )
        self.log("=" * 70)

        success_count = 0
        skipped_count = 0

        for idx in selected:
            project_path = self.projects[idx]
            name = os.path.basename(
                os.path.normpath(project_path)
            )

            self.log("")
            self.log(
                f">>> {action_config['display']}: {name}"
            )

            # ----------------------------------------------------------
            # Pre-flight
            # ----------------------------------------------------------
            if not os.path.isdir(project_path):
                self.log(
                    f"❌ [CRITICAL] Project folder not found: "
                    f"{project_path}"
                )
                self.finish_build()
                return

            if (
                isinstance(mvn_cmd, str)
                and mvn_cmd.lower().endswith(
                    (".cmd", ".bat")
                )
                and not os.path.exists(mvn_cmd)
            ):
                self.log(
                    f"❌ [CRITICAL] Maven file not found: "
                    f"{mvn_cmd}"
                )
                self.log(
                    "   └── Put apache-maven-* inside "
                    "./tools next to the EXE."
                )
                self.finish_build()
                return

            pom = os.path.join(
                project_path,
                "pom.xml",
            )

            if not os.path.exists(pom):
                skipped_count += 1
                self.log(
                    f"[SKIP] {name} (No pom.xml)"
                )
                continue

            # ----------------------------------------------------------
            # Execute
            # ----------------------------------------------------------
            try:
                if mvn_cmd.lower().endswith(
                    (".cmd", ".bat")
                ):
                    cmdline = [
                        comspec,
                        "/c",
                        *base_cmd,
                    ]
                else:
                    cmdline = base_cmd

                self.log(
                    f"[DEBUG] cwd={project_path}"
                )
                self.log(
                    f"[DEBUG] goals={' '.join(goals)}"
                )

                proc = subprocess.Popen(
                    cmdline,
                    cwd=project_path,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    env=env,
                    universal_newlines=True,
                )

                for line in proc.stdout:
                    line = line.rstrip()

                    # Keep useful Maven output in the application log.
                    if (
                        "[INFO]" in line
                        or "[WARNING]" in line
                        or "[ERROR]" in line
                        or "BUILD" in line
                    ):
                        self.log(line)

                proc.wait()

                if proc.returncode == 0:
                    success_count += 1

                    self.log(
                        f"✅ {name} SUCCESS"
                    )

                    # Only an operation producing artifacts should patch
                    # the generated dfms-web deployment.
                    if (
                        action != "clean"
                        and "dfms-web" in name
                    ):
                        self.copy_ws(project_path)

                else:
                    self.log(
                        f"❌ {name} FAILED "
                        f"(exit={proc.returncode})"
                    )

                    self.show_error_async(
                        "Maven Failed",
                        (
                            f"{action_config['display']} failed "
                            f"for {name}."
                        ),
                    )
                    self.finish_build()
                    return

            except FileNotFoundError as exc:
                self.log(
                    f"❌ [CRITICAL] FileNotFoundError: {exc}"
                )
                self.log(
                    f"[DEBUG] cmdline={cmdline}"
                )
                self.log(
                    f"[DEBUG] cwd={project_path}"
                )
                self.finish_build()
                return

            except Exception as exc:
                self.log(
                    f"❌ [CRITICAL] {exc}"
                )
                self.finish_build()
                return

        self.log("")
        self.log("=" * 70)
        self.log(
            f"✅ {action_config['display'].upper()} COMPLETE"
        )
        self.log(
            f"   Success : {success_count}"
        )
        self.log(
            f"   Skipped : {skipped_count}"
        )
        self.log(
            f"   Total   : {len(selected)}"
        )
        self.log("=" * 70)

        self.show_info_async(
            "Maven",
            (
                f"{action_config['display']} completed.\n\n"
                f"Success: {success_count}\n"
                f"Skipped: {skipped_count}"
            ),
        )

        self.finish_build()

    # ------------------------------------------------------------------
    # UI state
    # ------------------------------------------------------------------

    def set_buttons_state(self, state):
        self.btn_install.config(state=state)
        self.btn_clean.config(state=state)
        self.btn_clean_install.config(state=state)

    def finish_build(self):
        def update():
            self.build_running = False
            self.set_buttons_state("normal")
            self.lbl_status.config(text="Ready")

        self.after(0, update)

    def show_error_async(self, title, message):
        self.after(
            0,
            lambda: messagebox.showerror(
                title,
                message,
            ),
        )

    def show_info_async(self, title, message):
        self.after(
            0,
            lambda: messagebox.showinfo(
                title,
                message,
            ),
        )

    # ------------------------------------------------------------------
    # Post-build patch
    # ------------------------------------------------------------------

    def copy_ws(self, path):
        src = os.path.join(
            path,
            "src",
            "main",
            "webapp",
            "WEB-INF",
            "ws.properties",
        )

        dst = os.path.join(
            path,
            "target",
            "dfms-web",
            "WEB-INF",
        )

        if not os.path.exists(src):
            self.log(
                "   └── [WARN] ws.properties missing in src."
            )
            return

        try:
            os.makedirs(
                dst,
                exist_ok=True,
            )

            shutil.copy(
                src,
                dst,
            )

            self.log(
                "   └── [PATCH] ws.properties copied."
            )

        except Exception as exc:
            self.log(
                f"   └── [ERROR] Copy failed: {exc}"
            )
