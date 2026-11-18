# Task 2 - Shotgun Surgery crash test (FAIL state)

Two small, legitimate changes were made in classes the God Object depends on, and nothing else:

| Dependency | Change | Reason |
|---|---|---|
| `StationRegistry.has_free_slot` | `(station_id)` -> `(station_id, vehicle_type)` | per-type slot policy (EV chargers) |
| `TariffCalculator.price` | `(hours, vehicle_type)` -> `(hours, vehicle_type, zone)` | airport-zone pricing |

`RentalManager` builds these objects itself and calls them from many methods, so it is welded to
their signatures. Result (`pytest_fail.txt`): **5 of 10 behaviour tests fail with `TypeError`** and
the call sites that have to be edited by hand are all inside the mutant:

- `RentalManager.end_rental` (`has_free_slot`)
- `RentalManager.quote` (`price`)
- `RentalManager.build_invoice` (`price`) - and, transitively, `notify_finished`,
  `daily_report`, `revenue_by_vehicle_type`, which all call `build_invoice`.

One change in a collaborator ripples through lifecycle, billing, notification and reporting code
of a single class: Shotgun Surgery.
