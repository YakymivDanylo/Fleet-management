# Task 3 - inheritance crash test (FAIL state)

Only the top of the hierarchy was touched: `BasePricing.base_rate(vehicle_type)` became
`base_rate(vehicle_type, zone)` (airport-zone pricing), and `BasePricing.subtotal/total` forward the
new `zone` argument. `BasePricing` itself is consistent, its tests stay green.

The change "shoots down" the chain (`pytest_fail.txt`, 4 of 10 tests red, all in descendants):

- `WeekendPricing.base_rate(vehicle_type)` overrides the old signature and calls
  `super().base_rate(vehicle_type)` -> `TypeError: takes 2 positional arguments but 3 were given`
  (breaks `WeekendPricing.subtotal/total/quote` and everything below it).
- `CorporatePricing.subtotal(hours, vehicle_type)` overrides the old signature
  -> `TypeError: takes 3 positional arguments but 4 were given` (breaks `total/quote`).

To repair it the developer must edit two child classes that never asked for the change; every
override that calls `super()` is a hidden coupling to the parent's exact signature.
