import tkinter as tk
from tkinter import messagebox, ttk

from config import ConfigManager
from panel_build import BuildPanel
from panel_tomcat import TomcatPanel


class MainApp:
    """
    Main application window.

    UI intentionally hides the Notebook tabs.
    The Notebook is still kept internally because the existing
    TomcatPanel architecture already depends on it.

    User-facing Tomcat selection is handled through a Combobox.
    """

    def __init__(self, root):
        self.root = root

        self.root.title(
            "SM DevOps Dashboard (Multi-Deployment Tomcat)"
        )

        self.root.geometry("1200x800")

        # Prevent the UI from becoming too small for the fixed
        # Tomcat lifecycle controls.
        self.root.minsize(
            950,
            650,
        )

        self.config = ConfigManager()
        self.tomcat_counter = 1

        # --------------------------------------------------------------
        # ttk styling
        # --------------------------------------------------------------
        self.setup_styles()

        # --------------------------------------------------------------
        # Main split
        # --------------------------------------------------------------
        self.create_main_layout()

        # --------------------------------------------------------------
        # Global log
        # --------------------------------------------------------------
        self.create_log_panel()

        # --------------------------------------------------------------
        # Tomcat instances
        # --------------------------------------------------------------
        self.create_tomcat_container()

        # Restore saved Tomcat instances.
        self.restore_tabs()

    # ------------------------------------------------------------------
    # Styles
    # ------------------------------------------------------------------

    def setup_styles(self):
        """
        Hide the visual Notebook tabs.

        Important:
            The Notebook itself is NOT removed.

        Existing code can still use:
            self.tabs.add(...)
            self.tabs.select(...)
            self.tabs.tabs()
            self.tabs.nametowidget(...)

        Only the tab bar is hidden from the user.
        """
        style = ttk.Style(self.root)

        try:
            style.layout(
                "Hidden.TNotebook",
                [
                    (
                        "Notebook.client",
                        {
                            "sticky": "nswe"
                        },
                    )
                ],
            )
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Global log
    # ------------------------------------------------------------------

    def create_log_panel(self):
        self.txt_log = tk.Text(
            self.log_frame,
            state="disabled",
            bg="#1e1e1e",
            fg="#00FF00",
            font=("Consolas", 9),
            wrap="none",
        )

        self.log_scroll_y = ttk.Scrollbar(
            self.log_frame,
            orient="vertical",
            command=self.txt_log.yview,
        )

        self.log_scroll_x = ttk.Scrollbar(
            self.log_frame,
            orient="horizontal",
            command=self.txt_log.xview,
        )

        self.txt_log.configure(
            yscrollcommand=self.log_scroll_y.set,
            xscrollcommand=self.log_scroll_x.set,
        )

        # Text area
        self.txt_log.grid(
            row=0,
            column=0,
            sticky="nsew",
        )

        # Vertical scrollbar
        self.log_scroll_y.grid(
            row=0,
            column=1,
            sticky="ns",
        )

        # Horizontal scrollbar
        self.log_scroll_x.grid(
            row=1,
            column=0,
            sticky="ew",
        )

    # ------------------------------------------------------------------
    # Main layout
    # ------------------------------------------------------------------

    def create_main_layout(self):
        self.paned = tk.PanedWindow(
            self.root,
            orient=tk.HORIZONTAL,
            sashrelief=tk.RAISED,
            sashwidth=5,
        )

        self.paned.pack(
            fill=tk.BOTH,
            expand=True,
            padx=5,
            pady=5,
        )

        # --------------------------------------------------------------
        # Left: Maven Build
        # --------------------------------------------------------------
        self.left_panel = BuildPanel(
            self.paned,
            self.config,
            self.log,
        )

        self.paned.add(
            self.left_panel,
            minsize=360,
        )

        # --------------------------------------------------------------
        # Center: Tomcat
        # --------------------------------------------------------------
        self.right_container = tk.Frame(self.paned)

        self.paned.add(
            self.right_container,
            minsize=480,
        )

        # --------------------------------------------------------------
        # Right: System Logs
        # --------------------------------------------------------------
        self.log_frame = tk.LabelFrame(
            self.paned,
            text="System Logs",
            padx=5,
            pady=5,
        )

        self.log_frame.grid_rowconfigure(
            0,
            weight=1,
        )

        self.log_frame.grid_columnconfigure(
            0,
            weight=1,
        )

        self.paned.add(
            self.log_frame,
            minsize=300,
            stretch="always",
        )

    # ------------------------------------------------------------------
    # Tomcat container
    # ------------------------------------------------------------------

    def create_tomcat_container(self):
        """
        Create the user-facing Tomcat selector and the hidden Notebook.

        Visual UI:

            Tomcat Instance: [ email-api ▼ ]     [+ Add Tomcat]

        Internal UI:

            ttk.Notebook
                ├── TomcatPanel(email-api)
                └── TomcatPanel(Tomcat-1)
        """

        # --------------------------------------------------------------
        # Header
        # --------------------------------------------------------------
        header = tk.Frame(
            self.right_container
        )

        header.pack(
            fill=tk.X,
            pady=(0, 5),
        )

        tk.Label(
            header,
            text="Tomcat Instance:",
            font=("Arial", 10, "bold"),
        ).pack(
            side=tk.LEFT,
            padx=(0, 5),
        )

        self.instance_selector = ttk.Combobox(
            header,
            state="readonly",
            width=30,
        )

        self.instance_selector.pack(
            side=tk.LEFT,
            fill=tk.X,
            expand=True,
        )

        self.instance_selector.bind(
            "<<ComboboxSelected>>",
            self.on_instance_selected,
        )

        self.btn_remove_tomcat = tk.Button(
            header,
            text="🗑 Remove",
            bg="#ffcccc",
            fg="#b00000",
            command=self.remove_current_tab,
        )

        self.btn_remove_tomcat.pack(
            side=tk.RIGHT,
            padx=(5, 0),
        )

        self.btn_add_tomcat = tk.Button(
            header,
            text="➕ Add Tomcat",
            bg="#dddddd",
            command=self.add_new_tab_btn,
        )

        self.btn_add_tomcat.pack(
            side=tk.RIGHT,
            padx=(5, 0),
        )

        # --------------------------------------------------------------
        # Hidden Notebook
        # --------------------------------------------------------------
        self.tabs = ttk.Notebook(
            self.right_container,
            style="Hidden.TNotebook",
        )

        self.tabs.pack(
            fill=tk.BOTH,
            expand=True,
        )

    # ------------------------------------------------------------------
    # Tomcat instances
    # ------------------------------------------------------------------

    def restore_tabs(self):
        saved_tabs = self.config.get_active_tabs()

        if saved_tabs:
            for tab_name in saved_tabs:
                self.create_tomcat_tab(
                    tab_name
                )
        else:
            self.create_tomcat_tab(
                "Tomcat-1"
            )

        self.refresh_instance_selector()

        if self.tabs.tabs():
            self.select_instance_by_index(0)

    def create_tomcat_tab(self, name):
        panel = TomcatPanel(
            self.tabs,
            self.config,
            self.log,
            instance_name=name,
        )

        panel.set_rename_callback(
            self.update_tab_list_config
        )

        self.tabs.add(
            panel,
            text=name,
        )

        if name.startswith("Tomcat-"):
            try:
                number = int(
                    name.split("-", 1)[1]
                )

                self.tomcat_counter = max(
                    self.tomcat_counter,
                    number + 1,
                )

            except (ValueError, IndexError):
                pass

    def add_new_tab_btn(self):
        name = (
            f"Tomcat-{self.tomcat_counter}"
        )

        self.create_tomcat_tab(
            name
        )

        self.update_tab_list_config()

        self.refresh_instance_selector()

        self.instance_selector.set(
            name
        )

        self.select_instance_by_name(
            name
        )

    def remove_current_tab(self):
        """
        Remove the currently selected Tomcat instance.

        At least one Tomcat instance must remain.
        """

        tab_ids = self.tabs.tabs()

        # --------------------------------------------------------------
        # Never allow the application to have zero Tomcat instances.
        # --------------------------------------------------------------
        if len(tab_ids) <= 1:
            self.log(
                "[WARN] Cannot remove the last Tomcat instance."
            )

            return

        current_tab = self.tabs.select()

        if not current_tab:
            return

        panel = self.tabs.nametowidget(
            current_tab
        )

        instance_name = getattr(
            panel,
            "instance_name",
            "Tomcat",
        )

        # --------------------------------------------------------------
        # Confirm removal.
        # --------------------------------------------------------------

        confirmed = messagebox.askyesno(
            "Remove Tomcat",
            (
                f"Remove Tomcat instance '{instance_name}'?\n\n"
                "Deployment configuration for this instance "
                "will also be removed from the application configuration."
            ),
        )

        if not confirmed:
            return

        # --------------------------------------------------------------
        # Prevent removing a running Tomcat.
        # --------------------------------------------------------------
        try:
            if panel.is_tomcat_running():
                messagebox.showwarning(
                    "Remove Tomcat",
                    (
                        f"{instance_name} masih berjalan.\n\n"
                        "Stop Tomcat terlebih dahulu sebelum "
                        "menghapus instance."
                    ),
                )

                return

        except Exception as exc:
            self.log(
                f"[WARN] Could not determine Tomcat state: {exc}"
            )

        # --------------------------------------------------------------
        # Remove workspace debug configuration generated by this app.
        # --------------------------------------------------------------
        try:
            self.config.remove_workspace_debug_config(
                instance_name
            )

        except Exception as exc:
            self.log(
                "[WARN] Failed to remove VS Code debug "
                f"configuration: {exc}"
            )

        # --------------------------------------------------------------
        # Remove instance from deploy_map.
        # --------------------------------------------------------------
        deploy_map = self.config.data.get(
            "deploy_map",
            {},
        )

        if isinstance(
            deploy_map,
            dict,
        ):
            deploy_map.pop(
                instance_name,
                None,
            )

        # --------------------------------------------------------------
        # Remove from active tabs.
        # --------------------------------------------------------------
        active_tabs = self.config.get(
            "active_tabs",
            [],
        )

        active_tabs = [
            name
            for name in active_tabs
            if name != instance_name
        ]

        self.config.save_active_tabs(
            active_tabs
        )

        # --------------------------------------------------------------
        # Determine next tab before destroying current one.
        # --------------------------------------------------------------
        current_index = self.tabs.index(
            current_tab
        )

        remaining_tabs = [
            tab_id
            for tab_id in tab_ids
            if tab_id != current_tab
        ]

        # --------------------------------------------------------------
        # Destroy current panel.
        # --------------------------------------------------------------
        self.tabs.forget(
            current_tab
        )

        panel.destroy()

        self.config.save()

        # --------------------------------------------------------------
        # Select another Tomcat.
        # --------------------------------------------------------------
        if remaining_tabs:
            new_index = min(
                current_index,
                len(remaining_tabs) - 1,
            )

            self.select_instance_by_index(
                new_index
            )

        self.refresh_instance_selector()

        self.log(
            f"🗑 Removed Tomcat instance: "
            f"{instance_name}"
        )

    # ------------------------------------------------------------------
    # Instance selector
    # ------------------------------------------------------------------

    def refresh_instance_selector(self):
        names = []

        for tab_id in self.tabs.tabs():
            widget = self.tabs.nametowidget(
                tab_id
            )

            if hasattr(
                widget,
                "instance_name",
            ):
                names.append(
                    widget.instance_name
                )

        self.instance_selector["values"] = names

        if not names:
            self.instance_selector.set("")
            return

        current_name = (
            self.instance_selector.get()
        )

        if current_name in names:
            return

        self.instance_selector.set(
            names[0]
        )

    def on_instance_selected(self, _event=None):
        name = (
            self.instance_selector.get()
        )

        if not name:
            return

        self.select_instance_by_name(
            name
        )

    def select_instance_by_name(self, name):
        for index, tab_id in enumerate(
            self.tabs.tabs()
        ):
            widget = self.tabs.nametowidget(
                tab_id
            )

            if getattr(
                widget,
                "instance_name",
                None,
            ) == name:
                self.tabs.select(
                    index
                )

                self.instance_selector.set(
                    name
                )

                return

    def select_instance_by_index(self, index):
        tab_ids = self.tabs.tabs()

        if not tab_ids:
            return

        if index < 0:
            index = 0

        if index >= len(tab_ids):
            index = len(tab_ids) - 1

        tab_id = tab_ids[index]

        widget = self.tabs.nametowidget(
            tab_id
        )

        self.tabs.select(
            index
        )

        name = getattr(
            widget,
            "instance_name",
            "",
        )

        if name:
            self.instance_selector.set(
                name
            )

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def update_tab_list_config(self):
        current_tabs = []

        for tab_id in self.tabs.tabs():
            widget = self.tabs.nametowidget(
                tab_id
            )

            if hasattr(
                widget,
                "instance_name",
            ):
                current_tabs.append(
                    widget.instance_name
                )

        self.config.save_active_tabs(
            current_tabs
        )

        self.refresh_instance_selector()

    # ------------------------------------------------------------------
    # Log
    # ------------------------------------------------------------------

    def log(self, msg):
        """
        Thread-safe application log.

        Tomcat and Maven operations run in worker threads,
        therefore Tkinter widgets should not be modified directly
        from those threads.
        """

        def write_log():
            try:
                self.txt_log.config(
                    state="normal"
                )

                self.txt_log.insert(
                    tk.END,
                    str(msg) + "\n",
                )

                self.txt_log.see(
                    tk.END
                )

                self.txt_log.config(
                    state="disabled"
                )

            except tk.TclError:
                pass

        try:
            self.root.after(
                0,
                write_log,
            )
        except tk.TclError:
            pass


if __name__ == "__main__":
    root = tk.Tk()

    app = MainApp(
        root
    )

    root.mainloop()