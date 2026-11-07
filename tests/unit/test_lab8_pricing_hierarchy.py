"""Behaviour of the Lab 8 tariff hierarchy (baseline). Values must survive the refactoring."""

from datetime import date

import pytest

from fleet_management.lab8.pricing_hierarchy import BasePricing, CorporatePricing, WeekendPricing


def test_base_total_includes_tax():
    assert BasePricing().total(2, "car") == 12.0


def test_base_applies_minimum_charge():
    assert BasePricing().subtotal(0.5, "car") == 5.0


def test_base_rejects_non_positive_hours():
    with pytest.raises(ValueError):
        BasePricing().total(0, "car")


def test_base_quote_and_billable_hours():
    pricing = BasePricing()
    assert pricing.quote(2, "car") == {"tariff": "Standard tariff", "total": "12.00 EUR"}
    assert pricing.billable_hours(5400) == 2


def test_weekend_rate_has_surcharge_and_lower_tax():
    pricing = WeekendPricing(BasePricing())
    assert pricing.subtotal(2, "car") == 12.0
    assert pricing.total(2, "car") == 13.8


def test_weekend_helpers():
    pricing = WeekendPricing(BasePricing())
    saturday, monday = date(2026, 11, 7), date(2026, 11, 9)
    assert pricing.weekend_summary(saturday, 10.0) == "weekend: +2.00"
    assert pricing.weekend_label(monday) == "weekday"


def test_weekend_quote():
    assert WeekendPricing(BasePricing()).quote(2, "car")["tariff"] == "Weekend tariff"


def test_corporate_total_has_discount_no_tax_and_fee():
    pricing = CorporatePricing(WeekendPricing(BasePricing()), "C-1")
    assert pricing.subtotal(2, "car") == 10.8
    assert pricing.total(2, "car") == 12.0


def test_corporate_quote_mentions_contract():
    assert CorporatePricing(WeekendPricing(BasePricing()), "C-1").quote(2, "car") == {
        "tariff": "Corporate Weekend tariff",
        "total": "12.00 EUR (contract C-1)",
        "contract": "C-1",
    }


def test_corporate_extras():
    pricing = CorporatePricing(WeekendPricing(BasePricing()), "C-1")
    assert pricing.corporate_discount(50.0) == 5.0
    assert pricing.invoice_header() == "Contract C-1 / net 30 days"
    assert pricing.contract_id() == "C-1"


def test_airport_zone_is_forwarded_through_every_layer():
    corporate = CorporatePricing(WeekendPricing(BasePricing()), "C-1")
    assert BasePricing().subtotal(2, "car", "airport") == 15.0
    assert WeekendPricing(BasePricing()).subtotal(2, "car", "airport") == 18.0
    assert corporate.subtotal(2, "car", "airport") == 16.2


def test_layers_do_not_inherit_from_each_other():
    assert BasePricing.__mro__ == (BasePricing, object)
    assert WeekendPricing.__mro__ == (WeekendPricing, object)
    assert CorporatePricing.__mro__ == (CorporatePricing, object)
