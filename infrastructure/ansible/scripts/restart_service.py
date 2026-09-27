"""RB-SERVICE-001: restart an allowlisted container through the Docker Engine API (unix socket).

Only services in ALLOWED_CONTAINERS can be touched. Requires --dry-run or --apply.
"""
import argparse
import json
import sys

import httpx

DOCKER_SOCKET = "/var/run/docker.sock"
ALLOWED_CONTAINERS = {"product-api": "opsmind-product-api-1"}
RESTART_GRACE_SECONDS = 10
REQUEST_TIMEOUT_SECONDS = 60
EXIT_FAILED = 1


def restart(service: str, is_dry_run: bool, transport: httpx.BaseTransport | None = None) -> dict:
    container = ALLOWED_CONTAINERS[service]
    transport = transport or httpx.HTTPTransport(uds=DOCKER_SOCKET)
    with httpx.Client(transport=transport, base_url="http://docker", timeout=REQUEST_TIMEOUT_SECONDS) as client:
        info = client.get(f"/containers/{container}/json")
        info.raise_for_status()
        state_before = info.json()["State"]["Status"]
        if not is_dry_run:
            client.post(f"/containers/{container}/restart", params={"t": RESTART_GRACE_SECONDS}).raise_for_status()
        state_after = client.get(f"/containers/{container}/json").json()["State"]["Status"]
    return {"action": "service_restart", "dry_run": is_dry_run, "service": service,
            "container": container, "state_before": state_before, "state_after": state_after}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--service", required=True, choices=sorted(ALLOWED_CONTAINERS))
    parser.add_argument("--result-file", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = restart(args.service, args.dry_run)
        code = 0
    except httpx.HTTPError as exc:
        report, code = {"action": "service_restart", "error": str(exc)}, EXIT_FAILED
    with open(args.result_file, "w", encoding="utf-8") as handle:
        json.dump(report, handle)
    print(json.dumps(report))
    return code


if __name__ == "__main__":
    sys.exit(main())
