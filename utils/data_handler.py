import json
import os

class DataHandler:
    def __init__(self, file_path):
        self.file_path = file_path
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        if not os.path.exists(self.file_path):
            with open(self.file_path, 'w') as f:
                json.dump({}, f)

    def load_data(self):
        try:
            with open(self.file_path, 'r') as f:
                data = json.load(f)
            return data
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error loading data: {e}")  # Debugging line
            return {}

    def convert_sets(self, obj):
        if isinstance(obj, set):
            return list(obj)
        elif isinstance(obj, dict):
            return {k: self.convert_sets(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self.convert_sets(i) for i in obj]
        return obj

    def save_data(self, data):
        converted_data = self.convert_sets(data)
        with open(self.file_path, 'w') as f:
            json.dump(converted_data, f, indent=4)
