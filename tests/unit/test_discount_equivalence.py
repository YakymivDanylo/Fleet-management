"""Golden-master test: the lookup-table calculate_discount must equal the original monolith.

``_legacy_calculate_discount`` is the branch-heavy version committed in the FAIL state of the
complexity audit (CC=16), frozen verbatim with its helpers inlined. Both implementations are
compared over the full Cartesian grid of boundary values of every input.
"""

import itertools

from fleet_management.services.rental_service import calculate_discount

ZONE_DISCOUNTS = {"center": 1, "suburb": -1}


def _legacy_calculate_discount(
    rental_count,
    is_vip,
    vehicle_type,
    station_zones,
    has_coupon,
    is_weekend,
    is_holiday,
    *,
    is_corporate=False,
    is_night=False,
    trip_hours=0.0,
    is_birthday=False,
    returned_charged=False,
):
    if is_vip:
        if rental_count > 10:
            discount = 5 if vehicle_type == "premium" else 10
        else:
            discount = 2 if vehicle_type == "premium" else 5
    elif rental_count > 20:
        discount = 3
    elif rental_count <= 5:
        discount = 0
    else:
        discount = 4 if has_coupon else 1

    if is_weekend:
        discount += sum(ZONE_DISCOUNTS.get(zone, 0) for zone in station_zones)
    if is_holiday:
        discount += 2 if has_coupon else 1

    if is_corporate and rental_count > 5 and vehicle_type != "premium":
        discount += 3
    if is_night and trip_hours >= 3 and not has_coupon:
        discount += 4
    if is_birthday and (is_vip or rental_count > 3):
        discount += 6
    if returned_charged and vehicle_type == "electric" and trip_hours > 1:
        discount += 2

    return discount


def test_lookup_table_discount_matches_legacy_monolith_on_full_grid():
    grid = itertools.product(
        (0, 3, 4, 5, 6, 10, 11, 20, 21, 25),  # rental_count around every threshold
        (False, True),  # is_vip
        ("standard", "premium", "electric"),  # vehicle_type
        ([], ["center"], ["center", "suburb", "other"]),  # station_zones
        (False, True),  # has_coupon
        (False, True),  # is_weekend
        (False, True),  # is_holiday
        (False, True),  # is_corporate
        (False, True),  # is_night
        (0, 1, 1.5, 3),  # trip_hours around 1 and 3
        (False, True),  # is_birthday
        (False, True),  # returned_charged
    )
    checked = 0
    for args in grid:
        (count, vip, kind, zones, coupon, weekend, holiday, corp, night, hours, bday, charged) = (
            args
        )
        kwargs = {
            "is_corporate": corp,
            "is_night": night,
            "trip_hours": hours,
            "is_birthday": bday,
            "returned_charged": charged,
        }
        expected = _legacy_calculate_discount(
            count, vip, kind, zones, coupon, weekend, holiday, **kwargs
        )
        actual = calculate_discount(count, vip, kind, zones, coupon, weekend, holiday, **kwargs)
        assert actual == expected, args
        checked += 1
    assert checked == 10 * 2 * 3 * 3 * 2 * 2 * 2 * 2 * 2 * 4 * 2 * 2
