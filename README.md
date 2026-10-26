# 🛰️ PROJECT VIGIL // Sovereign Off-Grid Open Controller Hub v2.1

Project Vigil is a lightweight, local-first, off-grid smart home controller hub designed to run completely isolated from the commercial internet. Built explicitly to support open-source microcontrollers (ESP32/ESP8266) and network security cameras, it maps out a local command grid without tracking, cloud dependencies, or data leaks.

This software is released as 100% free software under the **GNU Affero General Public License v3.0 or later (AGPL-3.0-or-later)**.

---

## 🛠️ Out-of-the-Box Setup

Getting started takes less than a minute on Ubuntu or any Debian-based Linux distribution.

### 1. Unpack and Install
Open your terminal inside the project directory and run the automated installer:
```bash
chmod +x install.sh
./install.sh
```
This automatically updates system dependencies, provisions Python 3, sets up file structures, and configures the environment execution wrappers.

### 2. Launch the Matrix

**Within Citadel** (this embedded copy's actual deployment), Vigil runs as
Citadel's own `vigil` Docker service -- see the root `docker-compose.yml`
and `ROADMAP.md` Phase D, not a standalone launcher script.

---

## 🔌 Real Hardware Control (added 2026-09-13)

`vigil_kernel.py` includes a real adapter registry for controlling
devices found in the registry, targeting each ecosystem's own documented
local API (no cloud account, no vendor app):

| Protocol | Docs verified against |
|---|---|
| `tasmota` | https://tasmota.github.io/docs/Commands/#power |
| `shelly_gen1` | https://shelly-api-docs.shelly.cloud/gen1/#shelly-relay-0-1 |
| `shelly_gen2` | https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/Switch/ |
| `esphome` | https://esphome.io/web-api/ (needs the device's `web_server:` component enabled) |
| `zigbee2mqtt` | https://www.zigbee2mqtt.io/guide/usage/mqtt_topics_and_messages.html |

**Honest status:** these are written and unit-tested against each
protocol's real documented API shape, but none have been verified
against real physical hardware as of this writing. If you're trying one
of these against a real device, please report back what does and
doesn't work.

To wire a registered device to a real adapter, include `protocol` (and
any `adapter_args` the adapter needs -- see each function's docstring in
`vigil_kernel.py`) in its registration payload:
```json
{
  "device_id": "LIVING_ROOM_SWITCH",
  "ip": "192.168.1.105",
  "type": "Smart Power Relay",
  "state": "OFF",
  "protocol": "tasmota",
  "adapter_args": {"relay": 1}
}
```
Leave `protocol` out (or empty) to keep a device registry-only, with no
real hardware control -- this is the default, and matches this file's
original behavior before adapters existed.

**Not supported, and not planned: Blink and SimpliSafe.** Both are
closed cloud ecosystems with no supported local API. This isn't a gap
waiting to be closed -- don't buy either expecting it to work here.

### Local Network Discovery

`GET /api/discover` (proxied by Citadel's cockpit as
`/api/vigil/discover`) scans your LAN via mDNS for Tasmota, Shelly, and
ESPHome devices (~4 seconds) and reports whatever it actually finds. An
empty result on a network with none of that hardware yet is the correct,
honest answer -- not a bug.

---

## 🛰️ Local API Binding Specifications

Your physical open-source hardware nodes (smart plugs, relays, sensors, and video feeds) connect to Project Vigil by dispatching a localized network registration heartbeat package via an HTTP POST payload.

* **Target Destination Route:** `http://<YOUR_CONTROLLER_IP>:8085/api/register`
* **Content-Type Header Required:** `application/json`

### Hardware Registration Payload Examples

#### A. Relay / Smart Switch Node
```json
{
  "device_id": "LIVING_ROOM_SWITCH",
  "ip": "192.168.1.105",
  "type": "Smart Power Relay",
  "state": "OFF"
}
```

#### B. Security Camera / Surveillance Node
```json
{
  "device_id": "PERIMETER_CAM_01",
  "ip": "192.168.1.110",
  "type": "Surveillance Node",
  "state": "ACTIVE",
  "stream_url": "http://192.168.1"
}
```

---

## 🛡️ License

Project Vigil is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version. See the `LICENSE` file for more details.

