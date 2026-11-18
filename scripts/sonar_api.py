"""Pull measures from the SonarQube / SonarCloud Web API (Lab 8, task 1).

    SONAR_TOKEN=... python scripts/sonar_api.py src/fleet_management/services/rental_service.py

The equivalent curl command is printed first so it can be pasted into the report. SonarQube's own
Python analyzer exposes size/complexity metrics only; the CK metrics that the Python analyzer does
not provide (coupling_between_objects, lcom4, dit, ...) come from scripts/ck_metrics.py, which
prints the same JSON shape.
"""

import json
import os
import sys
import urllib.parse
import urllib.request

SONAR_URL = os.environ.get("SONAR_URL", "https://sonarcloud.io")
PROJECT_KEY = os.environ.get("SONAR_PROJECT_KEY", "fleet-management")
METRIC_KEYS = "complexity,cognitive_complexity,ncloc,functions,classes"


def build_url(path: str) -> str:
    query = urllib.parse.urlencode(
        {"component": f"{PROJECT_KEY}:{path}", "metricKeys": METRIC_KEYS}
    )
    return f"{SONAR_URL}/api/measures/component?{query}"


def main() -> int:
    token = os.environ.get("SONAR_TOKEN", "")
    for path in sys.argv[1:]:
        url = build_url(path)
        print(f'curl --header "Authorization: Bearer $SONAR_TOKEN" "{url}"')
        request = urllib.request.Request(url)
        request.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            print(json.dumps(json.load(response), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
