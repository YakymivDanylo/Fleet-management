"""Send N sequential requests through the Nginx balancer and show which replica answered.

    python scripts/lb_check.py                       # 15 requests to http://localhost:8000/info
    python scripts/lb_check.py -n 20 --delay 0.5     # slower, handy while stopping a replica

The replica is read from the "pod" field of GET /info (the container hostname: api1, api2, api3).
Failed requests are counted and shown as FAIL, so the script also proves that no request is lost
while a replica is down.
"""

import argparse
import json
import time
import urllib.error
import urllib.request
from collections import Counter


def call(url: str, timeout: float) -> tuple[int, str, str, float]:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = json.load(response)
            status = response.status
            upstream = response.headers.get("X-Upstream-Addr", "-")
            replica = body.get("pod", "?")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        status, upstream, replica = 0, "-", f"FAIL ({exc})"
    return status, replica, upstream, time.perf_counter() - started


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://localhost:8000/info")
    parser.add_argument("-n", "--requests", type=int, default=15)
    parser.add_argument("--delay", type=float, default=0.0, help="pause between requests, s")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()

    counts: Counter[str] = Counter()
    failures = 0
    print(f"{'#':>3}  {'HTTP':>4}  {'replica':<8} {'upstream':<18} time")
    for number in range(1, args.requests + 1):
        status, replica, upstream, elapsed = call(args.url, args.timeout)
        counts[replica] += 1
        failures += status != 200
        print(f"{number:>3}  {status:>4}  {replica:<8} {upstream:<18} {elapsed * 1000:.0f} ms")
        time.sleep(args.delay)

    print("\nRequests per replica:")
    for replica, count in sorted(counts.items()):
        print(f"  {replica:<8} {count:>3}  {'#' * count}")
    print(f"Failed requests: {failures} of {args.requests}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
