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
import socket  # Added for direct offline hardware network control

STATE_FILE = "vigil_state.json"
PORT = 8085

# Thread-safe global RAM state matrix tracking physical hardware devices
system_state = {
    "solar_battery_soc": 100,       
    "solar_input_watts": 0,         
    "critical_power_bus": "ON",     
    "secondary_power_bus": "ON",    
    "perimeter_tripline": "SECURE", 
    "smart_plug_fridge": "ON",      # Local smart plug relay state
    "perimeter_lights": "OFF",      # Local home security light array state
    "last_update": "NEVER"
}

state_lock = threading.Lock()

def blast_local_hardware_command(device_ip, target_port, command_payload):
    """Blasts an offline digital command packet directly to a local smart switch or plug"""
    print(f"📡 [HARDWARE OUTBOUND] Sending packet to {device_ip}:{target_port} -> {command_payload}")
    try:
        # Open a fast, raw UDP network socket lane to hit the physical switch instantly
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(1.0)
            sock.sendto(command_payload.encode('utf-8'), (device_ip, target_port))
    except Exception:
        print(f"⚠️ [HARDWARE ERROR] Unable to bridge communication lane with device at {device_ip}")

def save_state_to_disk():
    with state_lock:
        system_state["last_update"] = time.strftime("%Y-%m-%d %H:%M:%S UTC")
        with open(STATE_FILE, "w") as f:
            json.dump(system_state, f, indent=4)
def load_state_from_disk():
    global system_state
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                disk_data = json.load(f)
                with state_lock:
                    system_state.update(disk_data)
            print("💾 [STATE ENGINE] Recovered home hardware states from flat disk.")
        except Exception:
            save_state_to_disk()
    else:
        save_state_to_disk()

def autonomous_hardware_automation_loop():
    """The automated brain: Evaluates states and triggers local smart hardware actions"""
    # Sample Mock IP coordinates for physical smart devices connected to your router
    PLUG_FRIDGE_IP = "192.168.11.50"   
    SECURITY_LIGHTS_IP = "192.168.11.60" 

    while True:
        with state_lock:
            soc = system_state["solar_battery_soc"]
            tripline = system_state["perimeter_tripline"]
            secondary_bus = system_state["secondary_power_bus"]
            lights = system_state["perimeter_lights"]
            
            state_changed = False

            # 🔋 POWER AUTOMATION: If battery drops below critical 24% threshold
            if soc < 24 and secondary_bus == "ON":
                print("\n🚨 [LOAD SHEDDER] FORCING SECONDARY LOADS AND SMART PLUGS OFFLINE!")
                system_state["secondary_power_bus"] = "OFF"
                system_state["smart_plug_fridge"] = "OFF"
                state_changed = True
                # Blast raw offline network command to physically cut power to that device slot
                blast_local_hardware_command(PLUG_FRIDGE_IP, 9999, "RELAY_OFF")

            # ☀️ POWER RECOVERY: Re-engage when battery charges past 40%
            elif soc >= 40 and secondary_bus == "OFF":
                print("\n☀️ [POWER RECOVERY] SOLAR INTAKE OPTIMAL. RE-ENGAGING ACCESSORIES.")
                system_state["secondary_power_bus"] = "ON"
                system_state["smart_plug_fridge"] = "ON"
                state_changed = True
                blast_local_hardware_command(PLUG_FRIDGE_IP, 9999, "RELAY_ON")

            # 🛡️ SECURITY AUTOMATION: If security system or Project Ibris reports a breach
            if tripline == "TRIPPED" and lights == "OFF":
                print("\n🚨 [SECURITY INTERCEPT] PERIMETER BREACH DETECTED!")
                print("🚨 [SECURITY INTERCEPT] FORCING PROPERTY DEFENSIVE LIGHTING ARRAYS ON!")
                system_state["perimeter_lights"] = "ON"
                state_changed = True
                # Blast an automated command to instantly flip your property floodlights on
                blast_local_hardware_command(SECURITY_LIGHTS_IP, 9999, "LIGHTS_ON")
                
            elif tripline == "SECURE" and lights == "ON":
                print("\n🛡️ [SECURITY SAFE] Perimeter secure. Resetting lighting grids.")
                system_state["perimeter_lights"] = "OFF"
                state_changed = True
                blast_local_hardware_command(SECURITY_LIGHTS_IP, 9999, "LIGHTS_OFF")

        if state_changed:
            save_state_to_disk()
            
        time.sleep(4) # Run the hardware automation scans every 4 seconds
class VigilAPIHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return
        
    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            try:
                with open("index.html", "r", encoding="utf-8") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(content.encode("utf-8"))
            except Exception:
                self.send_error(500, "index.html missing")
                
        elif self.path == "/api/state":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
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
                self.end_headers()
                self.wfile.write(b'{"status":"STATE_SYNCHRONIZED_SUCCESS"}')
            except Exception:
                self.send_error(400, "Bad Request")
        else:
            self.send_error(404, "Endpoint Missing")

def start_api_server():
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), VigilAPIHandler) as httpd:
        print(f"🔌 [INITIALIZATION] Local API Gateway active at: http://localhost:{PORT}")
        httpd.serve_forever()

if __name__ == "__main__":
    print("=============================================================")
    print("⚙️  PROJECT VIGIL: Micro-Kernel Home Master Controller v2.0")
    print("Copyright (C) 2026 SnapPress")
    print("=============================================================")
    load_state_from_disk()
    automation_thread = threading.Thread(target=autonomous_hardware_automation_loop, daemon=True)
    automation_thread.start()
    start_api_server()
