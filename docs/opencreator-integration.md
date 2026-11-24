# OpenCreator integration

**Experimental; make a backup first.** Do not install during a print. This
guide applies to the inspected Creator 5 Pro SoC layout, not tunneled/SBC
installations. Confirm the installed firmware, plugin manager and API versions
before proceeding. The repository is private; the printer must have authorized
git access, or install a securely transferred local folder instead.

1. Back up `moonraker.conf`, the Moonraker database, FilaMan data and existing
   plugin configuration. Check `oc-plugin list`; this plugin uses ID `filaman`
   and module `filaman.py`, so it cannot coexist with an existing installation
   of that ID/component. Plan the replacement and rollback before removing it.
   Also check for an enabled `[spoolman]` or another component using the
   `/server/spoolman` endpoints: this bridge registers those names.
2. Install without restarting:

   ```sh
   oc-plugin install https://github.com/MarkSau/Filaman_OpenCreator5Pro_Plugin.git --no-restart
   ```

3. In the persistent `moonraker.conf` for this installation (the inspected
   SoC default is `/usr/data/opencreator/klipper/config/moonraker.conf`), add
   one `[filaman]` section, replacing the example URL and adding your actual
   FilaMan API key privately:

   ```ini
   [filaman]
   server: http://FILAMAN_HOST:8083
   api_key: YOUR_FILAMAN_API_KEY
   sync_rate: 5
   ```

   The component also supports Moonraker secret templates for `server` and
   `api_key`; verify secret configuration against your Moonraker version.
   Protect credentials and configuration with appropriate file permissions.
   Do not commit credentials. Do not edit `plugins/moonraker/filaman.conf`:
   the manager regenerates that directory and replaces edits.
4. Restart Moonraker through the firmware's service controls when safe. Confirm
   component load in Moonraker logs and query `GET /server/filaman/status`.
   Check `filaman_connected`, `last_error`, `filament_sensors` and
   `extruder_spools`. Confirm switch sensors, not `fm_ex*` wheel motion sensors,
   map to the expected extruders. If necessary use the component's
   `filament_sensors` mapping and verify its syntax against the deployed
   Moonraker version. Inspect sensors and toolhead objects via
   `GET /printer/objects/list` and `/printer/objects/query`.
5. On the FilaMan host, create a zip containing the `opencreator_filaman` folder
   (for example `zip -r creator_plugin.zip opencreator_filaman -x '*/__pycache__/*' '*.pyc'`) and install it
   using FilaMan's plugin manager. This archive contains only the FilaMan
   driver; the printer-side Moonraker component is installed separately above.
   Its plugin and driver key is
   `opencreator_filaman`. Configure the printer with `opencreator_url` pointing
   to Moonraker, optional Moonraker `api_key`,
   `mode: toolhead_only`, and `slot_count: 1`. Four toolheads should be
   discovered from the printer objects; `slot_count: 1` avoids creating
   unverified virtual trays. Existing configurations with a different value
   must be changed explicitly.
   The renamed plugin is a new FilaMan identity, not an in-place update of
   `moonraker_filaman`: back up FilaMan and follow its supported procedure to
   change each printer's driver and copy its settings to `opencreator_url`.
   The driver can read the legacy `moonraker_url` at runtime, but the new
   schema requires `opencreator_url`; test migration with your FilaMan version.
   Disable the old driver before activating the new one for the same printer to
   avoid duplicate assignments and consumption tracking. Existing plugin-owned
   location identifiers are retained for continuity.
6. With the printer idle, verify each toolhead assignment, switch insertion and
   removal, restart persistence and active-tool changes. Use small controlled
   extrusion and independently verify the expected consumption in FilaMan.
   Test pending assignments and error recovery before using in a print. The
   driver's health reports `afc_standalone_lanes` (physical extruder to AFC
   lane) and `afc_standalone_presence`. Verify all mappings against
   `/printer/objects/query` on the actual printer; unknown or ambiguous mappings
   are not used. On a multi-tool printer immediate auto-assign requires an
   explicit slot. Simultaneous insertions are not automatically assigned.

The bridge sets a per-extruder spool in Moonraker; it does not automatically
assign that spool to an AFC lane with `SET_SPOOL_ID`. No automatic tray mapping
or metadata display on Creator 5 Pro is claimed. The investigated Kalico AFC
enables Spoolman handling only when `/server/config` reports a `[spoolman]`
section. The bridge's `/server/spoolman` alias and its internal component
alias do not themselves create that section. Adding stock `[spoolman]` alongside
the bridge risks component and endpoint collisions; do not enable both as a
workaround. Verify the installed Kalico version and its FilaMan/Spoolman
integration before attempting AFC-side spool synchronization. Avoid `tray_macros` unless
the lane names, IDs, response handling and effects are independently verified.

To roll back, stop using the driver, back up changes, remove this plugin with
`oc-plugin remove filaman`, and remove its `[filaman]` section from the
persistent config before restarting Moonraker. Restore the previous plugin and
configuration if applicable. Removing the plugin does not migrate or undo
FilaMan locations, spool IDs, Moonraker database state or consumptions.

The inspected firmware's default Moonraker configuration trusts all clients
and disables its API key. Isolate the printer network or harden authorization
according to the deployed Moonraker documentation before enabling remote access.
