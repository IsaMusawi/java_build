import json
import os

CONFIG_FILE = "devops_settings.json"

class ConfigManager:
    def __init__(self):
        self.data = {
            "workspace_path": "",
            "java_home": "",
            "tomcat_home": "",
            "active_tabs": [], # <-- MEMORI BARU: Daftar Tab
            "deploy_map": {}
        }
        self.load()

    def load(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    loaded = json.load(f)
                    for k, v in loaded.items():
                        self.data[k] = v
            except: pass
        if not self.data["java_home"]:
            self.data["java_home"] = self.detect_java8()

    def save(self):
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.data, f, indent=4)
        except: pass

    def get(self, key):
        return self.data.get(key, "")

    def set(self, key, value):
        self.data[key] = value
        self.save()

    # --- TAB MANAGEMENT ---
    def get_active_tabs(self):
        return self.data.get("active_tabs", [])

    def save_active_tabs(self, tab_list):
        self.data["active_tabs"] = tab_list
        self.save()

    # --- INSTANCE DEPLOY ---
    def get_instance_deploy(self, instance_name):
        return self.data["deploy_map"].get(instance_name, {"project": "", "target": ""})

    def set_instance_deploy(self, instance_name, project_path, target_name):
        if "deploy_map" not in self.data: self.data["deploy_map"] = {}
        self.data["deploy_map"][instance_name] = {
            "project": project_path,
            "target": target_name
        }
        self.save()

    def detect_java8(self):
        # (Kode detect java sama seperti sebelumnya, tidak berubah)
        user_home = os.path.expanduser("~")
        specific = os.path.join(user_home, "Documents", "SM_TOOLS", "java", "jdk8u452-b09")
        if os.path.exists(specific): return specific
        return ""