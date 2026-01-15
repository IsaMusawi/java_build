import tkinter as tk
from tkinter import scrolledtext, ttk
from config import ConfigManager
from panel_build import BuildPanel
from panel_tomcat import TomcatPanel

class MainApp:
    def __init__(self, root):
        self.root = root
        self.root.title("SM DevOps Dashboard (Multi-Server Persisted)")
        self.root.geometry("1200x800")
        
        self.config = ConfigManager()
        self.tomcat_counter = 1

        # Log Area
        log_frame = tk.LabelFrame(root, text="System Logs", padx=5, pady=5)
        log_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=5, pady=5)
        self.txt_log = scrolledtext.ScrolledText(log_frame, height=12, state='disabled', bg="#1e1e1e", fg="#00FF00", font=("Consolas", 9))
        self.txt_log.pack(fill=tk.BOTH, expand=True)

        # Paned Window
        paned = tk.PanedWindow(root, orient=tk.HORIZONTAL, sashrelief=tk.RAISED, sashwidth=5)
        paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Left Panel
        self.left_panel = BuildPanel(paned, self.config, self.log)
        paned.add(self.left_panel, minsize=400)

        # Right Panel
        right_container = tk.Frame(paned)
        paned.add(right_container, minsize=450)

        tab_header = tk.Frame(right_container)
        tab_header.pack(fill=tk.X, pady=(0, 5))
        tk.Label(tab_header, text="Server Instances:", font=("Arial", 10, "bold")).pack(side=tk.LEFT)
        tk.Button(tab_header, text="➕ Add Server", bg="#dddddd", command=self.add_new_tab_btn).pack(side=tk.RIGHT)

        self.tabs = ttk.Notebook(right_container)
        self.tabs.pack(fill=tk.BOTH, expand=True)

        # --- RESTORE TABS LOGIC ---
        saved_tabs = self.config.get_active_tabs()
        if saved_tabs:
            # Jika ada data tersimpan (misal: "email-api"), load itu
            for tab_name in saved_tabs:
                self.create_tomcat_tab(tab_name)
        else:
            # Jika kosong (baru pertama kali install), buat Tomcat-1
            self.create_tomcat_tab("Tomcat-1")

    def create_tomcat_tab(self, name):
        """Helper function untuk membuat tab tanpa update config (dipakai saat startup)"""
        t_panel = TomcatPanel(self.tabs, self.config, self.log, instance_name=name)
        # Pass callback 'on_rename' agar MainApp bisa update list tabs saat rename
        t_panel.set_rename_callback(self.update_tab_list_config) 
        self.tabs.add(t_panel, text=name)
        
        # Update counter agar tombol (+) tidak membuat nama duplikat
        if name.startswith("Tomcat-"):
            try:
                num = int(name.split("-")[1])
                if num >= self.tomcat_counter: self.tomcat_counter = num + 1
            except: pass

    def add_new_tab_btn(self):
        """Dipanggil saat tombol (+) ditekan user"""
        name = f"Tomcat-{self.tomcat_counter}"
        self.create_tomcat_tab(name)
        self.tabs.select(len(self.tabs.tabs()) - 1) # Switch ke tab baru
        self.update_tab_list_config() # Simpan ke config

    def update_tab_list_config(self):
        """Membaca semua tab yang ada sekarang dan menyimpannya ke JSON"""
        current_tabs = []
        for i in range(len(self.tabs.tabs())):
            # Trik mengambil nama Tab dari widget title
            # (tapi lebih aman jika kita track manual, atau ambil dari child instance_name)
            # Cara terbaik: iterasi children
            widget_name = self.tabs.tabs()[i]
            widget = self.tabs.nametowidget(widget_name)
            if hasattr(widget, 'instance_name'):
                current_tabs.append(widget.instance_name)
        
        self.config.save_active_tabs(current_tabs)

    def log(self, msg):
        self.txt_log.config(state='normal')
        self.txt_log.insert(tk.END, str(msg) + "\n")
        self.txt_log.see(tk.END)
        self.txt_log.config(state='disabled')

if __name__ == "__main__":
    root = tk.Tk()
    app = MainApp(root)
    root.mainloop()