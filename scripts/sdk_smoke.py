"""Lab 11: smoke test of the client SDK generated from docs/api/openapi.yaml.

    npx @openapitools/openapi-generator-cli@2.42.2 generate -i docs/api/openapi.yaml -g python \
        -o sdkclient --additional-properties=packageName=fleet_client
    pip install ./sdkclient
    python scripts/sdk_smoke.py [--url http://localhost:8000]

Calls every contract operation through the generated typed client against a running API and
prints what came back; any deserialization error means the SDK (= the contract) and the code
disagree. ``sdkclient/`` is a build artifact and is not committed.
"""

import argparse
import sys

import fleet_client
from fleet_client.exceptions import ApiException


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://localhost:8000")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    config = fleet_client.Configuration(host=args.url)
    with fleet_client.ApiClient(config) as client:
        stations = fleet_client.StationsApi(client)
        rentals = fleet_client.RentalsApi(client)
        vehicles = fleet_client.VehiclesApi(client)

        all_stations = stations.list_stations()
        print(f"listStations -> {len(all_stations)} x {type(all_stations[0]).__name__}")
        availability = stations.get_station_availability(all_stations[0].id)
        print(f"getStationAvailability -> {availability!r}")

        state = vehicles.get_vehicle_state(1)
        print(f"getVehicleState -> source={state.source} recorded_at={state.recorded_at}")

        try:
            stations.get_station_availability(2_147_483_647)
        except ApiException as exc:
            error = fleet_client.Error.from_json(exc.body)
            detail = error.detail.actual_instance
            print(f"getStationAvailability(unknown) -> HTTP {exc.status}, detail={detail!r}")

        started = _start_first_available(rentals)
        print(f"startRental -> id={started.id} {started.status} started_at={started.started_at}")
        ended = rentals.end_rental(started.id, fleet_client.RentalEnd(end_station_id=1))
        print(f"endRental -> status={ended.status} cost={ended.cost} ended_at={ended.ended_at}")
    return 0


def _start_first_available(rentals: fleet_client.RentalsApi) -> fleet_client.Rental:
    """Rent the first available vehicle (409 = already rented; /vehicles is not in the contract)."""
    for vehicle_id in range(1, 50):
        try:
            return rentals.start_rental(
                fleet_client.RentalStart(renter_id=3, vehicle_id=vehicle_id)
            )
        except ApiException as exc:
            if exc.status not in (404, 409):
                raise
    raise SystemExit("no available vehicle")


if __name__ == "__main__":
    raise SystemExit(main())
