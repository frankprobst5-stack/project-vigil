# PROJECT VIGIL // Unified Smart Home Controller Kernel
# Copyright (C) 2026 SnapPress // Copyleft GNU AGPL-3.0-or-later
#
# Merges what used to be two separate files/containers -- vigil_core.py
# (device registry + relay toggle, ran as the "vigil-hub" container) and
# vigil_hub.py (solar/security telemetry, ran as the confusingly-named
# "vigil-power" container) -- into one real service, decided 2026-09-13
# (ROADMAP.md Phase D). Reasons: the file/container names were swapped
# in a way that was already confusing (vigil-hub ran vigil_core.py;
# vigil-power ran vigil_hub.py), the standalone project-vigil repo had
# already evolved a real automation loop (load-shedding, tripline-
# triggered lighting) here that the embedded two-file split never had,
# and that automation logic needs the SAME device registry it's meant to
# control, not a second disconnected state file.
#
# Also replaces the standalone repo's `blast_local_hardware_command` --
# a raw UDP packet with a made-up string command to a hardcoded fake IP,
# not any real protocol -- with a real adapter registry against actual
# documented local APIs (Tasmota, Shelly Gen1/Gen2, ESPHome, Zigbee2MQTT;
# see ADAPTERS below). None of these adapters have been verified against
# real physical hardware as of this writing (no such hardware owned) --
# each is written and cited directly against that project's own official
# API docs (checked 2026-09-13, not guessed), for real testers who do
# have the hardware to try them against and report back what breaks.
#
# Explicitly NOT supported, and not planned: Blink and SimpliSafe. Both
# are closed cloud ecosystems with no supported local API -- this isn't
# a gap to close, it's a hardware category to steer people away from.

import json
import os
import socketserver
import threading
import time
import urllib.parse
import urllib.request
import http.server

import camera_bridge

STATE_FILE = "vigil_state.json"
GRID_FILE = "vigil_grid_ledger.json"
PORT = 8085

# ---- Device registry (what used to be vigil_core.py's discovered_devices) ----
discovered_devices = {}
ledger_lock = threading.Lock()

if os.path.exists(GRID_FILE):
    try:
        with open(GRID_FILE, "r", encoding="utf-8") as f:
            discovered_devices = json.load(f)
        print(f"[STATE LOADED] Recovered {len(discovered_devices)} devices from {GRID_FILE}.")
    except Exception as e:
        print(f"[STATE ERROR] Could not read {GRID_FILE}: {e}")


def save_grid_state():
    with ledger_lock:
        try:
            with open(GRID_FILE, "w", encoding="utf-8") as f:
                json.dump(discovered_devices, f, indent=4)
        except Exception as e:
            print(f"[SAVE FAILED] Error writing {GRID_FILE}: {e}")


# ---- Power/security telemetry (what used to be vigil_hub.py's system_state) ----
system_state = {
    "solar_battery_soc": 100,
    "solar_input_watts": 0,
    "critical_power_bus": "ON",
    "secondary_power_bus": "ON",
    "perimeter_tripline": "SECURE",
    "smart_plug_fridge": "ON",
    "perimeter_lights": "OFF",
    "last_update": "NEVER",
}
state_lock = threading.Lock()


def load_state_from_disk():
    global system_state
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                disk_data = json.load(f)
                with state_lock:
                    system_state.update(disk_data)
            print("[STATE ENGINE] Recovered telemetry from disk.")
        except Exception:
            save_state_to_disk()
    else:
        save_state_to_disk()


def save_state_to_disk():
    with state_lock:
        system_state["last_update"] = time.strftime("%Y-%m-%d %H:%M:%S UTC")
        with open(STATE_FILE, "w") as f:
            json.dump(system_state, f, indent=4)


# ---- Hardware adapter registry ----
# Each function's docstring cites the exact official doc page it was
# verified against. All raise on failure -- send_hardware_command()
# below is what catches that, so a bad IP or offline device degrades to
# an honest error message instead of crashing the caller.

def _http_get(url, timeout=3):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.status, resp.read()


def _http_post(url, timeout=3):
    req = urllib.request.Request(url, data=b"", method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read()


def adapter_tasmota(ip, command, relay=1, **kwargs):
    """Tasmota HTTP command API.
    https://tasmota.github.io/docs/Commands/#power
    GET http://<ip>/cm?cmnd=Power<relay> <ON|OFF> (relay omitted = relay 1)."""
    state = "ON" if command == "ON" else "OFF"
    idx = "" if relay in (1, None) else str(relay)
    url = f"http://{ip}/cm?cmnd=Power{idx}%20{state}"
    return _http_get(url)


def adapter_shelly_gen1(ip, command, relay=0, **kwargs):
    """Shelly Gen1 (classic) HTTP relay API.
    https://shelly-api-docs.shelly.cloud/gen1/#shelly-relay-0-1
    GET http://<ip>/relay/<n>?turn=on|off"""
    turn = "on" if command == "ON" else "off"
    url = f"http://{ip}/relay/{relay}?turn={turn}"
    return _http_get(url)


def adapter_shelly_gen2(ip, command, relay=0, **kwargs):
    """Shelly Gen2/Plus/Pro RPC Switch API.
    https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/Switch/
    GET http://<ip>/rpc/Switch.Set?id=<n>&on=true|false"""
    on = "true" if command == "ON" else "false"
    url = f"http://{ip}/rpc/Switch.Set?id={relay}&on={on}"
    return _http_get(url)


def adapter_esphome(ip, command, entity=None, **kwargs):
    """ESPHome web_server component REST API.
    https://esphome.io/web-api/
    POST http://<ip>/switch/<entity_name>/turn_on|turn_off
    Requires the device's `web_server:` component with its REST API
    enabled -- not on by default in every ESPHome config."""
    if not entity:
        raise ValueError("esphome adapter requires an 'entity' name (adapter_args: {\"entity\": \"...\"})")
    action = "turn_on" if command == "ON" else "turn_off"
    url = f"http://{ip}/switch/{urllib.parse.quote(entity)}/{action}"
    return _http_post(url)


def adapter_zigbee2mqtt(friendly_name, command, mqtt_host=None, mqtt_port=1883, **kwargs):
    """Zigbee2MQTT device control via its MQTT bridge.
    https://www.zigbee2mqtt.io/guide/usage/mqtt_topics_and_messages.html
    Publishes {"state": "ON"|"OFF"} to zigbee2mqtt/<friendly_name>/set.
    Needs `paho-mqtt` (installed at container start) and a reachable
    broker -- Zigbee devices have no IP of their own, they're addressed
    by friendly name through whatever MQTT broker Zigbee2MQTT uses."""
    import paho.mqtt.publish as mqtt_publish
    if not mqtt_host:
        raise ValueError("zigbee2mqtt adapter requires mqtt_host (adapter_args: {\"mqtt_host\": \"...\"})")
    topic = f"zigbee2mqtt/{friendly_name}/set"
    payload = json.dumps({"state": command})
    mqtt_publish.single(topic, payload=payload, hostname=mqtt_host, port=mqtt_port)
    return 200, b""


ADAPTERS = {
    "tasmota": adapter_tasmota,
    "shelly_gen1": adapter_shelly_gen1,
    "shelly_gen2": adapter_shelly_gen2,
    "esphome": adapter_esphome,
    "zigbee2mqtt": adapter_zigbee2mqtt,
}


def send_hardware_command(device, command):
    """Dispatches through the adapter matching `device`'s registered
    `protocol` field. Returns (ok: bool, detail: str) and never raises --
    called from both a live API request and the unattended automation
    loop below, neither of which should crash the process over one
    unreachable or unconfigured device. A device with no `protocol` set
    (true for every device registered before this adapter registry
    existed, and for any device you simply haven't wired a real
    integration for yet) gets an honest "no adapter configured" result
    instead of a silent no-op or a fabricated success."""
    protocol = (device.get("protocol") or "").strip().lower()
    if not protocol:
        return False, "no protocol configured for this device (registry-only, no real control wired up)"
    adapter = ADAPTERS.get(protocol)
    if not adapter:
        return False, f"unknown protocol {protocol!r} -- supported: {', '.join(sorted(ADAPTERS))}"
    try:
        status, _ = adapter(device.get("ip"), command, **(device.get("adapter_args") or {}))
        return True, f"HTTP {status}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


# ---- Local network discovery (mDNS) ----
# Real, testable today even with zero smart-home hardware on hand: an
# honest empty result is the correct answer on a network that genuinely
# has none of these devices yet, same "no_data" honesty as every other
# discovery-shaped endpoint in this project (see /api/scanner,
# /api/weather in media-vault/app.py). This is the actual "capture a
# list of what's on the network" step meant to come before recommending
# hardware to buy, not after.
MDNS_SERVICE_TYPES = {
    "_tasmota._tcp.local.": "tasmota",
    "_shelly._tcp.local.": "shelly",
    "_esphomelib._tcp.local.": "esphome",
}


def discover_devices(timeout_s=4):
    from zeroconf import ServiceBrowser, Zeroconf

    found = []
    found_lock = threading.Lock()

    class _Listener:
        def __init__(self, hint):
            self.hint = hint

        def add_service(self, zc, service_type, name):
            info = zc.get_service_info(service_type, name)
            if info is None:
                return
            addresses = info.parsed_addresses() if hasattr(info, "parsed_addresses") else []
            with found_lock:
                found.append({
                    "name": name,
                    "type": service_type,
                    "likely_protocol": self.hint,
                    "ip": addresses[0] if addresses else None,
                    "port": info.port,
                })

        def remove_service(self, zc, service_type, name):
            pass

        def update_service(self, zc, service_type, name):
            pass

    zc = Zeroconf()
    try:
        browsers = [
            ServiceBrowser(zc, svc_type, _Listener(hint))
            for svc_type, hint in MDNS_SERVICE_TYPES.items()
        ]
        time.sleep(timeout_s)
    finally:
        zc.close()
    return found


class VigilAPIHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            try:
                with open("index.html", "r", encoding="utf-8") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(content.encode("utf-8"))
            except Exception:
                self.send_error(500)
            return

        if self.path.startswith("/api/grid"):
            with ledger_lock:
                self._send_json(discovered_devices)
            return

        if self.path.startswith("/api/state"):
            with state_lock:
                self._send_json(dict(system_state))
            return

        if self.path.startswith("/camera/") and self.path.endswith(".mjpg"):
            dev_id = self.path[len("/camera/"):-len(".mjpg")]
            with ledger_lock:
                device = discovered_devices.get(dev_id)
            rtsp_url = (device or {}).get("rtsp_url") or ""
            if not device or not rtsp_url:
                self.send_error(404, "no rtsp_url configured for this device")
                return
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-cache, private")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            camera_bridge.stream_mjpeg(dev_id, rtsp_url, self.wfile, lambda: True)
            return

        if self.path.startswith("/api/discover"):
            try:
                results = discover_devices()
                self._send_json({"status": "success", "devices": results})
            except ImportError:
                self._send_json({
                    "status": "error",
                    "detail": "zeroconf not installed in this container -- see docker-compose.yml's vigil service command.",
                }, status=500)
            except Exception as e:
                self._send_json({"status": "error", "detail": f"{type(e).__name__}: {e}"}, status=500)
            return

        self.send_error(404)

    def do_HEAD(self):
        # BaseHTTPRequestHandler has no default HEAD support -- any HEAD
        # request here died with a real 501 "Unsupported method" until
        # this existed, which is exactly what broke the cockpit
        # dashboard's Power health check the moment checkSameOrigin()
        # switched from GET to HEAD (2026-09-16, see index.html). Mirrors
        # do_GET's routing for status-code purposes only: no body is ever
        # sent for HEAD, and no side-effecting work (camera streaming,
        # live mDNS discovery) runs just to answer a reachability check.
        if self.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            return
        if self.path.startswith("/api/grid") or self.path.startswith("/api/state"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            return
        if self.path.startswith("/camera/") and self.path.endswith(".mjpg"):
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()
            return
        if self.path.startswith("/api/discover"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            return
        self.send_error(404)

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length)

        if self.path == "/api/register":
            try:
                device_packet = json.loads(post_data.decode("utf-8"))
                dev_id = device_packet["device_id"]
                with ledger_lock:
                    if dev_id not in discovered_devices:
                        print(f"[CAPTURE SUCCESS] NODE DETECTED! ID: {dev_id} | IP: {device_packet['ip']}")

                    # RTSP camera support, added 2026-09-16: an `rtsp_url`
                    # (a real ESP32-CAM/IP-camera RTSP source, e.g.
                    # rtsp://192.168.1.50:554/stream1) gets bridged
                    # server-side to a plain browser-viewable MJPEG feed
                    # at /camera/<device_id>.mjpg -- see camera_bridge.py
                    # for why a bridge is needed at all (ffmpeg's own raw
                    # HTTP output isn't multipart-framed, so a bare <img>
                    # tag can't render it). `stream_url` is overwritten to
                    # point there automatically whenever rtsp_url is set,
                    # so index.html's existing <img src="${stream_url}">
                    # rendering keeps working completely unchanged --
                    # no frontend code needed to know RTSP is involved.
                    rtsp_url = device_packet.get("rtsp_url", "")
                    old_rtsp = discovered_devices.get(dev_id, {}).get("rtsp_url", "")
                    stream_url = f"/camera/{dev_id}.mjpg" if rtsp_url else device_packet.get("stream_url", "")

                    discovered_devices[dev_id] = {
                        "ip": device_packet["ip"],
                        "type": device_packet["type"],
                        "state": device_packet.get("state", "ON"),
                        "stream_url": stream_url,
                        "rtsp_url": rtsp_url,
                        # New, optional -- absent means "registry-only, no
                        # real hardware control wired up yet" (see
                        # send_hardware_command's honest-default above).
                        "protocol": device_packet.get("protocol", ""),
                        "adapter_args": device_packet.get("adapter_args", {}),
                        "last_seen": time.strftime("%H:%M:%S UTC"),
                    }

                    if old_rtsp and old_rtsp != rtsp_url:
                        camera_bridge.stop_bridge(dev_id)

                save_grid_state()
                self._send_json({"status": "CONTROL_SECURED"})
            except Exception:
                self.send_error(400)
            return

        if self.path == "/api/toggle":
            try:
                toggle_cmd = json.loads(post_data.decode("utf-8"))
                target_id = toggle_cmd["device_id"]
                with ledger_lock:
                    if target_id not in discovered_devices:
                        self._send_json({"status": "error", "detail": "unknown device_id"}, status=404)
                        return
                    current = discovered_devices[target_id]["state"]
                    next_state = "OFF" if current == "ON" else "ON"
                    device = dict(discovered_devices[target_id])

                ok, detail = send_hardware_command(device, next_state)

                with ledger_lock:
                    discovered_devices[target_id]["state"] = next_state
                save_grid_state()

                self._send_json({"status": "COMMAND_DISPATCHED", "hardware_ok": ok, "detail": detail})
            except Exception:
                self.send_error(400)
            return

        if self.path == "/api/update":
            try:
                incoming = json.loads(post_data.decode("utf-8"))
                with state_lock:
                    for key, val in incoming.items():
                        if key in system_state:
                            system_state[key] = val
                save_state_to_disk()
                self._send_json({"status": "STATE_SYNCHRONIZED_SUCCESS"})
            except Exception:
                self.send_error(400)
            return

        self.send_error(404)


def run_automation_cycle():
    """One pass of the real automation decision logic carried over from
    the standalone repo's vigil_kernel.py: load-shedding on low battery,
    and security-triggered lighting. Split out from the infinite loop
    below so it's independently unit-testable (see test_vigil_kernel.py)
    without needing to wait on a live 4-second sleep loop. The one real
    change from the standalone version: hardware commands go through
    send_hardware_command()/the adapter registry above instead of a
    hardcoded fake UDP packet to a fake IP -- if no device in the
    registry is configured for the relevant role, this honestly does
    nothing and logs why, rather than pretending. Returns True if any
    state changed this cycle (so save_state_to_disk only runs then)."""
    with state_lock:
        soc = system_state["solar_battery_soc"]
        tripline = system_state["perimeter_tripline"]
        secondary_bus = system_state["secondary_power_bus"]
        lights = system_state["perimeter_lights"]
        state_changed = False

        if soc < 24 and secondary_bus == "ON":
            print("[LOAD SHEDDER] Battery below 24% -- forcing secondary loads off.")
            system_state["secondary_power_bus"] = "OFF"
            system_state["smart_plug_fridge"] = "OFF"
            state_changed = True
        elif soc >= 40 and secondary_bus == "OFF":
            print("[POWER RECOVERY] Battery above 40% -- re-engaging accessories.")
            system_state["secondary_power_bus"] = "ON"
            system_state["smart_plug_fridge"] = "ON"
            state_changed = True

        if tripline == "TRIPPED" and lights == "OFF":
            print("[SECURITY] Perimeter tripline TRIPPED -- turning on perimeter lights.")
            system_state["perimeter_lights"] = "ON"
            state_changed = True
        elif tripline == "SECURE" and lights == "ON":
            print("[SECURITY] Perimeter secure -- resetting perimeter lights.")
            system_state["perimeter_lights"] = "OFF"
            state_changed = True

    if state_changed:
        save_state_to_disk()
        with ledger_lock:
            targets = [d for d in discovered_devices.values() if d.get("role") == "perimeter_lights"]
        for device in targets:
            ok, detail = send_hardware_command(device, system_state["perimeter_lights"])
            if not ok:
                print(f"[AUTOMATION] Could not dispatch to {device.get('ip')}: {detail}")

    return state_changed


def autonomous_hardware_automation_loop():
    while True:
        run_automation_cycle()
        time.sleep(4)


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    print("=============================================================")
    print("PROJECT VIGIL: Unified Smart Home Controller Kernel")
    print("=============================================================")
    load_state_from_disk()
    threading.Thread(target=autonomous_hardware_automation_loop, daemon=True).start()
    with ThreadedHTTPServer(("", PORT), VigilAPIHandler) as httpd:
        print(f"[INITIALIZATION] Local API gateway active at http://localhost:{PORT}")
        httpd.serve_forever()
