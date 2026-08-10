import json
import os
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import threading
import shutil
from path import app_dir, tools_dir

# Nama file untuk menyimpan konfigurasi terakhir user
# CONFIG_FILE = "build_manager_settings.json"
CONFIG_FILE = str(app_dir() / "build_manager_settings.json")

class BuildManagerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("SM Build Manager V2.2 (Dependency Check)")
        self.root.geometry("900x750")
        
        self.projects = []
        self.vars = []
        
        # --- UI SETUP ---
        self.setup_ui()
        
        # --- LOAD SAVED CONFIG / AUTO DETECT ---
        self.load_initial_settings()

    def setup_ui(self):
        # 1. Configuration Frame (Top)
        frame_config = tk.LabelFrame(self.root, text="Configuration & Health Check", padx=10, pady=10)
        frame_config.pack(fill=tk.X, padx=10, pady=5)

        # Row 1: Workspace Selection
        tk.Label(frame_config, text="Workspace File (.code-workspace):").grid(row=0, column=0, sticky="w")
        self.entry_workspace = tk.Entry(frame_config, width=70)
        self.entry_workspace.grid(row=0, column=1, padx=5)
        btn_browse_ws = tk.Button(frame_config, text="Browse...", command=self.browse_workspace)
        btn_browse_ws.grid(row=0, column=2)

        # Row 2: Java Home Selection
        tk.Label(frame_config, text="Java 8 Home Path:").grid(row=1, column=0, sticky="w")
        self.entry_java = tk.Entry(frame_config, width=70)
        self.entry_java.grid(row=1, column=1, padx=5)
        btn_browse_java = tk.Button(frame_config, text="Browse...", command=self.browse_java)
        btn_browse_java.grid(row=1, column=2)

        # Row 3: Action Buttons
        frame_actions = tk.Frame(frame_config)
        frame_actions.grid(row=2, column=1, sticky="w", pady=10)
        
        btn_load = tk.Button(frame_actions, text="🔄 Reload Projects", command=self.load_projects_from_workspace, bg="#f0f0f0")
        btn_load.pack(side=tk.LEFT, padx=(0, 10))
        
        btn_check = tk.Button(frame_actions, text="🩺 Check Dependencies", command=self.run_dependency_check_ui, bg="#e3f2fd")
        btn_check.pack(side=tk.LEFT)

        # 2. Project List (Middle)
        lbl_list = tk.Label(self.root, text="Select Projects to Build:", font=("Arial", 11, "bold"))
        lbl_list.pack(pady=(5, 0))

        frame_list = tk.Frame(self.root, bd=1, relief="sunken")
        frame_list.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        canvas = tk.Canvas(frame_list, bg="white")
        scrollbar = ttk.Scrollbar(frame_list, orient="vertical", command=canvas.yview)
        self.scrollable_frame = tk.Frame(canvas, bg="white")

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 3. Action Buttons (Bottom)
        frame_btn = tk.Frame(self.root)
        frame_btn.pack(pady=10)
        
        tk.Button(frame_btn, text="Select All", command=self.select_all).pack(side=tk.LEFT, padx=5)
        tk.Button(frame_btn, text="Clear All", command=self.clear_all).pack(side=tk.LEFT, padx=5)
        
        self.btn_build = tk.Button(frame_btn, text="BUILD SELECTED 🚀", bg="green", fg="white", font=("Arial", 10, "bold"), command=self.start_build_thread)
        self.btn_build.pack(side=tk.LEFT, padx=20)

        # 4. Log Output
        self.log_area = scrolledtext.ScrolledText(self.root, height=12, state='disabled', bg="black", fg="#00FF00", font=("Consolas", 9))
        self.log_area.pack(fill=tk.X, padx=10, pady=(0, 10))

    def get_mvn_command(self):
        """Mencari Maven: Prioritas Portable -> System"""
        # 1. Cek Portable Maven di folder 'tools' sebelah script
        
        # 1. Cek Portable Maven di folder 'tools' sebelah EXE
        tdir = tools_dir()
        if tdir.exists():
            for folder in os.listdir(str(tdir)):
                if folder.startswith("apache-maven"):
                    mvn_bin = os.path.join(str(tdir), folder, "bin", "mvn.cmd")
                    if os.path.exists(mvn_bin):
                        return mvn_bin, "Portable"
        
        # 2. Fallback ke System Maven
        if shutil.which("mvn"):
            return "mvn", "System"
            
        return None, None

    # --- HEALTH CHECK & DETECTION ---

    def detect_java8_path(self):
        """Mencoba menebak lokasi Java 8"""
        user_home = os.path.expanduser("~")
        specific_path = os.path.join(user_home, "Documents", "SM_TOOLS", "java", "jdk8u452-b09")
        if os.path.exists(specific_path): return specific_path

        env_java = os.environ.get("JAVA_HOME", "")
        if env_java and ("1.8" in env_java or "jdk8" in env_java.lower()): return env_java

        common_roots = [r"C:\Program Files\Java", r"C:\Program Files (x86)\Java"]
        for root in common_roots:
            if os.path.exists(root):
                try:
                    for folder in os.listdir(root):
                        if "jdk1.8" in folder or "jdk-8" in folder:
                            return os.path.join(root, folder)
                except: pass
        return "" 

    def check_prerequisites(self):
        """Memeriksa apakah Maven dan Java valid"""
        errors = []
        
        # 1. Cek Maven (mvn)
        # --- UPDATE BAGIAN INI ---
        mvn_cmd, source = self.get_mvn_command()
        
        if not mvn_cmd:
            errors.append("❌ Maven not found! (Neither in /tools nor in System PATH)")
        else:
            self.log(f"[CHECK] Using {source} Maven: {mvn_cmd}")

        # 2. Cek Java Path (dari Input UI)
        java_home = self.entry_java.get()
        if not java_home or not os.path.exists(java_home):
            errors.append("❌ Java Path is empty or does not exist.")
        else:
            # Validasi isi folder JDK
            java_exe = os.path.join(java_home, "bin", "java.exe")
            javac_exe = os.path.join(java_home, "bin", "javac.exe")
            
            if not os.path.exists(java_exe):
                errors.append(f"❌ java.exe not found in {java_exe}")
            elif not os.path.exists(javac_exe):
                self.log(f"[WARN] javac.exe not found. Is this a JRE? JDK is recommended for Maven.")
            else:
                self.log(f"[CHECK] Java 8 binaries verified at: {java_home}")

        return errors

    def run_dependency_check_ui(self):
        self.log("\n--- Running Dependency Check ---")
        errors = self.check_prerequisites()
        if errors:
            for err in errors:
                self.log(err)
            messagebox.showerror("Dependency Missing", "\n".join(errors))
        else:
            self.log("✅ All System Dependencies are OK!")
            messagebox.showinfo("System Check", "All dependencies are ready for build!")

    # --- SETTINGS LOADING ---

    def load_initial_settings(self):
        ws_path = ""
        java_path = ""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                    ws_path = data.get("workspace_path", "")
                    java_path = data.get("java_home", "")
            except Exception: pass

        if not java_path:
            java_path = self.detect_java8_path()
            if java_path: self.log(f"[AUTO] Java 8 detected: {java_path}")

        self.entry_workspace.insert(0, ws_path)
        self.entry_java.insert(0, java_path)

        if ws_path and os.path.exists(ws_path):
            self.load_projects_from_workspace()

    # --- UI ACTIONS ---

    def browse_workspace(self):
        filename = filedialog.askopenfilename(filetypes=[("VS Code Workspace", "*.code-workspace"), ("All Files", "*.*")])
        if filename:
            self.entry_workspace.delete(0, tk.END)
            self.entry_workspace.insert(0, filename)
            self.save_settings()
            self.load_projects_from_workspace()

    def browse_java(self):
        directory = filedialog.askdirectory()
        if directory:
            self.entry_java.delete(0, tk.END)
            self.entry_java.insert(0, directory)
            self.save_settings()

    def save_settings(self):
        data = {"workspace_path": self.entry_workspace.get(), "java_home": self.entry_java.get()}
        try:
            with open(CONFIG_FILE, 'w') as f: json.dump(data, f)
        except: pass

    # --- BUILD LOGIC ---

    def load_projects_from_workspace(self):
        workspace_file = self.entry_workspace.get()
        for widget in self.scrollable_frame.winfo_children(): widget.destroy()
        self.projects = []
        self.vars = []

        if not workspace_file or not os.path.exists(workspace_file):
            self.log("[INFO] Select a valid workspace file.")
            return

        try:
            with open(workspace_file, 'r') as f:
                clean_lines = [line for line in f.read().splitlines() if not line.strip().startswith("//")]
                data = json.loads("\n".join(clean_lines))
                
                folders = data.get("folders", [])
                priority = ["common-lib", "bom", "api", "web"]
                sorted_folders = sorted(folders, key=lambda x: next((i for i, k in enumerate(priority) if k in x['path']), 99))
                ws_dir = os.path.dirname(workspace_file)

                for item in sorted_folders:
                    path = item.get("path")
                    full_path = os.path.normpath(os.path.join(ws_dir, path)) if not os.path.isabs(path) else os.path.normpath(path)
                    
                    var = tk.IntVar()
                    tk.Checkbutton(self.scrollable_frame, text=full_path, variable=var, anchor='w', bg="white").pack(fill='x', padx=5, pady=2)
                    self.projects.append(full_path)
                    self.vars.append(var)
                self.log(f"[INFO] Loaded {len(self.projects)} projects.")
                self.save_settings()
        except Exception as e:
            self.log(f"[ERROR] Load failed: {e}")

    def select_all(self): 
        for var in self.vars: var.set(1)
    def clear_all(self): 
        for var in self.vars: var.set(0)

    def log(self, message):
        self.log_area.config(state='normal')
        self.log_area.insert(tk.END, message + "\n")
        self.log_area.see(tk.END)
        self.log_area.config(state='disabled')

    def start_build_thread(self):
        # PRE-BUILD CHECK
        errors = self.check_prerequisites()
        if errors:
            messagebox.showerror("Pre-Build Check Failed", "\n".join(errors))
            return

        self.btn_build.config(state="disabled", text="Building... ⏳")
        threading.Thread(target=self.run_builds).start()

    def run_builds(self):
        java_home = self.entry_java.get()
        selected_indices = [i for i, var in enumerate(self.vars) if var.get() == 1]
        
        if not selected_indices:
            self.btn_build.config(state="normal", text="BUILD SELECTED 🚀")
            return

        my_env = os.environ.copy()
        my_env["JAVA_HOME"] = java_home
        my_env["PATH"] = f"{java_home}\\bin;" + my_env["PATH"]
        comspec = os.environ.get("ComSpec", r"C:\Windows\System32\cmd.exe")

        mvn_cmd_path, _ = self.get_mvn_command()
        if not mvn_cmd_path:
            messagebox.showerror("Error", "Maven not found!")
            return
        
        base_cmd = [mvn_cmd_path, "clean", "install", "-Dmaven.javadoc.skip=true", "-DskipTests", "-DPROJECT_ENV=LOCAL"]

        self.log("\n" + "="*60)
        self.log(f"STARTING BUILD SEQUENCE")
        self.log("="*60)

        for idx in selected_indices:
            project_path = self.projects[idx]
            folder_name = os.path.basename(project_path)
            
            self.log(f"\n>>> Building: {folder_name} ...")

            # --- Pre-flight checks (avoid WinError 2 mystery) ---
            if not os.path.isdir(project_path):
                self.log(f"❌ [CRITICAL] Project folder not found: {project_path}")
                self.btn_build.config(state="normal", text="BUILD SELECTED 🚀")
                return

            if isinstance(base_cmd[0], str) and base_cmd[0].lower().endswith(".cmd") and not os.path.exists(base_cmd[0]):
                self.log(f"❌ [CRITICAL] Maven file not found: {base_cmd[0]}")
                self.log("   └── Put apache-maven-* inside ./tools next to the EXE.")
                self.btn_build.config(state="normal", text="BUILD SELECTED 🚀")
                return
            
            if not os.path.exists(os.path.join(project_path, "pom.xml")):
                self.log(f"[SKIP] No pom.xml")
                continue

            try:
               # If Maven is a .cmd file, run via absolute cmd.exe /c (more reliable than "cmd" on PATH)
                if isinstance(base_cmd[0], str) and base_cmd[0].lower().endswith((".cmd", ".bat")):
                    cmdline = [comspec, "/c"] + base_cmd
                else:
                    cmdline = base_cmd

                self.log(f"[DEBUG] cmd={cmdline[0]} | cwd={project_path}")

                process = subprocess.Popen(
                   cmdline,
                    cwd=project_path, 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.STDOUT,
                    env=my_env, 
                    universal_newlines=True
                )
                
                for line in process.stdout:
                    l = line.strip()
                    if any(x in l for x in ["[INFO]", "[ERROR]", "[WARNING]", "BUILD"]): self.log(l)
                
                process.wait()

                if process.returncode == 0:
                    self.log(f"✅ [SUCCESS] {folder_name}")
                    if "dfms-web" in folder_name: self.copy_ws_properties(project_path)
                else:
                    self.log(f"❌ [FAILURE] {folder_name}")
                    messagebox.showerror("Build Failed", f"Failed to build {folder_name}")
                    self.btn_build.config(state="normal", text="BUILD SELECTED 🚀")
                    return 
            except FileNotFoundError as e:
                self.log(f"❌ [CRITICAL] FileNotFoundError: {e}")
                self.log(f"[DEBUG] cmdline={cmdline}")
                self.log(f"[DEBUG] cwd={project_path}")
                self.btn_build.config(state="normal", text="BUILD SELECTED 🚀")
                return
            except Exception as e:
                self.log(f"[CRITICAL ERROR] {e}")
                self.btn_build.config(state="normal", text="BUILD SELECTED 🚀")
                return

        self.log("\n" + "="*60)
        self.log("🎉 ALL DONE!")
        self.log("="*60)
        messagebox.showinfo("Done", "Build Completed!")
        self.btn_build.config(state="normal", text="BUILD SELECTED 🚀")

    def copy_ws_properties(self, web_path):
        src = os.path.join(web_path, "src", "main", "webapp", "WEB-INF", "ws.properties")
        dst = os.path.join(web_path, "target", "dfms-web", "WEB-INF") 
        if os.path.exists(src):
            try:
                if not os.path.exists(dst): os.makedirs(dst)
                shutil.copy(src, dst)
                self.log(f"   └── [PATCH] ws.properties copied.")
            except Exception as e: self.log(f"   └── [ERROR] Copy failed: {e}")
        else: self.log(f"   └── [WARN] ws.properties missing in src.")

if __name__ == "__main__":
    root = tk.Tk()
    app = BuildManagerApp(root)
    root.mainloop()