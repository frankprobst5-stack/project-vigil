# =========================================================================
# PROJECT VIGIL v2.0 // MASTER OFF-GRID SMART HOME CONTROLLER KERNEL
# Copyright (C) 2026 SnapPress // Copyleft GNU AGPL-3.0-or-later
# =========================================================================

import json
import os
import time
import http.server
import socketserver
import threading

STATE_FILE = "vigil_state.json"
PORT = 8082  # Aligned for Project Citadel coexistence

# Thread-safe global RAM state matrix tracking physical hardware parameters
system_state = {
    "solar_battery_soc": 100,       
    "solar_input_watts": 0,         
    "critical_power_bus": "ON",     
    "secondary_power_bus": "ON",    
    "perimeter_tripline": "SECURE", 
    "smart_plug_fridge": "ON",      
    "perimeter_lights": "OFF",      
    "last_update": "NEVER"
}

state_lock = threading.Lock()

def save_state_to_disk():
    with state_lock:
        system_state["last_update"] = time.strftime("%Y-%m-%d %H:%M:%S UTC")
        target_path = os.path.join(os.path.dirname(__file__), STATE_FILE)
        with open(target_path, "w") as f:
            json.dump(system_state, f, indent=4)

def load_state_from_disk():
    global system_state
    target_path = os.path.join(os.path.dirname(__file__), STATE_FILE)
    if os.path.exists(target_path):
        try:
            with open(target_path, "r") as f:
                disk_data = json.load(f)
                with state_lock:
                    system_state.update(disk_data)
            print("💾 [STATE ENGINE] Recovered home metric tracking data from flat disk.")
        except Exception:
            save_state_to_disk()
    else:
        save_state_to_disk()

class VigilAPIHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return
        
    def do_GET(self):
        if self.path == "/api/state":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            with state_lock:
                response_bytes = json.dumps(system_state).encode("utf-8")
            self.wfile.write(response_bytes)
        else:
            self.send_error(404, "Endpoint Missing")

    def do_POST(self):
        if self.path == "/api/update":
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                incoming_metrics = json.loads(post_data.decode('utf-8'))
                with state_lock:
                    for key, val in incoming_metrics.items():
                        if key in system_state:
                            system_state[key] = val
                save_state_to_disk()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(b'{"status":"STATE_SYNCHRONIZED_SUCCESS"}')
            except Exception:
                self.send_error(400, "Bad Request")
        else:
            self.send_error(404, "Endpoint Missing")

def start_api_server():
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), VigilAPIHandler) as httpd:
        print(f"🔌 [INITIALIZATION] Local API Gateway active at port: {PORT}")
        httpd.serve_forever()

if __name__ == "__main__":
    print("=============================================================")
    print("⚙️  PROJECT VIGIL: Micro-Kernel Home Master Controller v2.0")
    print("=============================================================")
    load_state_from_disk()
    start_api_server()
