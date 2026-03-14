import json

class ConfigManager:
    def __init__(self, config_file):
        self.config_file = config_file
        self.config = self.load_config()
    
    def load_config(self):
        try:
            with open(self.config_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print("Config not found")
    
    def save_config(self, config=None):
        with open(self.config_file, 'w') as f:
            json.dump(config or self.config, f, indent=4)
    
    def get_config(self):
        return self.config
    
    def update_config(self, section, key, value):
        if section not in self.config:
            self.config[section] = {}
        self.config[section][key] = value
        self.save_config()