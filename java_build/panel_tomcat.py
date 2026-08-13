import html
import json
import os
import re
import shutil
import socket
import subprocess
import threading
import time
import tkinter as tk

from tkinter import (
    filedialog,
    messagebox,
    simpledialog,
    ttk,
)


class TomcatPanel(tk.Frame):
    """
    One TomcatPanel represents ONE Tomcat instance.

    A Tomcat instance can contain many deployments:

        Tomcat-1
            /email-api
            /vendor-api
            /common-api
            /dfms-web

    The panel itself is still designed to work inside ttk.Notebook,
    but the Notebook tabs are hidden by MainApp.
    """

    CONTEXT_RE = re.compile(
        r"^[A-Za-z0-9._-]+$"
    )

    DEBUG_START_TIMEOUT = 30
    DEBUG_POLL_INTERVAL = 0.5

    def __init__(
        self,
        parent,
        config,
        logger,
        instance_name="Tomcat",
    ):
        super().__init__(parent)

        self.config = config
        self.raw_logger = logger
        self.instance_name = instance_name
        self.rename_callback = None

        # --------------------------------------------------------------
        # Tomcat process state
        # --------------------------------------------------------------
        self.launcher_proc = None
        self.tomcat_pid = None
        self.tomcat_home = None
        self.catalina_base = None
        self.process_lock = threading.Lock()

        # --------------------------------------------------------------
        # Project selection
        # --------------------------------------------------------------
        self.project_map = {}
        self.selected_project_path = ""

        # --------------------------------------------------------------
        # UI vars
        # --------------------------------------------------------------
        self.deploy_target_name = tk.StringVar()

        self.var_port_http = tk.StringVar()
        self.var_port_ajp = tk.StringVar()
        self.var_port_shutdown = tk.StringVar()
        self.var_port_debug = tk.StringVar()

        self.setup_ui()

        self.load_server_home()
        self.load_current_ports()
        self.refresh_project_list()
        self.refresh_deployment_list()

    # ==================================================================
    # General
    # ==================================================================

    def log(self, msg):
        self.raw_logger(
            f"[{self.instance_name}] {msg}"
        )

    def set_rename_callback(self, func):
        self.rename_callback = func

    # ==================================================================
    # UI
    # ==================================================================

    def setup_ui(self):
        """
        Layout strategy:

            Fixed:
                Header
                Server Path
                Port Configuration
                Deployment
                Deployment Buttons
                Tomcat Control

            Expandable:
                Deployed Applications

        This prevents START / DEBUG / STOP from being pushed out
        of the visible area when the window is resized smaller.
        """

        # ==============================================================
        # Main content container
        # ==============================================================

        main = tk.Frame(self)

        main.pack(
            fill=tk.BOTH,
            expand=True,
        )

        # Only the deployed-applications row is allowed to expand.
        main.grid_columnconfigure(
            0,
            weight=1,
        )

        main.grid_rowconfigure(
            0,
            weight=0,
        )

        main.grid_rowconfigure(
            1,
            weight=0,
        )

        main.grid_rowconfigure(
            2,
            weight=0,
        )

        main.grid_rowconfigure(
            3,
            weight=0,
        )

        main.grid_rowconfigure(
            4,
            weight=1,
        )

        main.grid_rowconfigure(
            5,
            weight=0,
        )

        main.grid_rowconfigure(
            6,
            weight=0,
        )

        # ==============================================================
        # Header
        # ==============================================================

        header = tk.Frame(main)

        header.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=5,
            pady=5,
        )

        header.grid_columnconfigure(
            0,
            weight=1,
        )

        self.lbl_title = tk.Label(
            header,
            text=(
                f"🐱 Server: "
                f"{self.instance_name}"
            ),
            font=("Arial", 11, "bold"),
            fg="#ff6600",
        )

        self.lbl_title.grid(
            row=0,
            column=0,
            sticky="w",
        )

        tk.Button(
            header,
            text="✏️ Rename",
            font=("Arial", 7),
            command=self.rename_tab,
        ).grid(
            row=0,
            column=1,
            sticky="e",
            padx=5,
        )

        # ==============================================================
        # Server Path
        # ==============================================================

        server_frame = tk.LabelFrame(
            main,
            text="Server Path",
            padx=5,
            pady=5,
        )

        server_frame.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=5,
            pady=(0, 5),
        )

        server_frame.grid_columnconfigure(
            0,
            weight=1,
        )

        path_frame = tk.Frame(
            server_frame
        )

        path_frame.grid(
            row=0,
            column=0,
            sticky="ew",
        )

        path_frame.grid_columnconfigure(
            0,
            weight=1,
        )

        self.ent_home = tk.Entry(
            path_frame
        )

        self.ent_home.grid(
            row=0,
            column=0,
            sticky="ew",
        )

        tk.Button(
            path_frame,
            text="Browse...",
            command=self.browse_home,
            font=("Arial", 8),
        ).grid(
            row=0,
            column=1,
            padx=(5, 0),
        )

        tk.Label(
            server_frame,
            text="Instance Base (CATALINA_BASE):",
        ).grid(
            row=1,
            column=0,
            sticky="w",
            pady=(5, 0),
        )

        base_frame = tk.Frame(server_frame)
        base_frame.grid(
            row=2,
            column=0,
            sticky="ew",
        )

        base_frame.grid_columnconfigure(
            0,
            weight=1,
        )

        self.ent_base = tk.Entry(base_frame)
        self.ent_base.grid(
            row=0,
            column=0,
            sticky="ew",
        )

        tk.Button(
            base_frame,
            text="Browse...",
            command=self.browse_base,
            font=("Arial", 8),
        ).grid(
            row=0,
            column=1,
            padx=(5, 0),
        )

        # ==============================================================
        # Port Configuration
        # ==============================================================

        port_frame = tk.LabelFrame(
            main,
            text="Port Configuration",
            padx=5,
            pady=5,
            fg="blue",
        )

        port_frame.grid(
            row=2,
            column=0,
            sticky="ew",
            padx=5,
            pady=(0, 5),
        )

        tk.Label(
            port_frame,
            text="HTTP:",
        ).grid(
            row=0,
            column=0,
            sticky="w",
        )

        tk.Entry(
            port_frame,
            textvariable=self.var_port_http,
            width=7,
        ).grid(
            row=0,
            column=1,
            padx=2,
        )

        tk.Label(
            port_frame,
            text="AJP:",
        ).grid(
            row=0,
            column=2,
            sticky="w",
        )

        tk.Entry(
            port_frame,
            textvariable=self.var_port_ajp,
            width=7,
        ).grid(
            row=0,
            column=3,
            padx=2,
        )

        tk.Label(
            port_frame,
            text="Shut:",
        ).grid(
            row=1,
            column=0,
            sticky="w",
        )

        tk.Entry(
            port_frame,
            textvariable=self.var_port_shutdown,
            width=7,
        ).grid(
            row=1,
            column=1,
            padx=2,
        )

        tk.Label(
            port_frame,
            text="Debug:",
        ).grid(
            row=1,
            column=2,
            sticky="w",
        )

        tk.Entry(
            port_frame,
            textvariable=self.var_port_debug,
            width=7,
        ).grid(
            row=1,
            column=3,
            padx=2,
        )

        tk.Button(
            port_frame,
            text="💾",
            bg="#ffeb3b",
            command=self.save_ports,
        ).grid(
            row=0,
            column=4,
            rowspan=2,
            padx=5,
            sticky="ns",
        )

        # ==============================================================
        # Deployment Editor
        # ==============================================================

        deploy_frame = tk.LabelFrame(
            main,
            text="⚡ Deployment",
            padx=5,
            pady=5,
            bg="#e3f2fd",
        )

        deploy_frame.grid(
            row=3,
            column=0,
            sticky="ew",
            padx=5,
            pady=(0, 5),
        )

        deploy_frame.grid_columnconfigure(
            0,
            weight=1,
        )

        select_frame = tk.Frame(
            deploy_frame,
            bg="#e3f2fd",
        )

        select_frame.grid(
            row=0,
            column=0,
            sticky="ew",
        )

        select_frame.grid_columnconfigure(
            1,
            weight=1,
        )

        tk.Label(
            select_frame,
            text="Project:",
            bg="#e3f2fd",
        ).grid(
            row=0,
            column=0,
            sticky="w",
        )

        self.cb_projects = ttk.Combobox(
            select_frame,
            state="readonly",
        )

        self.cb_projects.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=5,
        )

        self.cb_projects.bind(
            "<<ComboboxSelected>>",
            self.on_project_selected,
        )

        tk.Button(
            select_frame,
            text="🔄",
            command=self.refresh_project_list,
            bg="white",
            width=3,
        ).grid(
            row=0,
            column=2,
        )

        action_frame = tk.Frame(
            deploy_frame,
            bg="#e3f2fd",
        )

        action_frame.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(5, 0),
        )

        action_frame.grid_columnconfigure(
            3,
            weight=1,
        )

        tk.Label(
            action_frame,
            text="Ctx:",
            bg="#e3f2fd",
        ).grid(
            row=0,
            column=0,
            sticky="w",
        )

        self.ent_target = tk.Entry(
            action_frame,
            textvariable=self.deploy_target_name,
            font=("Arial", 9, "bold"),
            fg="blue",
            width=16,
        )

        self.ent_target.grid(
            row=0,
            column=1,
            padx=2,
        )

        self.btn_deploy = tk.Button(
            action_frame,
            text="📥 Deploy / Update",
            bg="#2196F3",
            fg="white",
            font=("Arial", 9, "bold"),
            command=self.execute_deployment,
        )

        self.btn_deploy.grid(
            row=0,
            column=3,
            sticky="ew",
            padx=2,
        )

        # ==============================================================
        # Deployed Applications
        #
        # THIS is the only expandable section.
        # ==============================================================

        list_frame = tk.LabelFrame(
            main,
            text="Deployed Applications",
            padx=5,
            pady=5,
        )

        list_frame.grid(
            row=4,
            column=0,
            sticky="nsew",
            padx=5,
            pady=(0, 5),
        )

        list_frame.grid_rowconfigure(
            0,
            weight=1,
        )

        list_frame.grid_columnconfigure(
            0,
            weight=1,
        )

        columns = (
            "context",
            "project",
            "target",
        )

        self.tree = ttk.Treeview(
            list_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
        )

        self.tree.heading(
            "context",
            text="Context",
        )

        self.tree.heading(
            "project",
            text="Project",
        )

        self.tree.heading(
            "target",
            text="Target",
        )

        self.tree.column(
            "context",
            width=130,
            anchor="w",
        )

        self.tree.column(
            "project",
            width=180,
            anchor="w",
        )

        self.tree.column(
            "target",
            width=130,
            anchor="w",
        )

        tree_scroll = ttk.Scrollbar(
            list_frame,
            orient="vertical",
            command=self.tree.yview,
        )

        self.tree.configure(
            yscrollcommand=tree_scroll.set
        )

        self.tree.grid(
            row=0,
            column=0,
            sticky="nsew",
        )

        tree_scroll.grid(
            row=0,
            column=1,
            sticky="ns",
        )

        self.tree.bind(
            "<<TreeviewSelect>>",
            self.on_deployment_selected,
        )

        # ==============================================================
        # Deployment Buttons
        #
        # Fixed row.
        # ==============================================================

        deployment_buttons = tk.Frame(
            main
        )

        deployment_buttons.grid(
            row=5,
            column=0,
            sticky="ew",
            padx=5,
            pady=(0, 5),
        )

        tk.Button(
            deployment_buttons,
            text="🔄 Refresh",
            command=self.refresh_deployment_list,
        ).pack(
            side=tk.LEFT,
            padx=2,
        )

        tk.Button(
            deployment_buttons,
            text="🗑 Undeploy",
            bg="#ff9800",
            command=self.undeploy_selected,
        ).pack(
            side=tk.LEFT,
            padx=2,
        )

        # ==============================================================
        # Tomcat Control
        #
        # Fixed row.
        #
        # This is the important fix for the disappearing buttons.
        # ==============================================================

        control_frame = tk.LabelFrame(
            main,
            text="Tomcat Control",
            padx=5,
            pady=5,
        )

        control_frame.grid(
            row=6,
            column=0,
            sticky="ew",
            padx=5,
            pady=(0, 5),
        )

        control_frame.grid_columnconfigure(
            0,
            weight=1,
        )

        control_frame.grid_columnconfigure(
            1,
            weight=1,
        )

        control_frame.grid_columnconfigure(
            2,
            weight=1,
        )

        tk.Button(
            control_frame,
            text="▶ START",
            bg="#4CAF50",
            fg="white",
            command=lambda: self.start(False),
        ).grid(
            row=0,
            column=0,
            sticky="ew",
            padx=2,
        )

        tk.Button(
            control_frame,
            text="🐞 DEBUG",
            bg="#9C27B0",
            fg="white",
            command=lambda: self.start(True),
        ).grid(
            row=0,
            column=1,
            sticky="ew",
            padx=2,
        )

        tk.Button(
            control_frame,
            text="⏹ STOP",
            bg="#f44336",
            fg="white",
            command=self.stop,
        ).grid(
            row=0,
            column=2,
            sticky="ew",
            padx=2,
        )

    # ==================================================================
    # Tomcat Home / CATALINA_BASE
    # ==================================================================

    def load_server_home(self):
        home = self.config.get_tomcat_home()

        if home:
            self.ent_home.delete(0, tk.END)
            self.ent_home.insert(0, home)
            self.tomcat_home = home

        base = self.config.ensure_instance_base(
            self.instance_name
        )

        if base:
            self.ent_base.delete(0, tk.END)
            self.ent_base.insert(0, base)
            self.catalina_base = base

        if home and os.path.isdir(home):
            try:
                self.ensure_instance_runtime(home, base)
            except Exception as exc:
                self.log(
                    f"[WARN] Cannot initialize CATALINA_BASE: {exc}"
                )

    def browse_home(self):
        directory = filedialog.askdirectory(
            title="Select shared Tomcat Home (CATALINA_HOME)"
        )

        if not directory:
            return

        if not os.path.isdir(os.path.join(directory, "bin")):
            return messagebox.showerror(
                "Tomcat Home",
                "Folder yang dipilih bukan Tomcat Home.\n\n"
                "Pastikan terdapat folder bin dan conf.",
            )

        self.ent_home.delete(0, tk.END)
        self.ent_home.insert(0, directory)

        self.tomcat_home = directory
        self.config.set_tomcat_home(directory)

        base = self.config.ensure_instance_base(
            self.instance_name
        )

        self.ent_base.delete(0, tk.END)
        self.ent_base.insert(0, base)
        self.catalina_base = base

        try:
            self.ensure_instance_runtime(directory, base)
            self.load_current_ports()
        except Exception as exc:
            self.log(
                f"[ERROR] Failed to initialize instance: {exc}"
            )

    def browse_base(self):
        directory = filedialog.askdirectory(
            title="Select CATALINA_BASE for this instance"
        )

        if not directory:
            return

        self.config.set_instance_base(
            self.instance_name,
            directory,
        )

        self.catalina_base = directory

        self.ent_base.delete(0, tk.END)
        self.ent_base.insert(0, directory)

        home = self.ent_home.get().strip()

        if home and os.path.isdir(home):
            try:
                self.ensure_instance_runtime(home, directory)
                self.load_current_ports()
            except Exception as exc:
                self.log(
                    f"[ERROR] Failed to initialize CATALINA_BASE: {exc}"
                )

    def _initialize_instance_ports(self, base):
        """
        Give a newly-created CATALINA_BASE a deterministic port offset.

        Instance #1 keeps the Tomcat distribution's original ports.
        Instance #2 becomes +1, instance #3 +2, and so on.

        This only runs for a freshly copied server.xml, so user-edited
        instance ports are never overwritten later.
        """
        server_xml = os.path.join(
            base,
            "conf",
            "server.xml",
        )

        if not os.path.isfile(server_xml):
            return

        tabs = self.config.get_active_tabs()
        current = self.instance_name

        names = list(tabs) if isinstance(tabs, list) else []

        if current not in names:
            names.append(current)

        try:
            offset = names.index(current)
        except ValueError:
            offset = 0

        if offset <= 0:
            return

        try:
            with open(
                server_xml,
                "r",
                encoding="utf-8",
            ) as f:
                content = f.read()

            ports = {
                "shutdown": 8005 + offset,
                "http": 8080 + offset,
                "ajp": 8009 + offset,
            }

            content = re.sub(
                r'(<Server[^>]*port=")\d+(")',
                rf'\g<1>{ports["shutdown"]}\g<2>',
                content,
                count=1,
            )

            content = re.sub(
                r'(<Connector[^>]*protocol=["\']HTTP/[^"\']*["\'][^>]*port=")\d+(")',
                rf'\g<1>{ports["http"]}\g<2>',
                content,
                count=1,
            )

            content = re.sub(
                r'(<Connector[^>]*port=")\d+("[^>]*protocol=["\']HTTP)',
                rf'\g<1>{ports["http"]}\g<2>',
                content,
                count=1,
            )

            content = re.sub(
                r'(<Connector[^>]*protocol=["\']AJP/[^"\']*["\'][^>]*port=")\d+(")',
                rf'\g<1>{ports["ajp"]}\g<2>',
                content,
                count=1,
            )

            content = re.sub(
                r'(<Connector[^>]*port=")\d+("[^>]*protocol=["\']AJP)',
                rf'\g<1>{ports["ajp"]}\g<2>',
                content,
                count=1,
            )

            with open(
                server_xml,
                "w",
                encoding="utf-8",
            ) as f:
                f.write(content)

            setenv = os.path.join(
                base,
                "bin",
                "setenv.bat",
            )

            debug_port = 8000 + offset

            with open(
                setenv,
                "w",
                encoding="utf-8",
            ) as f:
                f.write(
                    "set JPDA_ADDRESS="
                    f"{debug_port}\n"
                    "set JPDA_TRANSPORT=dt_socket\n"
                )

            self.log(
                "[TOMCAT] Auto-assigned ports: "
                f"HTTP={ports['http']}, "
                f"AJP={ports['ajp']}, "
                f"Shutdown={ports['shutdown']}, "
                f"Debug={debug_port}"
            )

        except Exception as exc:
            self.log(
                f"[WARN] Could not auto-assign ports: {exc}"
            )

    def ensure_instance_runtime(self, home, base):
        """
        Bootstrap an isolated CATALINA_BASE.

        CATALINA_HOME is never modified. Each instance receives its own
        conf/logs/temp/webapps/work/bin directories.
        """

        if not base:
            raise ValueError("CATALINA_BASE belum ditentukan.")

        if not os.path.isdir(home):
            raise ValueError(f"CATALINA_HOME tidak valid: {home}")

        os.makedirs(base, exist_ok=True)

        for directory in (
            "logs",
            "temp",
            "webapps",
            "work",
            "conf",
            "bin",
        ):
            os.makedirs(
                os.path.join(base, directory),
                exist_ok=True,
            )

        source_conf = os.path.join(home, "conf")
        target_conf = os.path.join(base, "conf")
        server_xml = os.path.join(target_conf, "server.xml")

        # Copy the standard Tomcat configuration only once. After that,
        # server.xml belongs exclusively to this instance.
        if (
            os.path.isdir(source_conf)
            and not os.path.exists(server_xml)
        ):
            for item in os.listdir(source_conf):
                source = os.path.join(source_conf, item)
                target = os.path.join(target_conf, item)

                if os.path.isdir(source):
                    shutil.copytree(
                        source,
                        target,
                        dirs_exist_ok=True,
                    )
                else:
                    shutil.copy2(source, target)

            self.log(
                "[TOMCAT] Initialized isolated "
                f"CATALINA_BASE: {base}"
            )

            self._initialize_instance_ports(base)

        self.config.set_instance_base(
            self.instance_name,
            base,
        )

        self.catalina_base = base

    # ==================================================================
    # Project List
    # ==================================================================

    def refresh_project_list(self):
        projects = (
            self.config.get_projects_from_workspace()
        )

        self.project_map = {
            name: path
            for name, path in projects
        }

        self.cb_projects["values"] = list(
            self.project_map.keys()
        )

        if not projects:
            self.log(
                "[WARN] Workspace kosong atau belum diset."
            )

    def on_project_selected(
        self,
        _event=None,
    ):
        name = self.cb_projects.get()

        path = self.project_map.get(
            name,
            "",
        )

        if not path:
            return

        self.selected_project_path = path

        self.detect_target_folder()

    def detect_target_folder(self):
        if not self.selected_project_path:
            return

        target_dir = os.path.join(
            self.selected_project_path,
            "target",
        )

        if not os.path.exists(
            target_dir
        ):
            self.deploy_target_name.set(
                ""
            )

            self.log(
                "[INFO] target belum ada. "
                f"Build dulu: {self.cb_projects.get()}"
            )

            return

        ignore_dirs = {
            "classes",
            "test-classes",
            "maven-archiver",
            "maven-status",
            "surefire-reports",
        }

        candidates = []

        for item in os.listdir(
            target_dir
        ):
            full_path = os.path.join(
                target_dir,
                item,
            )

            if item in ignore_dirs:
                continue

            if os.path.isdir(
                full_path
            ):
                candidates.append(
                    item
                )

            elif item.lower().endswith(
                ".war"
            ):
                candidates.append(
                    os.path.splitext(item)[0]
                )

        candidates.sort()

        if candidates:
            self.deploy_target_name.set(
                candidates[0]
            )

            self.log(
                f"[INFO] Target detected: "
                f"{candidates[0]}"
            )

        else:
            self.deploy_target_name.set(
                ""
            )

    # ==================================================================
    # Deployment Persistence
    # ==================================================================

    def refresh_deployment_list(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        deployments = (
            self.config.get_instance_deployments(
                self.instance_name
            )
        )

        for context, data in sorted(
            deployments.items()
        ):
            project = data.get(
                "project",
                "",
            )

            target = data.get(
                "target",
                "",
            )

            self.tree.insert(
                "",
                "end",
                iid=context,
                values=(
                    f"/{context}",
                    (
                        os.path.basename(project)
                        if project
                        else ""
                    ),
                    target,
                ),
            )

    def on_deployment_selected(
        self,
        _event=None,
    ):
        selected = self.tree.selection()

        if not selected:
            return

        context = selected[0]

        deployments = (
            self.config.get_instance_deployments(
                self.instance_name
            )
        )

        data = deployments.get(
            context,
            {},
        )

        project = data.get(
            "project",
            "",
        )

        target = data.get(
            "target",
            "",
        )

        self.selected_project_path = project

        self.deploy_target_name.set(
            target
        )

        project_name = ""

        for name, path in self.project_map.items():
            if os.path.normcase(
                path
            ) == os.path.normcase(
                project
            ):
                project_name = name
                break

        if project_name:
            self.cb_projects.set(
                project_name
            )

    # ==================================================================
    # Deployment
    # ==================================================================

    def execute_deployment(self):
        home = self.ent_home.get().strip()

        project_path = (
            self.selected_project_path
        )

        target = (
            self.deploy_target_name.get().strip()
        )

        context = self.config.normalize_context(
            target
        )

        if not home:
            return messagebox.showerror(
                "Deployment Error",
                "Tomcat Home belum diset.",
            )

        if not project_path:
            return messagebox.showerror(
                "Deployment Error",
                "Pilih Maven project terlebih dahulu.",
            )

        if not context:
            return messagebox.showerror(
                "Deployment Error",
                "Context name tidak boleh kosong.",
            )

        if not self.CONTEXT_RE.fullmatch(
            context
        ):
            return messagebox.showerror(
                "Deployment Error",
                (
                    "Context hanya boleh berisi "
                    "huruf, angka, '.', '_' atau '-'."
                ),
            )

        target_dir = os.path.join(
            project_path,
            "target",
        )

        directory = os.path.join(
            target_dir,
            target,
        )

        war_file = os.path.join(
            target_dir,
            f"{target}.war",
        )

        if os.path.isdir(
            directory
        ):
            docbase = directory

        elif os.path.isfile(
            war_file
        ):
            docbase = war_file

        else:
            return messagebox.showerror(
                "Deployment Error",
                (
                    "Artifact tidak ditemukan:\n\n"
                    f"{directory}\natau\n{war_file}\n\n"
                    "Build project terlebih dahulu."
                ),
            )

        base = self.ent_base.get().strip()

        if not base:
            return messagebox.showerror(
                "Deployment Error",
                "CATALINA_BASE belum diset.",
            )

        try:
            self.ensure_instance_runtime(home, base)
        except Exception as exc:
            return messagebox.showerror(
                "Deployment Error",
                f"Gagal menyiapkan CATALINA_BASE:\n\n{exc}",
            )

        xml_dir = os.path.join(
            base,
            "conf",
            "Catalina",
            "localhost",
        )

        xml_path = os.path.join(
            xml_dir,
            f"{context}.xml",
        )

        try:
            os.makedirs(
                xml_dir,
                exist_ok=True,
            )

            safe_docbase = html.escape(
                os.path.abspath(docbase),
                quote=True,
            )

            xml_content = (
                f'<Context docBase="{safe_docbase}" '
                f'reloadable="true"></Context>'
            )

            with open(
                xml_path,
                "w",
                encoding="utf-8",
            ) as f:
                f.write(
                    xml_content
                )

            self.config.set_tomcat_home(
                home,
            )

            self.config.set_instance_base(
                self.instance_name,
                base,
            )

            self.config.set_instance_deployment(
                self.instance_name,
                context,
                project_path,
                target,
            )

            self.refresh_deployment_list()

            self.log(
                f"✅ Deployed /{context} -> {docbase}"
            )

            messagebox.showinfo(
                "Deployment",
                (
                    f"/{context} berhasil dideploy "
                    f"ke {self.instance_name}."
                ),
            )

        except Exception as exc:
            self.log(
                f"❌ Deploy error: {exc}"
            )

            messagebox.showerror(
                "Deployment Error",
                str(exc),
            )

    def undeploy_selected(self):
        selected = self.tree.selection()

        if not selected:
            return messagebox.showwarning(
                "Undeploy",
                "Pilih deployment terlebih dahulu.",
            )

        context = selected[0]

        home = self.ent_home.get().strip()

        if not home:
            return messagebox.showerror(
                "Undeploy",
                "Tomcat Home belum diset.",
            )

        base = self.ent_base.get().strip()

        if not base:
            return messagebox.showerror(
                "Undeploy",
                "CATALINA_BASE belum diset.",
            )

        xml_path = os.path.join(
            base,
            "conf",
            "Catalina",
            "localhost",
            f"{context}.xml",
        )

        if not messagebox.askyesno(
            "Confirm",
            f"Undeploy /{context}?",
        ):
            return

        try:
            if os.path.exists(
                xml_path
            ):
                os.remove(
                    xml_path
                )

            self.config.remove_instance_deployment(
                self.instance_name,
                context,
            )

            self.refresh_deployment_list()

            self.log(
                f"🗑 Undeployed /{context}"
            )

        except Exception as exc:
            self.log(
                f"❌ Undeploy error: {exc}"
            )

            messagebox.showerror(
                "Undeploy Error",
                str(exc),
            )

    # ==================================================================
    # Rename
    # ==================================================================

    def rename_tab(self):
        new_name = simpledialog.askstring(
            "Rename",
            "Nama server:",
            initialvalue=self.instance_name,
        )

        if not new_name:
            return

        new_name = new_name.strip()

        if (
            not new_name
            or new_name == self.instance_name
        ):
            return

        old_name = self.instance_name

        self.config.rename_instance(
            old_name,
            new_name,
        )

        self.instance_name = new_name

        self.lbl_title.config(
            text=(
                f"🐱 Server: "
                f"{new_name}"
            )
        )

        # Notebook tabs are hidden now, but keep the internal
        # tab title updated for compatibility.
        try:
            current_index = (
                self.master.index(
                    self.master.select()
                )
            )

            self.master.tab(
                current_index,
                text=new_name,
            )

        except Exception:
            pass

        self.refresh_deployment_list()

        if self.rename_callback:
            self.rename_callback()

    # ==================================================================
    # Ports
    # ==================================================================

    def load_current_ports(self):
        home = self.ent_home.get().strip()

        if (
            not home
            or not os.path.exists(home)
        ):
            return

        base = self.ent_base.get().strip()

        if not base:
            return

        server_xml = os.path.join(
            base,
            "conf",
            "server.xml",
        )

        if os.path.exists(
            server_xml
        ):
            try:
                with open(
                    server_xml,
                    "r",
                    encoding="utf-8",
                ) as f:
                    content = f.read()

                match = re.search(
                    r'<Server[^>]*port="(\d+)"',
                    content,
                )

                if match:
                    self.var_port_shutdown.set(
                        match.group(1)
                    )

                match = re.search(
                    r'<Connector[^>]*'
                    r'protocol=["\']HTTP/[^"\']*["\']'
                    r'[^>]*port=["\'](\d+)["\']',
                    content,
                )

                if not match:
                    match = re.search(
                        r'<Connector[^>]*'
                        r'port=["\'](\d+)["\']'
                        r'[^>]*protocol=["\']HTTP',
                        content,
                    )

                if match:
                    self.var_port_http.set(
                        match.group(1)
                    )

                match = re.search(
                    r'<Connector[^>]*'
                    r'protocol=["\']AJP/[^"\']*["\']'
                    r'[^>]*port=["\'](\d+)["\']',
                    content,
                )

                if not match:
                    match = re.search(
                        r'<Connector[^>]*'
                        r'port=["\'](\d+)["\']'
                        r'[^>]*protocol=["\']AJP',
                        content,
                    )

                if match:
                    self.var_port_ajp.set(
                        match.group(1)
                    )

            except Exception as exc:
                self.log(
                    "[WARN] Cannot read "
                    f"server.xml: {exc}"
                )

        setenv = os.path.join(
            base,
            "bin",
            "setenv.bat",
        )

        if os.path.exists(
            setenv
        ):
            try:
                with open(
                    setenv,
                    "r",
                    encoding="utf-8",
                ) as f:
                    content = f.read()

                match = re.search(
                    r"JPDA_ADDRESS=(\d+)",
                    content,
                )

                if match:
                    self.var_port_debug.set(
                        match.group(1)
                    )

            except Exception:
                pass

        elif not self.var_port_debug.get():
            self.var_port_debug.set(
                "8000"
            )

    def save_ports(self):
        home = self.ent_home.get().strip()

        if (
            not home
            or not os.path.exists(home)
        ):
            return

        base = self.ent_base.get().strip()

        if not base:
            return

        try:
            self.ensure_instance_runtime(
                home,
                base,
            )

            server_xml = os.path.join(
                base,
                "conf",
                "server.xml",
            )

            with open(
                server_xml,
                "r",
                encoding="utf-8",
            ) as f:
                content = f.read()

            shutdown = (
                self.var_port_shutdown.get().strip()
            )

            http = (
                self.var_port_http.get().strip()
            )

            ajp = (
                self.var_port_ajp.get().strip()
            )

            if shutdown:
                content = re.sub(
                    r'(<Server[^>]*port=")(\d+)(")',
                    rf'\g<1>{shutdown}\g<3>',
                    content,
                    count=1,
                )

            if http:
                content = re.sub(
                    r'(<Connector[^>]*'
                    r'protocol=["\']HTTP/[^"\']*["\']'
                    r'[^>]*port=")(\d+)(")',
                    rf'\g<1>{http}\g<3>',
                    content,
                    count=1,
                )

                content = re.sub(
                    r'(<Connector[^>]*'
                    r'port=")(\d+)("'
                    r'[^>]*protocol=["\']HTTP)',
                    rf'\g<1>{http}\g<3>',
                    content,
                    count=1,
                )

            if ajp:
                content = re.sub(
                    r'(<Connector[^>]*'
                    r'protocol=["\']AJP/[^"\']*["\']'
                    r'[^>]*port=")(\d+)(")',
                    rf'\g<1>{ajp}\g<3>',
                    content,
                    count=1,
                )

                content = re.sub(
                    r'(<Connector[^>]*'
                    r'port=")(\d+)("'
                    r'[^>]*protocol=["\']AJP)',
                    rf'\g<1>{ajp}\g<3>',
                    content,
                    count=1,
                )

            with open(
                server_xml,
                "w",
                encoding="utf-8",
            ) as f:
                f.write(
                    content
                )

            self.config.set_instance_home(
                self.instance_name,
                home,
            )

        except Exception as exc:
            self.log(
                f"❌ Error server.xml: {exc}"
            )
            return

        # --------------------------------------------------------------
        # JPDA debug port
        # --------------------------------------------------------------

        setenv = os.path.join(
            base,
            "bin",
            "setenv.bat",
        )

        debug_port = (
            self.var_port_debug.get().strip()
        )

        try:
            content = ""

            if os.path.exists(
                setenv
            ):
                with open(
                    setenv,
                    "r",
                    encoding="utf-8",
                ) as f:
                    content = f.read()

            if "JPDA_ADDRESS" in content:
                content = re.sub(
                    r"(JPDA_ADDRESS=)(\d+)",
                    rf"\g<1>{debug_port}",
                    content,
                )

            else:
                content += (
                    f"\nset JPDA_ADDRESS={debug_port}"
                )

            if "JPDA_TRANSPORT" not in content:
                content += (
                    "\nset JPDA_TRANSPORT=dt_socket"
                )

            with open(
                setenv,
                "w",
                encoding="utf-8",
            ) as f:
                f.write(
                    content
                )

            self.log(
                "✅ Ports saved."
            )

        except Exception as exc:
            self.log(
                f"❌ Error saving debug port: {exc}"
            )

    # ==================================================================
    # Tomcat Lifecycle
    # ==================================================================

    def start(self, debug=False):
        if debug:
            self.start_debug()
            return

        self.start_normal()

    def start_normal(self):
        home = self.ent_home.get().strip()
        base = self.ent_base.get().strip()

        java = self.config.get(
            "java_home"
        )

        if not os.path.isdir(home):
            return messagebox.showerror(
                "Tomcat",
                "Tomcat Home tidak valid.",
            )

        if not os.path.isdir(java):
            return messagebox.showerror(
                "Tomcat",
                "JAVA_HOME tidak valid.",
            )

        try:
            self.ensure_instance_runtime(home, base)
        except Exception as exc:
            return messagebox.showerror(
                "Tomcat",
                f"Gagal menyiapkan CATALINA_BASE:\n\n{exc}",
            )

        if self.is_tomcat_running():
            return messagebox.showinfo(
                "Tomcat",
                "Tomcat instance ini sudah berjalan.",
            )

        self.config.set_instance_home(
            self.instance_name,
            home,
        )

        env = os.environ.copy()

        env["JAVA_HOME"] = java
        env["CATALINA_HOME"] = home
        env["CATALINA_BASE"] = base

        env["PATH"] = (
            f"{java}\\bin;"
            f"{home}\\bin;"
            + env.get("PATH", "")
        )

        env["PROJECT_ENV"] = "LOCAL"

        command = (
            "catalina.bat jpda run"
        )

        self.log(
            "🚀 STARTING Tomcat "
            f"({self.var_port_http.get() or '?'})..."
        )

        threading.Thread(
            target=self._run_proc,
            args=(
                command,
                home,
                base,
                env,
            ),
            daemon=True,
        ).start()

    def start_debug(self):
        home = self.ent_home.get().strip()
        base = self.ent_base.get().strip()

        java = self.config.get(
            "java_home"
        )

        workspace = self.config.get(
            "workspace_path"
        )

        debug_port = (
            self.var_port_debug.get().strip()
        )

        # --------------------------------------------------------------
        # Validation
        # --------------------------------------------------------------

        if not os.path.isdir(home):
            return messagebox.showerror(
                "Debug",
                "Tomcat Home tidak valid.",
            )

        if not os.path.isdir(java):
            return messagebox.showerror(
                "Debug",
                "JAVA_HOME tidak valid.",
            )

        try:
            self.ensure_instance_runtime(home, base)
        except Exception as exc:
            return messagebox.showerror(
                "Debug",
                f"Gagal menyiapkan CATALINA_BASE:\n\n{exc}",
            )

        if (
            not workspace
            or not os.path.isfile(workspace)
        ):
            return messagebox.showerror(
                "Debug",
                (
                    "VS Code workspace tidak ditemukan:\n\n"
                    f"{workspace or '(empty)'}"
                ),
            )

        if not debug_port.isdigit():
            return messagebox.showerror(
                "Debug",
                "Debug port harus berupa angka.",
            )

        debug_port = int(
            debug_port
        )

        if not 1 <= debug_port <= 65535:
            return messagebox.showerror(
                "Debug",
                (
                    "Debug port harus berada "
                    "antara 1-65535."
                ),
            )

        if self.is_tomcat_running():
            return messagebox.showinfo(
                "Debug",
                "Tomcat instance ini sudah berjalan.",
            )

        # --------------------------------------------------------------
        # Update VS Code workspace
        # --------------------------------------------------------------

        try:
            debug_config = (
                self.config.update_workspace_debug_config(
                    self.instance_name,
                    debug_port,
                )
            )

            self.log(
                "[VS CODE] Debug configuration updated."
            )

            self.log(
                f"[VS CODE] {debug_config['name']}"
            )

            self.log(
                "[VS CODE] "
                f"{debug_config['hostName']}:"
                f"{debug_config['port']}"
            )

        except Exception as exc:
            self.log(
                f"❌ Workspace update failed: {exc}"
            )

            return messagebox.showerror(
                "Debug",
                (
                    "Gagal meng-update "
                    ".code-workspace.\n\n"
                    f"{exc}"
                ),
            )

        # --------------------------------------------------------------
        # Persist configuration
        # --------------------------------------------------------------

        self.config.set_instance_home(
            self.instance_name,
            home,
        )

        # --------------------------------------------------------------
        # Prepare JPDA
        # --------------------------------------------------------------

        try:
            self.prepare_jpda(
                base,
                debug_port,
            )

        except Exception as exc:
            self.log(
                "❌ Failed to prepare JPDA: "
                f"{exc}"
            )

            return messagebox.showerror(
                "Debug",
                (
                    "Gagal menyiapkan JPDA:\n\n"
                    f"{exc}"
                ),
            )

        # --------------------------------------------------------------
        # Environment
        # --------------------------------------------------------------

        env = os.environ.copy()

        env["JAVA_HOME"] = java
        env["CATALINA_HOME"] = home
        env["CATALINA_BASE"] = base

        env["PATH"] = (
            f"{java}\\bin;"
            f"{home}\\bin;"
            + env.get("PATH", "")
        )


        self.log("")
        self.log("=" * 70)

        self.log(
            "🐞 DEBUG START: "
            f"{self.instance_name}"
        )

        self.log(
            "[DEBUG] HTTP : "
            f"{self.var_port_http.get() or '?'}"
        )

        self.log(
            "[DEBUG] JPDA : "
            f"localhost:{debug_port}"
        )

        self.log("=" * 70)

        threading.Thread(
            target=self._start_debug_sequence,
            args=(
                home,
                base,
                env,
                debug_port,
                workspace,
            ),
            daemon=True,
        ).start()

    def _run_proc(
        self,
        command,
        home,
        base,
        env,
    ):
        launcher = None

        try:
            creation_flags = getattr(
                subprocess,
                "CREATE_NEW_PROCESS_GROUP",
                0,
            )

            launcher = subprocess.Popen(
                command,
                cwd=os.path.join(
                    home,
                    "bin",
                ),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                shell=True,
                universal_newlines=True,
                creationflags=creation_flags,
            )

            with self.process_lock:
                self.launcher_proc = launcher
                self.tomcat_home = home
                self.catalina_base = base

            self.log(
                "[PROCESS] Launcher started. "
                f"PID={launcher.pid}"
            )

            deadline = (
                time.time()
                + self.DEBUG_START_TIMEOUT
            )

            while time.time() < deadline:
                pid = self._find_tomcat_pid(
                    home,
                    base,
                    launcher.pid,
                )

                if pid:
                    with self.process_lock:
                        self.tomcat_pid = pid

                    self.log(
                        "✅ Tomcat JVM detected. "
                        f"PID={pid}"
                    )

                    break

                if launcher.poll() is not None:
                    break

                time.sleep(
                    self.DEBUG_POLL_INTERVAL
                )

            for line in launcher.stdout:
                line = line.rstrip()

                if line:
                    self.log(line)

            return_code = launcher.wait()

            if self.is_tomcat_running():
                with self.process_lock:
                    tomcat_pid = (
                        self.tomcat_pid
                    )

                self.log(
                    "[PROCESS] Launcher exited "
                    f"(exit={return_code}), "
                    "but Tomcat JVM "
                    f"PID={tomcat_pid} "
                    "is still running."
                )

            else:
                self.log(
                    "🛑 Tomcat stopped "
                    f"(launcher exit={return_code})."
                )

        except Exception as exc:
            self.log(
                f"❌ Tomcat process error: {exc}"
            )

        finally:
            with self.process_lock:
                self.launcher_proc = None

    def stop(self):
        """
        Stop ONLY the Tomcat JVM belonging to this instance.

        We intentionally do NOT use:
            taskkill /IM java.exe

        because unrelated Java applications must remain alive.
        """

        home = self.ent_home.get().strip()
        base = self.ent_base.get().strip()

        if not home:
            self.log(
                "Tomcat Home belum diset."
            )
            return

        if not base:
            self.log(
                "CATALINA_BASE belum diset."
            )
            return

        with self.process_lock:
            tomcat_pid = self.tomcat_pid

        if not tomcat_pid:
            tomcat_pid = self._find_tomcat_pid(
                home,
                base,
            )

            if tomcat_pid:
                with self.process_lock:
                    self.tomcat_pid = tomcat_pid

        if not tomcat_pid:
            self.log(
                "Tomcat is not running."
            )
            return

        self.log(
            "⏹ Stopping Tomcat JVM "
            f"PID={tomcat_pid}..."
        )

        try:
            result = subprocess.run(
                [
                    "taskkill",
                    "/PID",
                    str(tomcat_pid),
                    "/T",
                    "/F",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )

            output = (
                result.stdout or ""
            ).strip()

            if output:
                self.log(
                    f"[STOP] {output}"
                )

            if result.returncode == 0:
                self.log(
                    "⏹ Stop command sent to "
                    f"Tomcat PID={tomcat_pid}"
                )

            else:
                self.log(
                    "❌ Failed to stop "
                    f"Tomcat PID={tomcat_pid}"
                )

            deadline = (
                time.time()
                + 5
            )

            while time.time() < deadline:
                if not self.is_tomcat_running():
                    with self.process_lock:
                        self.tomcat_pid = None

                    self.log(
                        "🛑 Tomcat stopped."
                    )

                    return

                time.sleep(
                    0.2
                )

            self.log(
                "⚠️ Tomcat PID="
                f"{tomcat_pid} "
                "still appears to be running."
            )

        except Exception as exc:
            self.log(
                f"❌ Stop error: {exc}"
            )

    # ==================================================================
    # JPDA
    # ==================================================================

    def prepare_jpda(
        self,
        base,
        debug_port,
    ):
        os.makedirs(
            os.path.join(
                base,
                "bin",
            ),
            exist_ok=True,
        )

        setenv = os.path.join(
            base,
            "bin",
            "setenv.bat",
        )

        content = ""

        if os.path.exists(
            setenv
        ):
            with open(
                setenv,
                "r",
                encoding="utf-8",
            ) as f:
                content = f.read()

        if "JPDA_ADDRESS" in content:
            content = re.sub(
                r"(JPDA_ADDRESS=)([^\r\n]+)",
                rf"\g<1>{debug_port}",
                content,
            )

        else:
            content += (
                f"\nset JPDA_ADDRESS={debug_port}"
            )

        if "JPDA_TRANSPORT" in content:
            content = re.sub(
                r"(JPDA_TRANSPORT=)([^\r\n]+)",
                r"\g<1>dt_socket",
                content,
            )

        else:
            content += (
                "\nset JPDA_TRANSPORT=dt_socket"
            )

        with open(
            setenv,
            "w",
            encoding="utf-8",
        ) as f:
            f.write(
                content
            )

        self.log(
            "[DEBUG] JPDA configured: "
            f"localhost:{debug_port}"
        )

    # ==================================================================
    # Debug Sequence
    # ==================================================================

    def _start_debug_sequence(
        self,
        home,
        base,
        env,
        debug_port,
        workspace,
    ):
        try:
            creation_flags = getattr(
                subprocess,
                "CREATE_NEW_PROCESS_GROUP",
                0,
            )

            launcher = subprocess.Popen(
                "catalina.bat jpda run",
                cwd=os.path.join(
                    home,
                    "bin",
                ),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                shell=True,
                universal_newlines=True,
                creationflags=creation_flags,
            )

            with self.process_lock:
                self.launcher_proc = launcher
                self.tomcat_home = home
                self.catalina_base = base

            self.log(
                "[DEBUG] Launcher started. "
                f"PID={launcher.pid}"
            )

            threading.Thread(
                target=self._read_launcher_output,
                args=(launcher,),
                daemon=True,
            ).start()

            ready = self.wait_for_debug_port(
                "127.0.0.1",
                debug_port,
                self.DEBUG_START_TIMEOUT,
            )

            if not ready:
                self.log(
                    "❌ JDWP endpoint was not ready."
                )

                self.show_error_async(
                    "Debug",
                    (
                        "Tomcat berhasil dijalankan, "
                        "tetapi debug port tidak tersedia.\n\n"
                        f"localhost:{debug_port}"
                    ),
                )

                return

            self.log(
                "✅ JDWP ready: "
                f"localhost:{debug_port}"
            )

            if not self.open_vscode(
                workspace
            ):
                self.show_error_async(
                    "Debug",
                    "VS Code tidak ditemukan.",
                )

                return

            self.log(
                "✅ VS Code workspace opened."
            )

            self.log(
                "ℹ️ Select 'Attach Tomcat' in VS Code "
                "and press F5 to start debugging."
            )

        except Exception as exc:
            self.log(
                f"❌ Debug startup error: {exc}"
            )

            self.show_error_async(
                "Debug",
                str(exc),
            )

    def wait_for_debug_port(
        self,
        host,
        port,
        timeout,
    ):
        deadline = (
            time.time()
            + timeout
        )

        while time.time() < deadline:
            if not self.is_tomcat_running():
                self.log(
                    "[DEBUG] Tomcat JVM stopped "
                    "before JDWP became ready."
                )

                return False

            try:
                with socket.create_connection(
                    (
                        host,
                        port,
                    ),
                    timeout=0.5,
                ):
                    return True

            except (
                ConnectionRefusedError,
                OSError,
            ):
                time.sleep(
                    self.DEBUG_POLL_INTERVAL
                )

        return False

    # ==================================================================
    # VS Code
    # ==================================================================

    def find_vscode(self):
        configured = self.config.get(
            "vscode_path"
        )

        if (
            configured
            and os.path.isfile(configured)
        ):
            return configured

        candidates = [
            os.path.expandvars(
                r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"
            ),
            os.path.expandvars(
                r"%ProgramFiles%\Microsoft VS Code\Code.exe"
            ),
            os.path.expandvars(
                r"%ProgramFiles(x86)%\Microsoft VS Code\Code.exe"
            ),
        ]

        for path in candidates:
            if os.path.isfile(path):
                self.config.set(
                    "vscode_path",
                    path,
                )

                return path

        code_cmd = shutil.which(
            "code"
        )

        if code_cmd:
            return code_cmd

        return None

    def open_vscode(
        self,
        workspace,
    ):
        vscode = self.find_vscode()

        if not vscode:
            self.log(
                "❌ VS Code executable not found."
            )

            return False

        self.log(
            f"[VS CODE] {vscode}"
        )

        try:
            subprocess.Popen(
                [
                    vscode,
                    "--reuse-window",
                    workspace,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(
                    subprocess,
                    "CREATE_NEW_PROCESS_GROUP",
                    0,
                ),
            )

            return True

        except Exception as exc:
            self.log(
                "❌ Failed to open VS Code: "
                f"{exc}"
            )

            return False

    # ==================================================================
    # Process Detection
    # ==================================================================

    def _get_windows_processes(self):
        command = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            (
                "Get-CimInstance Win32_Process | "
                "Select-Object ProcessId,ParentProcessId,"
                "Name,CommandLine | "
                "ConvertTo-Json -Compress"
            ),
        ]

        try:
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                self.log(
                    "[WARN] Failed to query "
                    "Windows processes."
                )

                return []

            output = (
                result.stdout.strip()
            )

            if not output:
                return []

            data = json.loads(
                output
            )

            if isinstance(
                data,
                dict,
            ):
                data = [data]

            processes = []

            for item in data:
                try:
                    processes.append(
                        {
                            "pid": int(
                                item.get(
                                    "ProcessId"
                                )
                            ),
                            "parent_pid": int(
                                item.get(
                                    "ParentProcessId"
                                )
                            ),
                            "name": (
                                item.get(
                                    "Name"
                                )
                                or ""
                            ),
                            "command_line": (
                                item.get(
                                    "CommandLine"
                                )
                                or ""
                            ),
                        }
                    )

                except (
                    TypeError,
                    ValueError,
                ):
                    continue

            return processes

        except Exception as exc:
            self.log(
                "[WARN] Process query failed: "
                f"{exc}"
            )

            return []

    def _find_tomcat_pid(
        self,
        home,
        base,
        launcher_pid=None,
    ):
        home = os.path.normcase(
            os.path.abspath(home)
        )

        base = os.path.normcase(
            os.path.abspath(base)
        )


        processes = (
            self._get_windows_processes()
        )

        if not processes:
            return None

        by_pid = {
            process["pid"]: process
            for process in processes
        }

        def is_descendant(
            pid,
            ancestor_pid,
        ):
            visited = set()

            current = pid

            while (
                current
                and current not in visited
            ):
                visited.add(
                    current
                )

                process = by_pid.get(
                    current
                )

                if not process:
                    return False

                parent_pid = process[
                    "parent_pid"
                ]

                if parent_pid == ancestor_pid:
                    return True

                current = parent_pid

            return False

        candidates = []

        for process in processes:
            name = (
                process["name"]
                .lower()
            )

            command_line = (
                process["command_line"]
                or ""
            ).lower()

            if name not in {
                "java.exe",
                "javaw.exe",
            }:
                continue

            if (
                "org.apache.catalina.startup.bootstrap"
                not in command_line
            ):
                continue

            if (
                "-dcatalina.home="
                not in command_line
            ):
                continue

            if (
                "-dcatalina.base="
                not in command_line
            ):
                continue

            normalized_command = (
                command_line
                .replace(
                    '"',
                    "",
                )
                .replace(
                    "\\",
                    "/",
                )
            )

            normalized_home = (
                home
                .replace(
                    "\\",
                    "/",
                )
            )

            normalized_base = (
                base
                .replace(
                    "\\",
                    "/",
                )
            )

            if (
                normalized_home
                not in normalized_command
                or normalized_base
                not in normalized_command
            ):
                continue

            if (
                launcher_pid
                and is_descendant(
                    process["pid"],
                    launcher_pid,
                )
            ):
                return process["pid"]

            candidates.append(
                process["pid"]
            )

        if candidates:
            return candidates[0]

        return None

    def is_tomcat_running(self):
        home = self.ent_home.get().strip()
        base = self.ent_base.get().strip()

        if not home or not base:
            return False

        with self.process_lock:
            current_pid = (
                self.tomcat_pid
            )

        if current_pid:
            processes = (
                self._get_windows_processes()
            )

            for process in processes:
                if (
                    process["pid"]
                    == current_pid
                ):
                    name = (
                        process["name"]
                        .lower()
                    )

                    if name in {
                        "java.exe",
                        "javaw.exe",
                    }:
                        return True

            with self.process_lock:
                self.tomcat_pid = None

        pid = self._find_tomcat_pid(
            home,
            base,
        )

        if pid:
            with self.process_lock:
                self.tomcat_pid = pid
                self.tomcat_home = home

            return True

        return False

    # ==================================================================
    # Launcher Output
    # ==================================================================

    def _read_launcher_output(
        self,
        launcher,
    ):
        try:
            for line in launcher.stdout:
                line = line.rstrip()

                if line:
                    self.log(line)

            return_code = launcher.wait()

            if self.is_tomcat_running():
                with self.process_lock:
                    pid = self.tomcat_pid

                self.log(
                    "[PROCESS] Debug launcher exited "
                    f"(exit={return_code}), "
                    f"Tomcat JVM PID={pid} "
                    "still running."
                )

            else:
                self.log(
                    "🛑 Tomcat stopped "
                    f"(exit={return_code})"
                )

        except Exception as exc:
            self.log(
                "❌ Launcher output error: "
                f"{exc}"
            )

        finally:
            with self.process_lock:
                if (
                    self.launcher_proc
                    is launcher
                ):
                    self.launcher_proc = None

    # ==================================================================
    # Async Message Boxes
    # ==================================================================

    def show_error_async(
        self,
        title,
        message,
    ):
        self.after(
            0,
            lambda: messagebox.showerror(
                title,
                message,
            ),
        )