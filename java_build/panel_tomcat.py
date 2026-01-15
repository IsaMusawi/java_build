import tkinter as tk
from tkinter import messagebox, filedialog, simpledialog
import os
import subprocess
import threading
import shutil
import re

class TomcatPanel(tk.Frame):
    def __init__(self, parent, config, logger, instance_name="Tomcat"):
        super().__init__(parent)
        self.config = config
        self.raw_logger = logger 
        self.instance_name = instance_name 
        self.rename_callback = None 
        
        # Variables
        self.deploy_project_path = tk.StringVar()
        self.deploy_target_name = tk.StringVar()
        
        # Port Variables
        self.var_port_http = tk.StringVar()
        self.var_port_ajp = tk.StringVar()
        self.var_port_shutdown = tk.StringVar()
        self.var_port_debug = tk.StringVar()
        
        self.setup_ui()
        if self.config.get("tomcat_home"): self.load_current_ports()
        self.load_deploy_config()
        
        # 1. Load Port Config (Hanya jika Home Path ada)
        if self.config.get("tomcat_home"):
            self.load_current_ports()
            
        # 2. Load Smart Deploy Config (FITUR BARU)
        self.load_deploy_config()

    def log(self, msg):
        self.raw_logger(f"[{self.instance_name}] {msg}")

    def setup_ui(self):
        # Header
        header_frame = tk.Frame(self)
        header_frame.pack(fill=tk.X, pady=5)
        self.lbl_title = tk.Label(header_frame, text=f"🐱 Server: {self.instance_name}", font=("Arial", 11, "bold"), fg="#ff6600")
        self.lbl_title.pack(side=tk.LEFT, padx=5)
        tk.Button(header_frame, text="✏️ Rename Tab", font=("Arial", 7), command=self.rename_tab).pack(side=tk.RIGHT, padx=5)

        # 1. SERVER CONFIG
        fr = tk.LabelFrame(self, text="Server Path", padx=5, pady=5)
        fr.pack(fill=tk.X, padx=5)
        path_frame = tk.Frame(fr)
        path_frame.pack(fill=tk.X)
        self.ent_home = tk.Entry(path_frame)
        # Default load global home untuk mempermudah
        self.ent_home.insert(0, self.config.get("tomcat_home"))
        self.ent_home.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(path_frame, text="Browse...", command=self.browse_home, font=("Arial", 8)).pack(side=tk.RIGHT, padx=(5,0))

        # 2. PORT EDITOR
        p_fr = tk.LabelFrame(self, text="Port Configuration", padx=5, pady=5, fg="blue")
        p_fr.pack(fill=tk.X, padx=5, pady=5)
        tk.Label(p_fr, text="HTTP:").grid(row=0, column=0, sticky="w")
        tk.Entry(p_fr, textvariable=self.var_port_http, width=8).grid(row=0, column=1, padx=5, pady=2)
        tk.Label(p_fr, text="AJP:").grid(row=0, column=2, sticky="w", padx=(5,0))
        tk.Entry(p_fr, textvariable=self.var_port_ajp, width=8).grid(row=0, column=3, padx=5, pady=2)
        tk.Label(p_fr, text="Shut:").grid(row=1, column=0, sticky="w")
        tk.Entry(p_fr, textvariable=self.var_port_shutdown, width=8).grid(row=1, column=1, padx=5, pady=2)
        tk.Label(p_fr, text="Debug:").grid(row=1, column=2, sticky="w", padx=(5,0))
        tk.Entry(p_fr, textvariable=self.var_port_debug, width=8).grid(row=1, column=3, padx=5, pady=2)
        tk.Button(p_fr, text="💾 Save", bg="#ffeb3b", font=("Arial", 8), command=self.save_ports).grid(row=0, column=4, rowspan=2, padx=10, sticky="ns")

        # 3. SMART DEPLOYMENT
        d_fr = tk.LabelFrame(self, text="⚡ Smart Deployment (Auto-Saved)", padx=5, pady=5, bg="#e3f2fd")
        d_fr.pack(fill=tk.X, padx=5, pady=5)
        
        f_sel = tk.Frame(d_fr, bg="#e3f2fd")
        f_sel.pack(fill=tk.X)
        tk.Label(f_sel, text="Proj:", bg="#e3f2fd").pack(side=tk.LEFT)
        tk.Entry(f_sel, textvariable=self.deploy_project_path, state="readonly", bg="#f0f0f0", width=15).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        tk.Button(f_sel, text="📂", command=self.browse_project_for_deploy, bg="white", width=3).pack(side=tk.LEFT)

        f_act = tk.Frame(d_fr, bg="#e3f2fd")
        f_act.pack(fill=tk.X, pady=5)
        tk.Label(f_act, text="Ctx:", bg="#e3f2fd").pack(side=tk.LEFT)
        # Entry ini kita bind event KeyRelease agar kalau user edit manual, tetap tersimpan
        self.ent_target = tk.Entry(f_act, textvariable=self.deploy_target_name, font=("Arial", 9, "bold"), fg="blue", width=12)
        self.ent_target.pack(side=tk.LEFT, padx=2)
        self.ent_target.bind("<KeyRelease>", self.on_target_change) # Auto save saat ngetik
        
        self.btn_deploy = tk.Button(f_act, text="📥 Deploy", bg="#2196F3", fg="white", font=("Arial", 9, "bold"), command=self.execute_deployment)
        self.btn_deploy.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 4. CONTROLS
        c_fr = tk.LabelFrame(self, text="Control", padx=5, pady=5)
        c_fr.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0,5))
        tk.Button(c_fr, text="▶ START", bg="#4CAF50", fg="white", command=lambda: self.start(False)).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        tk.Button(c_fr, text="🐞 DEBUG", bg="#9C27B0", fg="white", command=lambda: self.start(True)).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        tk.Button(c_fr, text="⏹ STOP", bg="#f44336", fg="white", command=self.stop).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)

    # --- MEMORY LOGIC ---
    def load_deploy_config(self):
        """Memuat setting terakhir untuk Tab ini"""
        saved = self.config.get_instance_deploy(self.instance_name)
        if saved["project"]:
            self.deploy_project_path.set(saved["project"])
        if saved["target"]:
            self.deploy_target_name.set(saved["target"])

    def save_deploy_config(self):
        """Menyimpan setting saat ini ke JSON"""
        self.config.set_instance_deploy(
            self.instance_name, 
            self.deploy_project_path.get(), 
            self.deploy_target_name.get()
        )

    def on_target_change(self, event):
        """Callback saat user mengetik di kolom Context"""
        self.save_deploy_config()

    def set_rename_callback(self, func):
        self.rename_callback = func

    def rename_tab(self):
        new_name = simpledialog.askstring("Rename", "Masukkan nama server:", initialvalue=self.instance_name)
        if new_name and new_name != self.instance_name:
            # 1. Migrasi Config lama ke baru
            old_conf = self.config.get_instance_deploy(self.instance_name)
            self.config.set_instance_deploy(new_name, old_conf["project"], old_conf["target"])
            
            # 2. Update UI
            self.instance_name = new_name
            self.lbl_title.config(text=f"🐱 Server: {new_name}")
            try:
                self.master.tab(self.master.index("current"), text=new_name)
            except: pass

            # 3. Panggil MainApp untuk simpan daftar tab baru
            if self.rename_callback:
                self.rename_callback()

    # --- ACTIONS ---
    def browse_home(self):
        d = filedialog.askdirectory()
        if d:
            self.ent_home.delete(0, tk.END); self.ent_home.insert(0, d)
            if self.instance_name == "Tomcat-1": self.config.set("tomcat_home", d)
            self.load_current_ports()

    def browse_project_for_deploy(self):
        d = filedialog.askdirectory()
        if not d: return
        self.deploy_project_path.set(d)
        
        target = os.path.join(d, "target")
        # Auto-detect logic
        detected_name = ""
        if os.path.exists(target): 
            ignore = ['classes', 'test-classes', 'maven-archiver', 'maven-status', 'surefire-reports']
            cands = [f for f in os.listdir(target) if os.path.isdir(os.path.join(target, f)) and f not in ignore]
            if cands: detected_name = cands[0]
        
        self.deploy_target_name.set(detected_name)
        self.save_deploy_config() # <--- AUTO SAVE DISINI

    def execute_deployment(self):
        # Save before deploy
        self.save_deploy_config()
        
        home = self.ent_home.get()
        path = self.deploy_project_path.get()
        name = self.deploy_target_name.get().strip()
        if not home or not name: return messagebox.showerror("Err", "Config incomplete")
        
        docbase = os.path.join(path, "target", name)
        if not os.path.exists(docbase): return messagebox.showerror("Err", f"Target not found: {docbase}")

        xml = os.path.join(home, "conf", "Catalina", "localhost", f"{name}.xml")
        try:
            if not os.path.exists(os.path.dirname(xml)): os.makedirs(os.path.dirname(xml))
            with open(xml, "w") as f: f.write(f'<Context docBase="{docbase}" path="/{name}" reloadable="true"></Context>')
            self.log(f"✅ Deployed /{name}")
            messagebox.showinfo("OK", f"Deployed successfully!")
        except Exception as e: self.log(f"Err Deploy: {e}")

    # --- PORT LOGIC (Improved Regex) ---
    def load_current_ports(self):
        # ... (Sama seperti kode regex sebelumnya) ...
        # Copy dari kode Port Editor Edition sebelumnya
        home = self.ent_home.get()
        if not home or not os.path.exists(home): return
        server_xml = os.path.join(home, "conf", "server.xml")
        if os.path.exists(server_xml):
            try:
                with open(server_xml, 'r', encoding='utf-8') as f: content = f.read()
                m_shut = re.search(r'<Server[^>]*port="(\d+)"', content)
                if m_shut: self.var_port_shutdown.set(m_shut.group(1))
                # Regex HTTP Aggressive
                m_http = re.search(r'<Connector[^>]*protocol=["\']HTTP/[^"\']*["\'][^>]*port=["\'](\d+)["\']', content)
                if not m_http: m_http = re.search(r'<Connector[^>]*port=["\'](\d+)["\'][^>]*protocol=["\']HTTP', content)
                if m_http: self.var_port_http.set(m_http.group(1))
                # Regex AJP
                m_ajp = re.search(r'<Connector[^>]*protocol=["\']AJP/[^"\']*["\'][^>]*port=["\'](\d+)["\']', content)
                if m_ajp: self.var_port_ajp.set(m_ajp.group(1))
            except: pass
        setenv = os.path.join(home, "bin", "setenv.bat")
        if os.path.exists(setenv):
            try:
                with open(setenv, 'r') as f:
                    m = re.search(r'JPDA_ADDRESS=(\d+)', f.read())
                    if m: self.var_port_debug.set(m.group(1))
            except: pass
        else: self.var_port_debug.set("8000")

    def save_ports(self):
        # ... (Sama seperti kode regex sebelumnya) ...
        home = self.ent_home.get()
        if not home or not os.path.exists(home): return
        xml = os.path.join(home, "conf", "server.xml")
        try:
            with open(xml, 'r') as f: c = f.read()
            c = re.sub(r'(<Server[^>]*port=")(\d+)(")', rf'\g<1>{self.var_port_shutdown.get()}\g<3>', c)
            c = re.sub(r'(<Connector[^>]*protocol=["\']HTTP/[^"\']*["\'][^>]*port=")(\d+)(")', rf'\g<1>{self.var_port_http.get()}\g<3>', c)
            c = re.sub(r'(<Connector[^>]*port=")(\d+)("[^>]*protocol=["\']HTTP)', rf'\g<1>{self.var_port_http.get()}\g<3>', c)
            # AJP hanya update jika ada
            if self.var_port_ajp.get():
                c = re.sub(r'(<Connector[^>]*protocol=["\']AJP/[^"\']*["\'][^>]*port=")(\d+)(")', rf'\g<1>{self.var_port_ajp.get()}\g<3>', c)
                c = re.sub(r'(<Connector[^>]*port=")(\d+)("[^>]*protocol=["\']AJP)', rf'\g<1>{self.var_port_ajp.get()}\g<3>', c)
            with open(xml, 'w') as f: f.write(c)
        except Exception as e: self.log(f"Err server.xml: {e}")

        bat = os.path.join(home, "bin", "setenv.bat")
        new_d = self.var_port_debug.get()
        try:
            content = ""
            if os.path.exists(bat):
                with open(bat, 'r') as f: content = f.read()
                if "JPDA_ADDRESS" in content: content = re.sub(r'(JPDA_ADDRESS=)(\d+)', rf'\g<1>{new_d}', content)
                else: content += f"\nset JPDA_ADDRESS={new_d}"
            else: content = f"set JPDA_ADDRESS={new_d}\nset JPDA_TRANSPORT=dt_socket"
            with open(bat, 'w') as f: f.write(content)
            self.log(f"✅ Ports Saved.")
        except Exception as e: self.log(f"Err setenv: {e}")

    # --- PROCESS CONTROL (START/STOP) ---
    def start(self, debug):
        home = self.ent_home.get()
        java = self.config.get("java_home")
        if not os.path.exists(home) or not os.path.exists(java): return messagebox.showerror("Err", "Path Invalid")
        env = os.environ.copy()
        env["JAVA_HOME"] = java; env["CATALINA_HOME"] = home; env["PATH"] = f"{java}\\bin;{home}\\bin;" + env["PATH"]; env["PROJECT_ENV"] = "LOCAL"
        cmd = f"catalina.bat {'jpda run' if debug else 'run'}"
        self.log(f"🚀 STARTING...")
        threading.Thread(target=self._run_proc, args=(cmd, home, env)).start()

    def _run_proc(self, cmd, cwd, env):
        try:
            self.proc = subprocess.Popen(cmd, cwd=os.path.join(cwd, "bin"), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True, universal_newlines=True)
            for line in self.proc.stdout: self.log(line.strip())
            self.proc.wait(); self.log("🛑 STOPPED")
        except Exception as e: self.log(f"Err: {e}")

    def stop(self):
        self.log("Killing Java..."); subprocess.run(["taskkill", "/F", "/IM", "java.exe"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)