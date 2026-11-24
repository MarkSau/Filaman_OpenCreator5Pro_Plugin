# Architecture

```
FilaMan backend + moonraker_filaman driver
        | HTTP: printer objects, status, spool assignment, optional G-code
        v
OpenCreator Moonraker + filaman component
        | Klippy APIs / Unix domain socket         | HTTP + ApiKey
        v                                           v
Kalico: toolhead, sensors, AFC                FilaMan REST API
```

The driver is loaded in FilaMan and uses its `BaseDriver`, emitter, SQLAlchemy
models and spool/location services. It polls Moonraker, discovers extruders and
optional feeder slots, tracks assignments and original locations, and can send
configured G-code. Its `aiohttp` dependency is declared in its plugin manifest.
It is **not** an OpenCreator plugin-manager component.

The firmware-side component uses Moonraker's component lifecycle, event loop,
HTTP client, history, database, announcements and `klippy_apis`. It publishes
FilaMan and Spoolman-compatible endpoints/notifications, retains per-extruder
IDs, subscribes to toolhead position and filament presence, and reports
extrusion as consumption to FilaMan. It attempts to register a `spoolman`
component and remote method for AFC; conflicts need manual resolution.
Printer metadata push is conditional on the `filament_detect` object.

OpenCreator's plugin manager links the component and synchronizes its generated
includes. Local component settings live in the regular Moonraker config, not the
generated plugin config or git checkout. The manager only links Klippy and
Moonraker components in non-tunneled mode, hence the SoC restriction.

The inspected OpenCreator config starts Kalico with `/tmp/uds` and Moonraker
uses the same socket. Kalico's native API uses JSON messages terminated by
ASCII `0x03`, request IDs, `method`/`params`, `result`/`error` and subscription
response templates. Moonraker mediates it; the FilaMan driver does not implement
that socket protocol. Actual installation paths and ports can differ.
