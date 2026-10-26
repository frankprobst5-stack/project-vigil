"""Real unit tests for vigil_kernel.py -- covers everything that doesn't
need actual physical hardware: adapter URL/payload construction (checked
against each protocol's real, cited docs), the honest-default dispatch
behavior in send_hardware_command(), the registry/toggle HTTP handlers,
and the automation decision logic. Does NOT verify the adapters actually
control real devices -- no such hardware exists to test against as of
this writing (see vigil_kernel.py's own top-of-file note); that's for a
real tester with real hardware to confirm.
"""
import json
import unittest
from unittest.mock import patch, MagicMock

import vigil_kernel as vk


class AdapterUrlConstructionTests(unittest.TestCase):
    """Each assertion mirrors the exact syntax from that adapter's cited
    official doc page -- see vigil_kernel.py's docstrings for the links."""

    @patch("vigil_kernel._http_get")
    def test_tasmota_default_relay(self, mock_get):
        mock_get.return_value = (200, b'{"POWER":"ON"}')
        vk.adapter_tasmota("192.168.1.50", "ON")
        mock_get.assert_called_once_with("http://192.168.1.50/cm?cmnd=Power%20ON")

    @patch("vigil_kernel._http_get")
    def test_tasmota_numbered_relay(self, mock_get):
        mock_get.return_value = (200, b'{"POWER2":"OFF"}')
        vk.adapter_tasmota("192.168.1.50", "OFF", relay=2)
        mock_get.assert_called_once_with("http://192.168.1.50/cm?cmnd=Power2%20OFF")

    @patch("vigil_kernel._http_get")
    def test_shelly_gen1(self, mock_get):
        mock_get.return_value = (200, b'{"ison":true}')
        vk.adapter_shelly_gen1("192.168.1.51", "ON", relay=0)
        mock_get.assert_called_once_with("http://192.168.1.51/relay/0?turn=on")

    @patch("vigil_kernel._http_get")
    def test_shelly_gen2(self, mock_get):
        mock_get.return_value = (200, b'{"was_on":false}')
        vk.adapter_shelly_gen2("192.168.1.52", "ON", relay=0)
        mock_get.assert_called_once_with("http://192.168.1.52/rpc/Switch.Set?id=0&on=true")

    @patch("vigil_kernel._http_post")
    def test_esphome(self, mock_post):
        mock_post.return_value = (200, b'')
        vk.adapter_esphome("192.168.1.53", "ON", entity="Porch Light")
        mock_post.assert_called_once_with("http://192.168.1.53/switch/Porch%20Light/turn_on")

    def test_esphome_requires_entity(self):
        with self.assertRaises(ValueError):
            vk.adapter_esphome("192.168.1.53", "ON")

    @patch("paho.mqtt.publish.single")
    def test_zigbee2mqtt(self, mock_publish):
        vk.adapter_zigbee2mqtt("living_room_plug", "ON", mqtt_host="192.168.1.10")
        mock_publish.assert_called_once_with(
            "zigbee2mqtt/living_room_plug/set",
            payload=json.dumps({"state": "ON"}),
            hostname="192.168.1.10",
            port=1883,
        )

    def test_zigbee2mqtt_requires_broker_host(self):
        with self.assertRaises(ValueError):
            vk.adapter_zigbee2mqtt("living_room_plug", "ON")


class SendHardwareCommandTests(unittest.TestCase):
    def test_no_protocol_configured_is_honest_not_silent(self):
        ok, detail = vk.send_hardware_command({"ip": "1.2.3.4"}, "ON")
        self.assertFalse(ok)
        self.assertIn("no protocol configured", detail)

    def test_unknown_protocol_is_honest(self):
        ok, detail = vk.send_hardware_command({"ip": "1.2.3.4", "protocol": "nonexistent_brand"}, "ON")
        self.assertFalse(ok)
        self.assertIn("unknown protocol", detail)

    @patch.dict(vk.ADAPTERS, {"tasmota": MagicMock(return_value=(200, b"ok"))})
    def test_dispatches_to_correct_adapter_with_args(self):
        ok, detail = vk.send_hardware_command(
            {"ip": "1.2.3.4", "protocol": "TASMOTA", "adapter_args": {"relay": 2}}, "ON"
        )
        self.assertTrue(ok)
        vk.ADAPTERS["tasmota"].assert_called_once_with("1.2.3.4", "ON", relay=2)

    @patch.dict(vk.ADAPTERS, {"tasmota": MagicMock(side_effect=TimeoutError("device unreachable"))})
    def test_adapter_exception_becomes_honest_failure_not_a_crash(self):
        ok, detail = vk.send_hardware_command({"ip": "1.2.3.4", "protocol": "tasmota"}, "ON")
        self.assertFalse(ok)
        self.assertIn("device unreachable", detail)


class AutomationCycleTests(unittest.TestCase):
    def setUp(self):
        vk.system_state.update({
            "solar_battery_soc": 100,
            "secondary_power_bus": "ON",
            "smart_plug_fridge": "ON",
            "perimeter_tripline": "SECURE",
            "perimeter_lights": "OFF",
        })
        vk.discovered_devices.clear()

    @patch("vigil_kernel.save_state_to_disk")
    def test_low_battery_sheds_secondary_load(self, mock_save):
        vk.system_state["solar_battery_soc"] = 10
        changed = vk.run_automation_cycle()
        self.assertTrue(changed)
        self.assertEqual(vk.system_state["secondary_power_bus"], "OFF")
        self.assertEqual(vk.system_state["smart_plug_fridge"], "OFF")

    @patch("vigil_kernel.save_state_to_disk")
    def test_recovered_battery_restores_load(self, mock_save):
        vk.system_state["solar_battery_soc"] = 50
        vk.system_state["secondary_power_bus"] = "OFF"
        changed = vk.run_automation_cycle()
        self.assertTrue(changed)
        self.assertEqual(vk.system_state["secondary_power_bus"], "ON")

    @patch("vigil_kernel.save_state_to_disk")
    def test_mid_range_battery_is_a_no_op(self, mock_save):
        vk.system_state["solar_battery_soc"] = 30
        changed = vk.run_automation_cycle()
        self.assertFalse(changed)
        mock_save.assert_not_called()

    @patch("vigil_kernel.save_state_to_disk")
    def test_tripline_triggers_lights_and_dispatches_to_registered_role(self, mock_save):
        vk.discovered_devices["front_lights"] = {
            "ip": "1.2.3.4", "protocol": "tasmota", "role": "perimeter_lights",
        }
        vk.system_state["perimeter_tripline"] = "TRIPPED"
        with patch.dict(vk.ADAPTERS, {"tasmota": MagicMock(return_value=(200, b""))}):
            changed = vk.run_automation_cycle()
            self.assertTrue(changed)
            self.assertEqual(vk.system_state["perimeter_lights"], "ON")
            vk.ADAPTERS["tasmota"].assert_called_once_with("1.2.3.4", "ON")

    @patch("vigil_kernel.save_state_to_disk")
    def test_tripline_trigger_with_no_registered_device_is_honest_not_silent_crash(self, mock_save):
        # No device has role=perimeter_lights -- should update system_state
        # (so the UI shows lights "should" be on) without raising, since
        # send_hardware_command has nothing to dispatch to.
        vk.system_state["perimeter_tripline"] = "TRIPPED"
        changed = vk.run_automation_cycle()
        self.assertTrue(changed)
        self.assertEqual(vk.system_state["perimeter_lights"], "ON")

    @patch("vigil_kernel.save_state_to_disk")
    def test_secure_after_tripped_resets_lights(self, mock_save):
        vk.system_state["perimeter_tripline"] = "SECURE"
        vk.system_state["perimeter_lights"] = "ON"
        changed = vk.run_automation_cycle()
        self.assertTrue(changed)
        self.assertEqual(vk.system_state["perimeter_lights"], "OFF")


class RegistryHandlerTests(unittest.TestCase):
    """Exercises the do_GET/do_POST logic directly (not over a real
    socket) by calling the handler's methods on a constructed instance,
    same technique already used for BaseHTTPRequestHandler subclasses in
    this project's style elsewhere."""

    def setUp(self):
        vk.discovered_devices.clear()

    def _make_handler(self, path, method="GET", body=None):
        handler = vk.VigilAPIHandler.__new__(vk.VigilAPIHandler)
        handler.path = path
        handler.command = method
        handler.headers = {"Content-Length": str(len(body or b""))}
        handler.rfile = MagicMock()
        handler.rfile.read.return_value = body or b""
        handler.wfile = MagicMock()
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.send_error = MagicMock()
        handler.end_headers = MagicMock()
        return handler

    @patch("vigil_kernel.save_grid_state")
    def test_register_new_device_defaults_to_no_protocol(self, mock_save):
        handler = self._make_handler(
            "/api/register", "POST",
            json.dumps({"device_id": "porch", "ip": "1.2.3.4", "type": "Smart Plug"}).encode(),
        )
        handler.do_POST()
        self.assertEqual(vk.discovered_devices["porch"]["protocol"], "")
        handler.send_error.assert_not_called()
        mock_save.assert_called_once()

    @patch("vigil_kernel.save_grid_state")
    def test_toggle_unknown_device_returns_404_not_a_crash(self, mock_save):
        handler = self._make_handler(
            "/api/toggle", "POST", json.dumps({"device_id": "nonexistent"}).encode(),
        )
        handler.do_POST()
        handler.wfile.write.assert_called_once()
        body = json.loads(handler.wfile.write.call_args[0][0])
        self.assertEqual(body["status"], "error")

    @patch("vigil_kernel.save_grid_state")
    def test_toggle_registry_only_device_reports_honest_hardware_ok_false(self, mock_save):
        vk.discovered_devices["porch"] = {"ip": "1.2.3.4", "type": "Smart Plug", "state": "OFF", "protocol": ""}
        handler = self._make_handler(
            "/api/toggle", "POST", json.dumps({"device_id": "porch"}).encode(),
        )
        handler.do_POST()
        body = json.loads(handler.wfile.write.call_args[0][0])
        self.assertEqual(body["status"], "COMMAND_DISPATCHED")
        self.assertFalse(body["hardware_ok"])
        self.assertIn("no protocol configured", body["detail"])
        self.assertEqual(vk.discovered_devices["porch"]["state"], "ON")


if __name__ == "__main__":
    unittest.main()
