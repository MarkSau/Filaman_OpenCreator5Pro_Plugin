# Developer setup

Clone this repository and run the dependency-free focused checks:

```sh
python3 tests/test_opencreator.py
python3 tests/test_slot_sensor.py
python3 -m compileall -q moonraker moonraker_filaman
```

`tests/test_slot_locations.py` imports the real FilaMan backend, SQLAlchemy,
FastAPI and `aiosqlite`. Run it in a compatible FilaMan backend environment
with that backend and this repository on `PYTHONPATH`; its FilaMan revision is
not pinned here. No backend is bundled. The focused tests extract methods from
the shipped source and fake their dependencies; they are not integration tests.

For end-to-end testing, use a disposable FilaMan instance, a matching
OpenCreator/Moonraker/Kalico installation and disposable test spools. Avoid
real hardware motion and production inventory until the matrix's manual checks
are completed. Source snapshots and outstanding checks are in `migration.md`.
