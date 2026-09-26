import json
import sys
import urllib.request

TOXIPROXY_URL = "http://localhost:8474"
PROXY = "redis"


def call(method: str, path: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{TOXIPROXY_URL}{path}", data=data, method=method)
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=5) as response:
        raw = response.read()
    return json.loads(raw) if raw else None


def reset() -> None:
    call("POST", "/reset")


def add_toxic(toxic_type: str, attributes: dict) -> None:
    call(
        "POST",
        f"/proxies/{PROXY}/toxics",
        {"name": toxic_type, "type": toxic_type, "stream": "downstream", "attributes": attributes},
    )


def status() -> None:
    proxy = call("GET", f"/proxies/{PROXY}")
    toxics = ", ".join(f"{t['type']} {t['attributes']}" for t in proxy["toxics"]) or "none"
    print(f"proxy '{PROXY}': enabled={proxy['enabled']}, toxics: {toxics}")


def main(argv: list[str]) -> None:
    command = argv[0] if argv else "status"
    if command == "latency":
        reset()
        add_toxic("latency", {"latency": int(argv[1]) if len(argv) > 1 else 3000, "jitter": 0})
    elif command == "timeout":
        reset()
        add_toxic("timeout", {"timeout": 0})
    elif command == "down":
        reset()
        call("POST", f"/proxies/{PROXY}", {"enabled": False})
    elif command == "reset":
        reset()
    elif command != "status":
        sys.exit(__doc__)
    status()


if __name__ == "__main__":
    main(sys.argv[1:])
