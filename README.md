# FilaMan for OpenCreator Creator 5 Pro

**Experimental:** source-based adaptation, not yet validated on a printer or
against a running FilaMan/Moonraker installation. Do not rely on it for
inventory or unattended printing until the checks in the integration guide pass.

This repository contains two separate pieces: an OpenCreator-installed
Moonraker component (`moonraker/filaman.py`) and a FilaMan-installed driver
(`moonraker_filaman/`). OpenCreator already uses Moonraker to reach Kalico;
this integration deliberately retains that bridge.
The FilaMan plugin and driver key is `opencreator_filaman`; its
`opencreator_url` points to the printer's Moonraker HTTP service.

See the [integration guide](docs/opencreator-integration.md), [architecture](docs/architecture.md),
[compatibility matrix and migration plan](docs/migration.md), and
[developer setup](docs/development.md). The inherited driver options are
documented in [upstream-driver.md](docs/upstream-driver.md); its installation
instructions refer to the original project, not this repository.

The firmware plugin targets Creator 5 Pro SoC installations only. SBC/tunneled
installation, physical devices, and firmware versions other than those
referenced in the migration report remain unverified.

## Source and licensing

The driver derives from [MarkSau/FilaMan-Moonraker-Plugin](https://github.com/MarkSau/FilaMan-Moonraker-Plugin)
(itself a fork of Fire-Devils/FilaMan-Moonraker-Plugin); no license was found
in either repository. Its reuse here is based on the repository owner's
confirmation of permission; redistribution terms still require clarification.
The component derives from [MarkSau/FilaMan-OpenCreator-Plugin](https://github.com/MarkSau/FilaMan-OpenCreator-Plugin)
and is GPLv3; its license is in `moonraker/LICENSE`. Do not assume that license
also covers the driver.
