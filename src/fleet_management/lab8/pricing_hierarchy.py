"""Tariff layers combined by composition: Corporate -> Weekend -> Base (no inheritance)."""

import math
from datetime import date

RATES = {"car": 5.0, "premium": 9.0, "electric": 7.0}
ZONE_FACTOR = {"city": 1.0, "airport": 1.5}


class BasePricing:
    TAX_RATE = 0.2

    def billable_hours(self, seconds: float) -> int:
        return max(math.ceil(seconds / 3600), 1)

    def validate_hours(self, hours: float) -> float:
        if hours <= 0:
            raise ValueError("hours must be positive")
        return hours

    def base_rate(self, vehicle_type: str, zone: str) -> float:
        return RATES.get(vehicle_type, RATES["car"]) * ZONE_FACTOR[zone]

    def min_charge(self) -> float:
        return 5.0

    def subtotal(self, hours: float, vehicle_type: str, zone: str = "city") -> float:
        raw = self.validate_hours(hours) * self.base_rate(vehicle_type, zone)
        return max(raw, self.min_charge())

    def tax(self, amount: float) -> float:
        return amount * self.TAX_RATE

    def apply_fee(self, amount: float) -> float:
        return amount

    def round_amount(self, amount: float) -> float:
        return round(amount, 2)

    def total(self, hours: float, vehicle_type: str, zone: str = "city") -> float:
        subtotal = self.subtotal(hours, vehicle_type, zone)
        return self.round_amount(self.apply_fee(subtotal + self.tax(subtotal)))

    def currency(self) -> str:
        return "EUR"

    def format_price(self, amount: float) -> str:
        return f"{amount:.2f} {self.currency()}"

    def describe(self) -> str:
        return "Standard tariff"

    def quote(self, hours: float, vehicle_type: str) -> dict[str, str]:
        return {
            "tariff": self.describe(),
            "total": self.format_price(self.total(hours, vehicle_type)),
        }


class WeekendPricing:
    SURCHARGE = 0.2
    MIN_CHARGE = 8.0
    TAX_RATE = 0.15

    def __init__(self, base: BasePricing):
        self._base = base

    def subtotal(self, hours: float, vehicle_type: str, zone: str = "city") -> float:
        rate = self._base.base_rate(vehicle_type, zone) * (1 + self.SURCHARGE)
        return max(self._base.validate_hours(hours) * rate, self.MIN_CHARGE)

    def tax(self, amount: float) -> float:
        return amount * self.TAX_RATE

    def total(self, hours: float, vehicle_type: str, zone: str = "city") -> float:
        subtotal = self.subtotal(hours, vehicle_type, zone)
        return self._base.round_amount(self._base.apply_fee(subtotal + self.tax(subtotal)))

    def format_price(self, amount: float) -> str:
        return self._base.format_price(amount)

    def describe(self) -> str:
        return "Weekend tariff"

    def quote(self, hours: float, vehicle_type: str, zone: str = "city") -> dict[str, str]:
        total = self.total(hours, vehicle_type, zone)
        return {"tariff": self.describe(), "total": self.format_price(total)}

    def weekend_surcharge(self, amount: float) -> float:
        return round(amount * self.SURCHARGE, 2)

    def is_weekend(self, day: date) -> bool:
        return day.weekday() >= 5

    def weekend_label(self, day: date) -> str:
        return "weekend" if self.is_weekend(day) else "weekday"

    def weekend_summary(self, day: date, amount: float) -> str:
        return f"{self.weekend_label(day)}: +{self.weekend_surcharge(amount):.2f}"


class CorporatePricing:
    DISCOUNT = 0.1
    ADMIN_FEE = 1.0

    def __init__(self, weekend: WeekendPricing, contract: str):
        self._weekend = weekend
        self._contract = contract

    def subtotal(self, hours: float, vehicle_type: str, zone: str = "city") -> float:
        return round(self._weekend.subtotal(hours, vehicle_type, zone) * (1 - self.DISCOUNT), 4)

    def total(self, hours: float, vehicle_type: str, zone: str = "city") -> float:
        return round((self.subtotal(hours, vehicle_type, zone) + self.ADMIN_FEE) * 2) / 2

    def format_price(self, amount: float) -> str:
        return f"{self._weekend.format_price(amount)} (contract {self._contract})"

    def describe(self) -> str:
        return f"Corporate {self._weekend.describe()}"

    def quote(self, hours: float, vehicle_type: str, zone: str = "city") -> dict[str, str]:
        total = self.total(hours, vehicle_type, zone)
        return {
            "tariff": self.describe(),
            "total": self.format_price(total),
            "contract": self._contract,
        }

    def corporate_discount(self, amount: float) -> float:
        return round(amount * self.DISCOUNT, 2)

    def contract_id(self) -> str:
        return self._contract

    def invoice_header(self) -> str:
        return f"Contract {self._contract} / net {self.net_terms()} days"

    def net_terms(self) -> int:
        return 30
