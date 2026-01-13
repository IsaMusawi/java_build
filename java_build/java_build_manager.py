import json
import os
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import threading

# Nama file untuk menyimpan konfigurasi terakhir user
CONFIG_FILE = "build_manager_settings.json"

class BuildManagerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("SM Build Manager V2.1 (Auto-Detect)")
        self.root.geometry("900x700")
        
        self.projects = []
        self.vars = []
        
        # --- UI SETUP ---
        self.setup_ui()
        
        # --- LOAD SAVED CONFIG / AUTO DETECT ---
        self.load_initial_settings()

    def setup_ui(self):
        # 1. Configuration Frame (Top)
        frame_config = tk.LabelFrame(self.root, text="Configuration", padx=10, pady=10)
        frame_config.pack(fill=tk.X, padx=10, pady=5)

        # Row 1: Workspace Selection
        tk.Label(frame_config, text="Workspace File (.code-workspace):").grid(row=0, column=0, sticky="w")
        self.entry_workspace = tk.Entry(frame_config, width=80)
        self.entry_workspace.grid(row=0, column=1, padx=5)
        btn_browse_ws = tk.Button(frame_config, text="Browse...", command=self.browse_workspace)
        btn_browse_ws.grid(row=0, column=2)

        # Row 2: Java Home Selection
        tk.Label(frame_config, text="Java 8 Home Path:").grid(row=1, column=0, sticky="w")
        self.entry_java = tk.Entry(frame_config, width=80)
        self.entry_java.grid(row=1, column=1, padx=5)
        btn_browse_java = tk.Button(frame_config, text="Browse...", command=self.browse_java)
        btn_browse_java.grid(row=1, column=2)

        # Row 3: Reload Button
        btn_load = tk.Button(frame_config, text="🔄 Reload Projects", command=self.load_projects_from_workspace, bg="#f0f0f0")
        btn_load.grid(row=2, column=1, sticky="e", pady=5)

        # 2. Project List (Middle)
        lbl_list = tk.Label(self.root, text="Select Projects to Build:", font=("Arial", 11, "bold"))
        lbl_list.pack(pady=(10, 0))

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

    # --- INTELLIGENT DETECTION ---

    def detect_java8_path(self):
        """Mencoba menebak lokasi Java 8 secara otomatis"""
        
        # 1. Cek Lokasi Spesifik User (Berdasarkan history Anda)
        user_home = os.path.expanduser("~")
        specific_path = os.path.join(user_home, "Documents", "SM_TOOLS", "java", "jdk8u452-b09")
        if os.path.exists(specific_path):
            return specific_path

        # 2. Cek Environment Variable 'JAVA_HOME'
        env_java = os.environ.get("JAVA_HOME", "")
        if env_java and ("1.8" in env_java or "jdk8" in env_java.lower()):
            return env_java

        # 3. Cek folder standar Windows
        common_roots = [r"C:\Program Files\Java", r"C:\Program Files (x86)\Java"]
        for root in common_roots:
            if os.path.exists(root):
                try:
                    for folder in os.listdir(root):
                        # Cari folder yang mengandung 'jdk1.8' atau 'jdk-8'
                        if "jdk1.8" in folder or "jdk-8" in folder:
                            return os.path.join(root, folder)
                except: pass
        
        return "" # Menyerah, biarkan kosong

    def load_initial_settings(self):
        """Load dari file JSON, jika kosong gunakan auto-detect"""
        ws_path = ""
        java_path = ""

        # Coba baca file config
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                    ws_path = data.get("workspace_path", "")
                    java_path = data.get("java_home", "")
            except Exception:
                pass

        # Jika Java Path kosong di config, jalankan Auto-Detect
        if not java_path:
            java_path = self.detect_java8_path()
            if java_path:
                self.log(f"[AUTO] Java 8 detected at: {java_path}")

        # Masukkan ke UI
        self.entry_workspace.insert(0, ws_path)
        self.entry_java.insert(0, java_path)

        # Trigger load project jika workspace ada
        if ws_path and os.path.exists(ws_path):
            self.load_projects_from_workspace()

    # --- UI ACTIONS ---

    def browse_workspace(self):
        filename = filedialog.askopenfilename(
            title="Select VS Code Workspace",
            filetypes=[("VS Code Workspace", "*.code-workspace"), ("All Files", "*.*")]
        )
        if filename:
            self.entry_workspace.delete(0, tk.END)
            self.entry_workspace.insert(0, filename)
            self.save_settings()
            self.load_projects_from_workspace()

    def browse_java(self):
        directory = filedialog.askdirectory(title="Select JDK 8 Directory")
        if directory:
            self.entry_java.delete(0, tk.END)
            self.entry_java.insert(0, directory)
            self.save_settings()

    def save_settings(self):
        data = {
            "workspace_path": self.entry_workspace.get(),
            "java_home": self.entry_java.get()
        }
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(data, f)
        except Exception: pass

    # --- CORE BUILD LOGIC ---

    def load_projects_from_workspace(self):
        workspace_file = self.entry_workspace.get()
        
        # Clear list
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.projects = []
        self.vars = []

        if not workspace_file or not os.path.exists(workspace_file):
            self.log("[INFO] Please select a valid workspace file.")
            return

        try:
            with open(workspace_file, 'r') as f:
                content = f.read()
                clean_lines = [line for line in content.splitlines() if not line.strip().startswith("//")]
                data = json.loads("\n".join(clean_lines))
                
                folders = data.get("folders", [])
                
                # Priority Sorting
                priority_keywords = ["common-lib", "bom", "api", "web"]
                sorted_folders = sorted(folders, key=lambda x: next((i for i, k in enumerate(priority_keywords) if k in x['path']), 99))

                ws_dir = os.path.dirname(workspace_file)

                for item in sorted_folders:
                    path = item.get("path")
                    if not os.path.isabs(path):
                        full_path = os.path.normpath(os.path.join(ws_dir, path))
                    else:
                        full_path = os.path.normpath(path)
                    
                    var = tk.IntVar()
                    chk = tk.Checkbutton(self.scrollable_frame, text=full_path, variable=var, anchor='w', bg="white")
                    chk.pack(fill='x', padx=5, pady=2)
                    self.projects.append(full_path)
                    self.vars.append(var)
                
                self.log(f"[INFO] Loaded {len(self.projects)} projects.")
                self.save_settings() # Auto save jika berhasil load

        except Exception as e:
            self.log(f"[ERROR] Failed to load projects: {str(e)}")
            messagebox.showerror("Error", f"Workspace Error:\n{e}")

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
        self.btn_build.config(state="disabled", text="Building... ⏳")
        threading.Thread(target=self.run_builds).start()

    def run_builds(self):
        java_home = self.entry_java.get()
        if not java_home:
            messagebox.showerror("Error", "Java 8 Path cannot be empty!")
            self.btn_build.config(state="normal", text="BUILD SELECTED 🚀")
            return

        selected_indices = [i for i, var in enumerate(self.vars) if var.get() == 1]
        
        if not selected_indices:
            messagebox.showwarning("Warning", "No projects selected!")
            self.btn_build.config(state="normal", text="BUILD SELECTED 🚀")
            return

        # Prepare Environment
        my_env = os.environ.copy()
        my_env["JAVA_HOME"] = java_home
        my_env["PATH"] = f"{java_home}\\bin;" + my_env["PATH"]
        
        mvn_cmd = ["mvn", "clean", "install", "-Dmaven.javadoc.skip=true", "-DskipTests", "-DPROJECT_ENV=LOCAL"]

        self.log("\n" + "="*60)
        self.log(f"STARTING BUILD SEQUENCE")
        self.log(f"Java: {java_home}")
        self.log("="*60)

        for idx in selected_indices:
            project_path = self.projects[idx]
            folder_name = os.path.basename(project_path)
            
            self.log(f"\n>>> Building: {folder_name} ...")
            
            if not os.path.exists(os.path.join(project_path, "pom.xml")):
                self.log(f"[SKIP] No pom.xml in {project_path}")
                continue

            try:
                process = subprocess.Popen(
                    mvn_cmd, 
                    cwd=project_path, 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.STDOUT,
                    env=my_env, 
                    universal_newlines=True,
                    shell=True 
                )
                
                for line in process.stdout:
                    clean_line = line.strip()
                    if any(x in clean_line for x in ["[INFO]", "[ERROR]", "[WARNING]", "BUILD"]):
                         self.log(clean_line)
                
                process.wait()

                if process.returncode == 0:
                    self.log(f"✅ [SUCCESS] {folder_name}")
                    if "dfms-web" in folder_name:
                        self.copy_ws_properties(project_path)
                else:
                    self.log(f"❌ [FAILURE] {folder_name}")
                    messagebox.showerror("Build Failed", f"Failed to build {folder_name}")
                    self.btn_build.config(state="normal", text="BUILD SELECTED 🚀")
                    return 

            except Exception as e:
                self.log(f"[CRITICAL ERROR] {str(e)}")
                self.btn_build.config(state="normal", text="BUILD SELECTED 🚀")
                return

        self.log("\n" + "="*60)
        self.log("🎉 ALL BUILDS COMPLETED SUCCESSFULLY!")
        self.log("="*60)
        messagebox.showinfo("Done", "Build Sequence Completed!")
        self.btn_build.config(state="normal", text="BUILD SELECTED 🚀")

    def copy_ws_properties(self, web_path):
        src = os.path.join(web_path, "src", "main", "webapp", "WEB-INF", "ws.properties")
        dst = os.path.join(web_path, "target", "dfms-web", "WEB-INF") 
        
        if os.path.exists(src):
            try:
                if not os.path.exists(dst): os.makedirs(dst)
                import shutil
                shutil.copy(src, dst)
                self.log(f"   └── [PATCH] ws.properties copied to target.")
            except Exception as e:
                self.log(f"   └── [ERROR] Failed to copy ws.properties: {e}")
        else:
            self.log(f"   └── [WARN] Source ws.properties not found at {src}")

if __name__ == "__main__":
    root = tk.Tk()
    app = BuildManagerApp(root)
    root.mainloop()