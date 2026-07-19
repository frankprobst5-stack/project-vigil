#!/bin/bash
echo "📡 [EMULATOR ACTIVE] Dispatched localized hardware heartbeat signals..."

while true; do
    curl -X POST -H "Content-Type: application/json" \
        -d '{"device_id":"BARN_FRIDGE_PLUG","type":"SONOFF_TASMOTA","ip":"192.168.11.75","state":"ON"}' \
        http://localhost:8085/api/register
    echo " ✓ Device heartbeats transmitted cleanly."
    sleep 4
done
