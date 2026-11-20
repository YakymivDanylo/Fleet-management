---
title: Клієнтський SDK
owner: "@YakymivDanylo"
status: published
review_date: 2027-02-18
review_cycle_days: 90
tags: [api]
---

# Клієнтський SDK з контракту (OpenAPI Generator)

SDK не пишеться руками і не комітиться: це артефакт збірки з [`openapi.yaml`](openapi.yaml).

```powershell
npx @openapitools/openapi-generator-cli@2.42.2 generate -i docs/api/openapi.yaml -g python -o sdkclient `
    --additional-properties=packageName=fleet_client,projectName=fleet-client,packageVersion=1.0.0
pip install ./sdkclient
python scripts/sdk_smoke.py --url http://localhost:8000
```

Генератор 7.27.0 створює пакет `fleet_client`: класи `StationsApi`, `RentalsApi`, `VehiclesApi` (по одному на тег
контракту, методи названо за `operationId`) і типізовані Pydantic-моделі `Station`, `StationAvailability`,
`Rental`, `RentalStatus`, `RentalStart`, `RentalEnd`, `VehicleState`, `Error`, `ValidationIssue`.

```python
import fleet_client

with fleet_client.ApiClient(fleet_client.Configuration(host="http://localhost:8000")) as client:
    availability = fleet_client.StationsApi(client).get_station_availability(1)
    rental = fleet_client.RentalsApi(client).start_rental(
        fleet_client.RentalStart(renter_id=3, vehicle_id=7)
    )
```

`scripts/sdk_smoke.py` проходить усіма операціями контракту через SDK проти живого API: якщо відповідь не
десеріалізується в модель, SDK (= контракт) і код розійшлися. Версія пакета = `info.version` контракту.

Пов'язано: [[api-overview]] · [[contract-testing]] · #api
