from flask import Flask, render_template, jsonify, request
import json
import os
from utils.config_manager import ConfigManager

app = Flask(__name__)

config_manager = ConfigManager('config.json')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/config', methods=['GET', 'POST'])
def config():
    if request.method == 'POST':
        data = request.json
        config_manager.save_config(data)
        return jsonify({"status": "success"})
    return jsonify(config_manager.get_config())

@app.route('/api/leveling', methods=['GET'])
def leveling_data():
    try:
        with open('data/leveling.json', 'r') as f:
            return jsonify(json.load(f))
    except FileNotFoundError:
        return jsonify({})

@app.route('/api/tickets', methods=['GET'])
def tickets_data():
    try:
        with open('data/tickets.json', 'r') as f:
            return jsonify(json.load(f))
    except FileNotFoundError:
        return jsonify({})

if __name__ == '__main__':
    app.run()