"""Baseline design: three-level tariff hierarchy (Base -> Weekend -> Corporate pricing)."""

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


class WeekendPricing(BasePricing):
    SURCHARGE = 0.2

    def base_rate(self, vehicle_type: str) -> float:
        return super().base_rate(vehicle_type) * (1 + self.SURCHARGE)

    def min_charge(self) -> float:
        return 8.0

    def tax(self, amount: float) -> float:
        return amount * 0.15

    def describe(self) -> str:
        return "Weekend tariff"

    def weekend_surcharge(self, amount: float) -> float:
        return round(amount * self.SURCHARGE, 2)

    def is_weekend(self, day: date) -> bool:
        return day.weekday() >= 5

    def weekend_label(self, day: date) -> str:
        return "weekend" if self.is_weekend(day) else "weekday"

    def weekend_summary(self, day: date, amount: float) -> str:
        return f"{self.weekend_label(day)}: +{self.weekend_surcharge(amount):.2f}"


class CorporatePricing(WeekendPricing):
    DISCOUNT = 0.1
    ADMIN_FEE = 1.0

    def __init__(self, contract: str):
        self._contract = contract

    def subtotal(self, hours: float, vehicle_type: str) -> float:
        return round(super().subtotal(hours, vehicle_type) * (1 - self.DISCOUNT), 4)

    def tax(self, amount: float) -> float:
        return 0.0

    def apply_fee(self, amount: float) -> float:
        return amount + self.ADMIN_FEE

    def round_amount(self, amount: float) -> float:
        return round(amount * 2) / 2

    def format_price(self, amount: float) -> str:
        return f"{super().format_price(amount)} (contract {self._contract})"

    def describe(self) -> str:
        return f"Corporate {super().describe()}"

    def quote(self, hours: float, vehicle_type: str) -> dict[str, str]:
        return {**super().quote(hours, vehicle_type), "contract": self._contract}

    def corporate_discount(self, amount: float) -> float:
        return round(amount * self.DISCOUNT, 2)

    def contract_id(self) -> str:
        return self._contract

    def invoice_header(self) -> str:
        return f"Contract {self._contract} / net {self.net_terms()} days"

    def net_terms(self) -> int:
        return 30
