import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import os
import subprocess
import threading
import shutil

class BuildPanel(tk.Frame):
    def __init__(self, parent, config, logger):
        super().__init__(parent)
        self.config = config
        self.log = logger # Callback function untuk nulis log ke Main Window
        self.projects = []
        self.vars = []
        
        self.setup_ui()
        # Auto load jika config sudah ada
        if self.config.get("workspace_path"):
            self.load_projects()

    def setup_ui(self):
        lbl = tk.Label(self, text="🛠️ Maven Build Manager", font=("Arial", 12, "bold"), fg="blue")
        lbl.pack(pady=10)

        # Config Area
        fr = tk.LabelFrame(self, text="Source Config", padx=5, pady=5)
        fr.pack(fill=tk.X, padx=5)

        tk.Label(fr, text="Workspace (.code-workspace):").pack(anchor="w")
        self.ent_ws = tk.Entry(fr)
        self.ent_ws.insert(0, self.config.get("workspace_path"))
        self.ent_ws.pack(fill=tk.X)
        tk.Button(fr, text="Browse...", command=self.browse_ws, font=("Arial", 8)).pack(anchor="e", pady=2)

        tk.Label(fr, text="Java 8 Home:").pack(anchor="w")
        self.ent_java = tk.Entry(fr)
        self.ent_java.insert(0, self.config.get("java_home"))
        self.ent_java.pack(fill=tk.X)
        tk.Button(fr, text="Browse...", command=self.browse_java, font=("Arial", 8)).pack(anchor="e", pady=2)

        # Project List
        tk.Label(self, text="Project List:").pack(anchor="w", padx=5, pady=(10,0))
        
        list_fr = tk.Frame(self, bd=1, relief="sunken")
        list_fr.pack(fill=tk.BOTH, expand=True, padx=5)
        
        cvs = tk.Canvas(list_fr, bg="white")
        scr = ttk.Scrollbar(list_fr, orient="vertical", command=cvs.yview)
        self.scroll_frame = tk.Frame(cvs, bg="white")
        
        self.scroll_frame.bind("<Configure>", lambda e: cvs.configure(scrollregion=cvs.bbox("all")))
        cvs.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        cvs.configure(yscrollcommand=scr.set)
        
        cvs.pack(side="left", fill="both", expand=True)
        scr.pack(side="right", fill="y")

        # Buttons
        btn_fr = tk.Frame(self)
        btn_fr.pack(pady=10)
        tk.Button(btn_fr, text="Reload", command=self.load_projects).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_fr, text="All", command=lambda: [v.set(1) for v in self.vars]).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_fr, text="None", command=lambda: [v.set(0) for v in self.vars]).pack(side=tk.LEFT, padx=2)
        
        self.btn_run = tk.Button(btn_fr, text="BUILD 🚀", bg="green", fg="white", font=("Arial", 10, "bold"), command=self.start_thread)
        self.btn_run.pack(side=tk.LEFT, padx=10)

    def browse_ws(self):
        f = filedialog.askopenfilename(filetypes=[("VS Code Workspace", "*.code-workspace")])
        if f:
            self.ent_ws.delete(0, tk.END); self.ent_ws.insert(0, f)
            self.config.set("workspace_path", f)
            self.load_projects()

    def browse_java(self):
        d = filedialog.askdirectory()
        if d:
            self.ent_java.delete(0, tk.END); self.ent_java.insert(0, d)
            self.config.set("java_home", d)

    def load_projects(self):
        path = self.ent_ws.get()
        for w in self.scroll_frame.winfo_children(): w.destroy()
        self.projects = []; self.vars = []
        
        if not os.path.exists(path): return
        try:
            with open(path, 'r') as f:
                raw = f.read()
                clean = [l for l in raw.splitlines() if not l.strip().startswith("//")]
                data = json.loads("\n".join(clean))
                
                # Sorting logic
                folders = data.get("folders", [])
                prio = ["common-lib", "bom", "api", "web"]
                sorted_f = sorted(folders, key=lambda x: next((i for i, k in enumerate(prio) if k in x['path']), 99))
                
                ws_dir = os.path.dirname(path)
                for item in sorted_f:
                    p = item.get("path")
                    full = os.path.normpath(os.path.join(ws_dir, p)) if not os.path.isabs(p) else os.path.normpath(p)
                    
                    v = tk.IntVar()
                    tk.Checkbutton(self.scroll_frame, text=os.path.basename(full), variable=v, anchor='w', bg="white").pack(fill='x', padx=5)
                    self.projects.append(full)
                    self.vars.append(v)
            self.log("[INFO] Projects loaded.")
        except Exception as e:
            self.log(f"[ERROR] Load projects: {e}")

    def start_thread(self):
        threading.Thread(target=self.run_builds).start()

    def run_builds(self):
        java = self.ent_java.get()
        sel = [i for i, v in enumerate(self.vars) if v.get() == 1]
        
        if not sel: return
        self.btn_run.config(state="disabled")
        
        env = os.environ.copy()
        env["JAVA_HOME"] = java
        env["PATH"] = f"{java}\\bin;" + env["PATH"]
        cmd = ["mvn", "clean", "install", "-Dmaven.javadoc.skip=true", "-DskipTests", "-DPROJECT_ENV=LOCAL"]

        self.log(f"\n=== STARTING BUILD ({len(sel)} Projects) ===")
        for idx in sel:
            p_path = self.projects[idx]
            name = os.path.basename(p_path)
            
            if not os.path.exists(os.path.join(p_path, "pom.xml")):
                self.log(f"[SKIP] {name} (No pom.xml)")
                continue
                
            self.log(f"> Building {name}...")
            try:
                proc = subprocess.Popen(cmd, cwd=p_path, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, universal_newlines=True, shell=True)
                for line in proc.stdout:
                    l = line.strip()
                    if any(x in l for x in ["[INFO]", "[ERROR]", "BUILD"]): self.log(l)
                proc.wait()
                
                if proc.returncode == 0:
                    self.log(f"✅ {name} SUCCESS")
                    if "dfms-web" in name: self.copy_ws(p_path)
                else:
                    self.log(f"❌ {name} FAILED")
                    self.btn_run.config(state="normal")
                    return
            except Exception as e:
                self.log(f"[CRITICAL] {e}")
                self.btn_run.config(state="normal")
                return
                
        self.log("=== BUILD SEQUENCE COMPLETE ===")
        self.btn_run.config(state="normal")

    def copy_ws(self, path):
        src = os.path.join(path, "src", "main", "webapp", "WEB-INF", "ws.properties")
        dst = os.path.join(path, "target", "dfms-web", "WEB-INF")
        if os.path.exists(src):
            try:
                if not os.path.exists(dst): os.makedirs(dst)
                shutil.copy(src, dst)
                self.log("   └── [PATCH] ws.properties copied.")
            except: pass