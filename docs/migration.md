# Compatibility assessment and migration report

## Evidence and scope

These are source observations, not proof of device compatibility:

- FilaMan driver: [MarkSau fork, `703441f`](https://github.com/MarkSau/FilaMan-Moonraker-Plugin/tree/703441f892a20a0701f43893aa11902142ca925c).
- Firmware-side bridge: [MarkSau OpenCreator plugin, `92dc765`](https://github.com/MarkSau/FilaMan-OpenCreator-Plugin/tree/92dc7658034ab469b96f09f4a04811f5b2d955c1).
- Kalico: [MarkSau fork, `7da732e`](https://github.com/MarkSau/kalico/tree/7da732e09d4e213b7766482b6cfdf7e75ee9e191).
- OpenCreator: [opencreator-fs, `3d2f88b`](https://github.com/FlashForge-C5-Modding-Group/opencreator-fs/tree/3d2f88be16822192290e8d748045e086482aca81);
  [plugin example, `3c4086b`](https://github.com/FlashForge-C5-Modding-Group/OpenCreator-Plugin-Example/tree/3c4086b176bee1b6168251b35e57d8daa948dd9d).

The actual printer, installed revisions and FilaMan backend were unavailable.
These snapshots may not be the versions on the device.

## Compatibility matrix

| Area | Source evidence | Adaptation / status |
| --- | --- | --- |
| Runtime architecture | OpenCreator `config/moonraker.conf` and startup scripts use Moonraker and Kalico's `/tmp/uds`. Kalico `docs/API_Server.md` defines framed socket messages. | Retain Moonraker; no evidence supports removing it. Socket path and service versions must be verified on device. |
| OpenCreator lifecycle | `oc_plugin.py` links Moonraker components and regenerates plugin config; `sync()` skips links in tunneled mode. | Manifest restricts to Creator5Pro `soc`; local `[filaman]` settings remain outside generated files. SBC is not supported by this package. |
| Four toolheads | OpenCreator `printer.cfg` defines `extruder` through `extruder3`; standalone `AFC_extruder` sections create `AFC_lane extruder0` through `extruder3` in Kalico `AFC_extruder.py`. | The driver maps these lanes to existing toolhead slots via `extruder_name`, `is_standalone`, `lanes` and lane `extruder`. Default `slot_count` is 1, so additional feeder trays are not invented. Confirm object list and existing settings. |
| Tool presence | OpenCreator `printer.afc-standalone.cfg` configures `pin_tool_start`; Kalico registers switches `<extruderN>_tool_start`. `printer.filament.cfg` also has `fm_ex*` wheel motion sensors. | Component prioritizes switches, ignores motion sensors unless explicitly mapped, and honors overrides. Verify actual mappings and semantics on device. |
| Feeder/AMS presence | Original driver recognizes `AFC_stepper`, MMU and QIDI patterns, not standalone `AFC_lane` objects. AFC lane status has `prep`. The original schema defaulted `slot_count` to 4, which could create virtual trays even without AFC discovery. | Feeder support remains unchanged. Standalone lane presence is associated with its toolhead, without duplicating it as a separate tray; actual installation behavior still requires live verification. Explicit existing `slot_count > 1` can still create virtual trays. |
| Assignment | Driver POSTs `spool_id` and optional `extruder` to `/server/filaman/spool_id`; component stores per-extruder IDs. | Preserved. Tool assignments do not call AFC `SET_SPOOL_ID`; lane synchronization and response verification remain open. |
| Metadata push | Existing component calls `/printer/filament_detect/set`; `filament_detect` and `print_task_config` implementations are not present in the inspected Kalico tree. | Skip pushes if `filament_detect` object was not discovered. Presence of an object does not itself prove the HTTP endpoint works; verify if present. No Creator 5 metadata adapter is claimed. |
| Usage reporting | Component subscribes to toolhead position, calculates positive extrusion, converts length to weight and POSTs a consumption. | Preserved, not end-to-end tested. Test resets, retractions, toolchanges, outages and duplicate reporting; defaults for missing density/diameter may affect accuracy. Pending reports are in memory. |
| Spoolman/AFC | Component registers Spoolman aliases and a remote method; `AFC_utils.get_spoolman_server` requires `orig.spoolman.server` from `/server/config`. `AFC_spool.py` calls `spoolman_set_active_spool` and obtains spool data via Moonraker. | Registering an alias alone does not satisfy this detection. The driver reads AFC but does not write lane spool IDs. Existing `[spoolman]` or endpoint registration can conflict; do not add it blindly. Kalico is unchanged. |
| Sensor-driven auto-assign | Driver reads component `filament_present` and optional per-tray sensor status; absent baseline is not an insertion. | Retained. Verify debounce, mapping, insertion/unload and restart behavior with four tools; avoid assuming a motion sensor represents spool presence. |
| Security | Inspected OpenCreator default has API keys disabled and trusts `0.0.0.0/0`; component sends FilaMan `Authorization: ApiKey ...`. Driver optionally sends Moonraker `X-Api-Key`. | No credentials included here; use protected configuration and network isolation/hardening. Do not expose the default service to untrusted networks. |

## Moonraker dependencies and interfaces

The driver requires HTTP access to:

- `GET /server/filaman/status`: `filaman_connected`, `spool_id`,
  `extruder_spools`, `filament_present`, error and success fields.
- `POST /server/filaman/spool_id`: JSON `spool_id` and optional `extruder`;
  a null ID clears an assignment.
- `GET /printer/objects/list`, `GET /printer/objects/query?...` for discovery
  and sensors; `GET /server/config` for optional tray configuration;
  `POST /printer/gcode/script` with `{"script": ...}` in macro mode.
- Moonraker JSON `result` envelopes and optionally `X-Api-Key`; HTTP errors
  are surfaced by the driver.

The component requires Moonraker's `ConfigHelper`, `RequestType`, web requests,
component loader, lifecycle, event loop/timer, `history`, `database`,
`http_client`, `announcements`, `klippy_apis`, registration of endpoints,
notifications, events and remote methods. It stores `filaman.spool_id`,
`filaman.extruder_spools` and legacy `spoolman.spool_id` in the `moonraker`
database namespace and adds a history auxiliary field.

It registers GET/POST `spool_id`, GET `spool_ids`, POST `proxy`, GET `status`
and POST `repush` under both `/server/filaman` and `/server/spoolman`.
Proxy requests accept `request_method`, `path`, optional `query`, `body` and
`use_v2_response`; legacy `/use` is converted from length to consumption
weight. It emits `filaman:*` and selected `spoolman:*` notifications, listens
for `server:klippy_ready`, and registers `filaman_set_active_spool` and, when
possible, `spoolman_set_active_spool`.

The component subscribes to `toolhead.position`/`extruder`, discovered filament
sensors and optional printer-specific objects. It talks to FilaMan's
`/api/v1/spools`, `/api/v1/spools/{id}` and
`/api/v1/spools/{id}/consumptions`; it also proxies arbitrary supported paths
and attempts `/spoolman/api/v1` for legacy requests. The driver additionally
depends on FilaMan backend models, database sessions, `SpoolService`,
`BaseDriver`, emitter contracts and `aiohttp`, not just Moonraker.

Kalico's UDS protocol is distinct from Moonraker HTTP: JSON dictionaries with
`method`, optional `params` and `id`, terminated by byte `0x03`; responses
contain `result` or `error`, subscriptions use `response_template`. See
`docs/API_Server.md` in the cited Kalico snapshot for protocol details.

## Migration plan

1. Retain the proven-by-source Moonraker transport;
   replace only incompatible assumptions. Use distinct firmware and FilaMan
   install artifacts. Implemented here.
2. Package the existing bridge for the OpenCreator plugin manager, keep
   credentials in persistent local configuration, and restrict installation
   to SoC/Pro. Implemented; deployment remains untested.
3. Prefer switches, require explicit opt-in for motion sensors, and avoid
   metadata requests when their supporting object is absent. Implemented with
   focused tests.
4. Map AFC standalone lanes to existing toolheads from reported status fields;
   use `prep` as a presence fallback. Refuse ambiguous mappings and simultaneous
   insertion confirmations. Implemented with source-shaped tests; validate
   against the actual printer. Design a separate adapter for bidirectional
   spool synchronization; do not assume sorted lane order or send motion commands.
5. Test against the exact deployed FilaMan, Moonraker and Kalico versions in a
   disposable environment: registration/authentication, discovery,
   per-extruder assign/clear, pending insertion, runout debounce, toolchange,
   restart persistence, loss/recovery, consumption and Spoolman proxy.
   Then perform controlled, supervised Creator 5 Pro hardware checks.
6. Only claim compatibility or expand the manifest after those checks pass.

## Pull-request style change report

Relative to the driver fork:

- **Modified:** `opencreator_filaman/plugin.json` changes the virtual tray default
  from 4 to 1 and renames the plugin/driver key to `opencreator_filaman` and
  URL field to `opencreator_url`. `driver.py` uses the new identity and accepts
  the old URL field as a runtime fallback; schema validation still requires the
  new field. `.gitignore` excludes Python cache directories.
- **AFC adaptation:** `opencreator_filaman/driver.py` reads and validates
  standalone lane-to-extruder mappings and lane presence, merges it with
  component presence for pending assignments, reports it in health, and
  refuses ambiguous/mismatched tool assignments. `tests/test_opencreator.py`
  and `tests/test_slot_sensor.py` cover the new behavior.
- **Added:** `opencreator-plugin.json`; `moonraker/filaman.py` and
  `moonraker/LICENSE` from the separate existing firmware-side project, with
  switch precedence, explicit motion-sensor opt-in and conditional metadata push adaptations;
  `tests/test_opencreator.py`; `README.md`; `docs/architecture.md`,
  `docs/migration.md`, `docs/opencreator-integration.md`,
  `docs/development.md` and `docs/upstream-driver.md` (original driver README).
- **Retained:** package initializer and icon, and
  inherited tests/fixture. CI release workflows were not
  carried over.
- **Manual review:** `moonraker/filaman.py` (endpoint conflicts, sensor/usage
  and printer metadata behavior), `opencreator_filaman/driver.py` (slot and
  location persistence, multi-tool pending assignment), both manifests,
  licensing and all deployment instructions.

## Verification performed

The focused compatibility tests and inherited dependency-free sensor tests
passed, including synthetic statuses shaped from the inspected Kalico source.
The inspected OpenCreator plugin manager installed, synced and removed
the package in a temporary simulated SoC filesystem; persistent Moonraker
configuration remained intact. Python compilation passed. The inherited
location tests could not run here: the FilaMan backend and its dependencies,
including FastAPI, are unavailable. No live service or printer was tested.

## TODO / risks requiring manual verification

- Verify actual installed revisions, model, SoC mode, plugin-manager compatibility,
  restart behavior, paths, Python versions, FilaMan plugin loading and API schemas.
- Verify physical sensor mappings, sensor polarity/debounce, four toolhead
  selection, assignments, runout and auto-assignment across restarts.
- Verify AFC's Spoolman proxy data shapes and implement and test lane spool ID
  synchronization without modifying Kalico or conflicting with a real
  Spoolman component. Avoid duplicate consumption from other integrations.
- Establish Creator 5's actual metadata API, if any; implement a dedicated
  adapter only after verifying its interface and effects.
- Run backend-dependent location tests and integration tests with realistic
  FilaMan/Moonraker/Kalico services, then hardware acceptance. Test failures,
  offline retries, power loss and recovery; queued usage is not durable.
- Resolve upstream driver's redistribution license and verify compatibility
  of all dependencies and license obligations before distribution.
- Review security and authentication, existing endpoint collisions, spool
  migration/rollback, and configuration persistence on firmware updates.
