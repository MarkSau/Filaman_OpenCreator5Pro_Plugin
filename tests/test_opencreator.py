"""Focused tests against the shipped methods without Moonraker/FilaMan imports."""
import ast
import json
import logging
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]


def extract(path, class_name, names, namespace):
    tree = ast.parse(path.read_text())
    cls = next(node for node in tree.body
               if isinstance(node, ast.ClassDef) and node.name == class_name)
    methods = [node for node in cls.body
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
               and node.name in names]
    assert {node.name for node in methods} == set(names)
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[
        ast.alias(name="annotations")], level=0),
        ast.ClassDef(name="Probe", bases=[], keywords=[], body=methods,
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


if __name__ == "__main__":
    unittest.main()
