import math

RATES = {"car": 5.0, "premium": 9.0, "electric": 7.0}


class TariffCalculator:
    def price(self, hours: int, vehicle_type: str) -> float:
        return round(max(hours, 1) * RATES.get(vehicle_type, RATES["car"]), 2)

    def discount(self, subtotal: float, rental_count: int, has_coupon: bool, is_vip: bool) -> float:
        percent = 10 if is_vip else 0
        percent += 5 if has_coupon else 0
        percent += 5 if rental_count > 10 else 0
        return round(subtotal * percent / 100, 2)

    @staticmethod
    def billable_hours(seconds: float) -> int:
        return max(math.ceil(seconds / 3600), 1)


class FineCalculator:
    FINE_PER_HOUR = 3.0

    def late_fee(self, hours_over: int) -> float:
        return round(max(hours_over, 0) * self.FINE_PER_HOUR, 2)
