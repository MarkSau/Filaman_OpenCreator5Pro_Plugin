"""Focused tests against the shipped methods without Moonraker/FilaMan imports."""
import ast
import asyncio
import json
import logging
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from urllib.parse import quote, urlparse

ROOT = Path(__file__).resolve().parents[1]


def extract(path, class_name, names, namespace, bases=None):
    tree = ast.parse(path.read_text())
    cls = next(node for node in tree.body
               if isinstance(node, ast.ClassDef) and node.name == class_name)
    methods = [node for node in cls.body
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
               and node.name in names]
    assert {node.name for node in methods} == set(names)
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[
        ast.alias(name="annotations")], level=0),
        ast.ClassDef(name="Probe", bases=bases or [], keywords=[], body=methods,
                     decorator_list=[])], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(path), "exec"), namespace)
    return namespace["Probe"]


Component = extract(ROOT / "moonraker/filaman.py", "FilaManManager",
                    ["_discover_filament_sensors", "_sensor_to_extruder",
                     "_push_spool_to_printer"], {"logging": logging, "re": re})
Driver = extract(ROOT / "moonraker_filaman/driver.py", "Driver",
                 ["_discover_slots"], {
                     "re": re,
                     "AFC_LANE_PREFIX": "afc_stepper ",
                     "MMU_GATE_PREFIX": "mmu_gate ",
                     "_name_matches": lambda name, needle, prefix:
                         name.casefold().startswith(needle.casefold()) if prefix
                         else name.casefold() == needle.casefold(),
                     "logger": logging.getLogger(__name__),
                 })


class FakeBase:
    def __init__(self, printer_id, config, emitter):
        self.printer_id = printer_id


InitDriver = extract(
    ROOT / "moonraker_filaman/driver.py", "Driver", ["__init__", "_validate_url"],
    {"asyncio": asyncio, "urlparse": urlparse,
     "logger": logging.getLogger(__name__), "FakeBase": FakeBase,
     "DEFAULT_AUTO_ASSIGN_CONFIRM": "sensor",
     "AUTO_ASSIGN_CONFIRM_VALUES": ("sensor", "immediate", "off"),
     "DEFAULT_SENSOR_TIMEOUT_SECONDS": 300,
     "MIN_SENSOR_TIMEOUT_SECONDS": 10, "MAX_SENSOR_TIMEOUT_SECONDS": 3600},
    bases=[ast.Name(id="FakeBase", ctx=ast.Load())],
)
InitDriver._normalize_slot_targets = lambda self, config: []
InitDriver._build_initial_slots = lambda self: []

AfcDriver = extract(
    ROOT / "moonraker_filaman/driver.py", "Driver",
    ["_refresh_standalone_afc", "refresh_status", "assign_pending_spool", "_complete_pending_assignment",
     "_slot_extruder", "_slot_to_ids", "_find_slot"],
    {"quote": quote, "logger": logging.getLogger(__name__),
     "_name_matches": lambda name, needle, prefix:
         name.casefold().startswith(needle.casefold()) if prefix
         else name.casefold() == needle.casefold(),
     "_now_iso": lambda: "now"},
)


class OpenCreatorTests(unittest.IsolatedAsyncioTestCase):
    def component(self):
        manager = Component()
        manager._known_extruders = {"extruder", "extruder1"}
        manager.sensor_map_override = {}
        manager.filament_sensors = {}
        return manager

    def test_tool_start_switch_wins_over_wheel_regardless_of_order(self):
        for objects in (
            ["filament_motion_sensor fm_ex0", "filament_switch_sensor extruder0_tool_start"],
            ["filament_switch_sensor extruder0_tool_start", "filament_motion_sensor fm_ex0"],
        ):
            manager = self.component()
            manager._discover_filament_sensors(objects)
            self.assertEqual(manager.filament_sensors,
                             {"filament_switch_sensor extruder0_tool_start": "extruder"})

    def test_override_does_not_fall_back_to_wrong_sensor(self):
        manager = self.component()
        manager.sensor_map_override = {"extruder": "extruder0_tool_start"}
        manager._discover_filament_sensors(["filament_motion_sensor fm_ex0"])
        self.assertEqual(manager.filament_sensors, {})

    def test_motion_sensor_not_used_implicitly_when_switch_missing(self):
        manager = self.component()
        manager._discover_filament_sensors(["filament_motion_sensor fm_ex0"])
        self.assertEqual(manager.filament_sensors, {})

    def test_explicit_mapping_wins_over_switch(self):
        manager = self.component()
        manager.sensor_map_override = {"extruder": "fm_ex0"}
        manager._discover_filament_sensors([
            "filament_switch_sensor extruder0_tool_start",
            "filament_motion_sensor fm_ex0",
        ])
        self.assertEqual(manager.filament_sensors,
                         {"filament_motion_sensor fm_ex0": "extruder"})

    async def test_no_metadata_request_when_object_absent(self):
        manager = self.component()
        manager._has_filament_detect = False
        manager.http_client = SimpleNamespace(request=AsyncMock())
        await manager._push_spool_to_printer("extruder", 123)
        await manager._push_spool_to_printer("extruder", None)
        manager.http_client.request.assert_not_awaited()

    async def test_metadata_clear_still_works_when_object_exists(self):
        manager = self.component()
        manager._has_filament_detect = True
        manager.server = SimpleNamespace(get_host_info=lambda: {"port": 7125})
        manager._extruder_to_channel = lambda extruder: 0
        manager._pushed_official = {}
        manager._reclaim_tries = {}
        response = SimpleNamespace(has_error=lambda: False)
        manager.http_client = SimpleNamespace(request=AsyncMock(return_value=response))
        await manager._push_spool_to_printer("extruder", None)
        self.assertEqual(manager.http_client.request.await_args.kwargs["body"],
                         {"channel": 0, "info": {}})

    def test_fila_man_default_does_not_create_virtual_trays(self):
        manifest = json.loads((ROOT / "moonraker_filaman/plugin.json").read_text())
        self.assertEqual(manifest["config_schema"]["properties"]["slot_count"]["default"], 1)

    def test_driver_identity_and_schema_match(self):
        manifest = json.loads((ROOT / "moonraker_filaman/plugin.json").read_text())
        tree = ast.parse((ROOT / "moonraker_filaman/driver.py").read_text())
        cls = next(node for node in tree.body
                   if isinstance(node, ast.ClassDef) and node.name == "Driver")
        key = next(node.value.value for node in cls.body if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == "driver_key"
                           for target in node.targets))
        self.assertEqual(manifest["plugin_key"], "opencreator_filaman")
        self.assertEqual(manifest["driver_key"], key)
        self.assertIn("opencreator_url", manifest["config_schema"]["required"])
        self.assertIn("opencreator_url", manifest["config_schema"]["properties"])

    def test_url_config_and_legacy_fallback(self):
        for config, expected in [
            ({"opencreator_url": "http://new.test/", "moonraker_url": "http://old.test"},
             "http://new.test"),
            ({"moonraker_url": "http://old.test/"}, "http://old.test"),
        ]:
            driver = InitDriver(1, config, lambda event: None)
            driver._validate_url()
            self.assertEqual(driver._moonraker_url, expected)
        with self.assertRaisesRegex(ValueError, "opencreator_url"):
            InitDriver(1, {"opencreator_url": "invalid"}, lambda event: None)._validate_url()

    async def test_standalone_afc_lanes_are_not_feeder_trays(self):
        driver = Driver()
        driver._slot_targets = []
        driver._slot_count = 1
        driver._discover_objects = AsyncMock(return_value=[
            "extruder", "extruder1", "extruder2", "extruder3",
            "AFC_lane extruder0", "AFC_lane extruder1",
            "AFC_lane extruder2", "AFC_lane extruder3",
        ])
        driver._discover_tray_count_from_config = AsyncMock(return_value=0)
        slots = await driver._discover_slots()
        self.assertEqual([slot["toolhead_name"] for slot in slots],
                         ["extruder", "extruder1", "extruder2", "extruder3"])
        self.assertTrue(all(slot["slot_kind"] == "toolhead" for slot in slots))

    def afc_driver(self, lane_presence=(False, False, False, False)):
        driver = AfcDriver()
        driver.printer_id = 1
        driver._afc_objects = []
        driver._slots = []
        status = {}
        for index, present in enumerate(lane_presence):
            lane = f"extruder{index}"
            tool = "extruder" if index == 0 else lane
            lane_obj = f"AFC_lane {lane}"
            extruder_obj = f"AFC_extruder {lane}"
            driver._afc_objects.extend([lane_obj, extruder_obj])
            status[lane_obj] = {"name": lane, "extruder": lane, "prep": present}
            status[extruder_obj] = {
                "is_standalone": True, "extruder_name": tool, "lanes": [lane]
            }
            driver._slots.append({
                "slot_index": f"0-{index}", "slot_kind": "toolhead",
                "toolhead_name": tool,
            })
        driver._afc_lanes = {}
        driver._afc_presence = {}
        driver._warn_once = Mock()
        driver._clear_warn_once = Mock()
        driver._unwrap_result = lambda data: data.get("result", data)
        driver._request = AsyncMock(return_value={"result": {"status": status}})
        return driver, status

    async def test_afc_maps_standalone_lanes_to_real_toolheads(self):
        driver, _ = self.afc_driver((False, True, False, True))
        await driver._refresh_standalone_afc()
        self.assertEqual(driver._afc_lanes, {
            "extruder": "extruder0", "extruder1": "extruder1",
            "extruder2": "extruder2", "extruder3": "extruder3",
        })
        self.assertEqual(driver._afc_presence, {
            "extruder": False, "extruder1": True,
            "extruder2": False, "extruder3": True,
        })
        self.assertEqual(driver._request.await_args.args[0], "GET")

    async def test_afc_refuses_incomplete_or_duplicate_mapping(self):
        driver, status = self.afc_driver()
        status["AFC_lane extruder0"] = {}
        status["AFC_extruder extruder1"]["extruder_name"] = "extruder2"
        await driver._refresh_standalone_afc()
        self.assertNotIn("extruder", driver._afc_lanes)
        self.assertNotIn("extruder2", driver._afc_lanes)
        self.assertEqual(driver._afc_lanes, {"extruder3": "extruder3"})

    async def test_afc_failure_clears_baseline_and_reports_error(self):
        driver, _ = self.afc_driver()
        await driver._refresh_standalone_afc()
        driver._request.side_effect = RuntimeError("offline")
        await driver._refresh_standalone_afc()
        self.assertEqual(driver._afc_presence, {})
        self.assertEqual(driver._afc_lanes, {})
        driver._warn_once.assert_called_once()

    async def test_afc_insertion_confirms_corresponding_tool_not_first(self):
        driver, status = self.afc_driver()
        await driver._refresh_standalone_afc()
        driver._filament_present = dict(driver._afc_presence)
        driver._active_spool_id = None
        driver._pending = {"spool_id": 10}
        driver._auto_assign_confirm = "sensor"
        driver._apply_extruder_spools = Mock(return_value=False)
        driver._emit_slots_update = Mock()
        driver._complete_pending_assignment = AsyncMock()
        status["AFC_lane extruder2"]["prep"] = True
        async def request(method, path):
            if path == "/server/filaman/status":
                return {"result": {"filaman_connected": True, "filament_present": {}}}
            return {"result": {"status": status}}
        driver._request = AsyncMock(side_effect=request)
        await driver.refresh_status()
        driver._complete_pending_assignment.assert_awaited_once_with("extruder2")

    async def test_simultaneous_afc_insertions_are_not_assigned(self):
        driver, status = self.afc_driver()
        await driver._refresh_standalone_afc()
        driver._filament_present = dict(driver._afc_presence)
        driver._active_spool_id = None
        driver._pending = {"spool_id": 10}
        driver._auto_assign_confirm = "sensor"
        driver._apply_extruder_spools = Mock(return_value=False)
        driver._emit_slots_update = Mock()
        driver._complete_pending_assignment = AsyncMock()
        status["AFC_lane extruder0"]["prep"] = True
        status["AFC_lane extruder2"]["prep"] = True
        async def request(method, path):
            if path == "/server/filaman/status":
                return {"result": {"filaman_connected": True, "filament_present": {}}}
            return {"result": {"status": status}}
        driver._request = AsyncMock(side_effect=request)
        await driver.refresh_status()
        driver._complete_pending_assignment.assert_not_awaited()

    async def test_component_and_afc_edges_are_considered_together(self):
        driver, status = self.afc_driver()
        await driver._refresh_standalone_afc()
        driver._filament_present = dict(driver._afc_presence)
        driver._active_spool_id = None
        driver._pending = {"spool_id": 10}
        driver._auto_assign_confirm = "sensor"
        driver._apply_extruder_spools = Mock(return_value=False)
        driver._emit_slots_update = Mock()
        driver._complete_pending_assignment = AsyncMock()
        status["AFC_lane extruder2"]["prep"] = True
        async def request(method, path):
            if path == "/server/filaman/status":
                return {"result": {
                    "filaman_connected": True,
                    "filament_present": {"extruder1": True},
                }}
            return {"result": {"status": status}}
        driver._request = AsyncMock(side_effect=request)
        await driver.refresh_status()
        driver._complete_pending_assignment.assert_not_awaited()

    async def test_component_presence_precedes_afc_fallback(self):
        driver, status = self.afc_driver()
        await driver._refresh_standalone_afc()
        driver._filament_present = dict(driver._afc_presence)
        driver._active_spool_id = None
        driver._pending = {"spool_id": 10}
        driver._auto_assign_confirm = "sensor"
        driver._apply_extruder_spools = Mock(return_value=False)
        driver._emit_slots_update = Mock()
        driver._complete_pending_assignment = AsyncMock()
        status["AFC_lane extruder2"]["prep"] = True
        async def request(method, path):
            if path == "/server/filaman/status":
                return {"result": {
                    "filaman_connected": True,
                    "filament_present": {"extruder2": False},
                }}
            return {"result": {"status": status}}
        driver._request = AsyncMock(side_effect=request)
        await driver.refresh_status()
        driver._complete_pending_assignment.assert_not_awaited()

    async def test_afc_recovery_does_not_invent_an_insertion(self):
        driver, status = self.afc_driver((True, False, False, False))
        driver._filament_present = {}
        driver._active_spool_id = None
        driver._pending = {"spool_id": 10}
        driver._auto_assign_confirm = "sensor"
        driver._apply_extruder_spools = Mock(return_value=False)
        driver._emit_slots_update = Mock()
        driver._complete_pending_assignment = AsyncMock()
        async def request(method, path):
            if path == "/server/filaman/status":
                return {"result": {"filaman_connected": True, "filament_present": {}}}
            return {"result": {"status": status}}
        driver._request = AsyncMock(side_effect=request)
        await driver.refresh_status()
        driver._complete_pending_assignment.assert_not_awaited()

    async def test_pending_slot_must_match_inserted_tool(self):
        driver, _ = self.afc_driver()
        driver._pending = {"spool_id": 10, "slot_index": "0-2"}
        driver.send_filament_to_tray = AsyncMock()
        driver._clear_pending = Mock()
        await driver._complete_pending_assignment("extruder1")
        driver.send_filament_to_tray.assert_not_awaited()
        driver._clear_pending.assert_not_called()

    async def test_pending_unknown_tool_does_not_assign_first_slot(self):
        driver, _ = self.afc_driver()
        driver._pending = {"spool_id": 10}
        driver.send_filament_to_tray = AsyncMock()
        driver._clear_pending = Mock()
        await driver._complete_pending_assignment("extruder9")
        driver.send_filament_to_tray.assert_not_awaited()
        driver._clear_pending.assert_not_called()

    async def test_immediate_assignment_requires_target_for_multi_tool(self):
        driver, _ = self.afc_driver()
        driver._auto_assign_confirm = "immediate"
        with self.assertRaisesRegex(ValueError, "requires a slot"):
            await driver.assign_pending_spool(10, {})


if __name__ == "__main__":
    unittest.main()
