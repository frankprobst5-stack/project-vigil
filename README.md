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
To launch the entire dashboard infrastructure, initialize background server workers, and fire up your offline browser interface instantly, execute the unified launcher:
```bash
./launch_matrix.sh
```

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

