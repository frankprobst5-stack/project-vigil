# PROJECT VIGIL v2.1 // OFF-GRID OPEN CONTROLLER HUB
# Copyright (C) 2026 SnapPress // Copyleft GNU AGPL-3.0-or-later

import json
import os
import time
import http.server
import socketserver
import threading
import urllib.request  # Added to dispatch outbound commands to real hardware

STATE_FILE = "vigil_grid_ledger.json"
PORT = 8085
discovered_devices = {}
ledger_lock = threading.Lock()

# Load saved state from previous sessions if it exists
if os.path.exists(STATE_FILE):
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            discovered_devices = json.load(f)
        print(f"💾 [STATE LOADED] Recovered {len(discovered_devices)} devices from ledger.")
    except Exception as e:
        print(f"⚠️ [STATE ERROR] Could not read ledger file: {e}")

def save_ledger_state():
    """Helper to commit the current global device state to disk safely."""
    with ledger_lock:
        try:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(discovered_devices, f, indent=4)
        except Exception as e:
            print(f"⚠️ [SAVE FAILED] Error writing to disk: {e}")

class MasterDiscoveryEngine(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args): 
        return  # Suppress default noise in console

    def do_OPTIONS(self):
        """🌟 THE CORS PREFLIGHT FIX: Resolves errors from modern browser UIs."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

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
                self.send_error(500)
        elif self.path.startswith("/api/grid"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            with ledger_lock: 
                bytes_data = json.dumps(discovered_devices).encode("utf-8")
            self.wfile.write(bytes_data)
        else: 
            self.send_error(404)

    def do_POST(self):
        # Allow cross-origin POSTs right away
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        if self.path == "/api/register":
            try:
                device_packet = json.loads(post_data.decode('utf-8'))
                dev_id = device_packet["device_id"]
                
                with ledger_lock:
                    if dev_id not in discovered_devices: 
                        print(f"\n✨ [CAPTURE SUCCESS] NODE DETECTED! ID: {dev_id} | IP: {device_packet['ip']}")
                    
                    discovered_devices[dev_id] = {
                        "ip": device_packet["ip"], 
                        "type": device_packet["type"], 
                        "state": device_packet.get("state", "ON"), 
                        "stream_url": device_packet.get("stream_url", ""), 
                        "last_seen": time.strftime("%H:%M:%S UTC")
                    }
                
                save_ledger_state()  # Commit to file
                self.send_response(200)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(b'{"status":"CONTROL_SECURED"}')
            except Exception: 
                self.send_error(400)
                
        elif self.path == "/api/toggle":
            try:
                toggle_cmd = json.loads(post_data.decode('utf-8'))
                target_id = toggle_cmd["device_id"]
                target_ip = None
                next_state = "OFF"
                
                with ledger_lock:
                    if target_id in discovered_devices:
                        current = discovered_devices[target_id]["state"]
                        next_state = "OFF" if current == "ON" else "ON"
                        discovered_devices[target_id]["state"] = next_state
                        target_ip = discovered_devices[target_id]["ip"]
                
                if target_ip:
                    print(f"🔌 [OVERRIDE BLAST] Outbound packet sent to local IP {target_ip} -> SET RELAY {next_state}")
                    save_ledger_state()
                    
                    # 🚀 FIRING HARDWARE DIRECTIVE OVER NETWORK
                    # Spawning a background thread keeps the UI fast and snappy
                    def dispatch():
                        try:
                            # Modify url path below if your hardware expects /toggle or /relay instead
                            hardware_url = f"http://{target_ip}/control?state={next_state}"
                            req = urllib.request.Request(hardware_url, method="POST")
                            with urllib.request.urlopen(req, timeout=2) as response:
                                pass
                        except Exception as e:
                            print(f"⚠️ [DISPATCH FAILED] Hardware at {target_ip} unresponsive: {e}")
                            
                    threading.Thread(target=dispatch, daemon=True).start()

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(b'{"status":"COMMAND_DISPATCHED"}')
            except Exception: 
                self.send_error(400)

if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), MasterDiscoveryEngine) as httpd:
        print("=============================================================")
        print("🛰️  PROJECT VIGIL: Master Off-Grid Open Controller Hub v2.1")
        print("=============================================================")
        print(f"🔌 [SERVICE RUNTIME] Core interception net active on port: {PORT}")
        httpd.serve_forever()

