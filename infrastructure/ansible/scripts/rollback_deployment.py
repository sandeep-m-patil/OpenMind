"""RB-DEPLOY-001: trigger the Jenkins `<service>-rollback` job. Requires --dry-run or --apply.

Credentials come from JENKINS_URL / JENKINS_USER / JENKINS_API_TOKEN (never from arguments).
"""
import argparse
import json
import os
import sys

import httpx

ALLOWED_SERVICES = {"product-api"}
REQUEST_TIMEOUT_SECONDS = 30
EXIT_FAILED = 1
HTTP_NOT_FOUND = 404


def _crumb_headers(client: httpx.Client) -> dict[str, str]:
    """Jenkins CSRF protection: password-authenticated POSTs need a crumb from the same session."""
    response = client.get("/crumbIssuer/api/json")
    if response.status_code == HTTP_NOT_FOUND:
        return {}  # CSRF protection disabled
    response.raise_for_status()
    body = response.json()
    return {body["crumbRequestField"]: body["crumb"]}


def rollback(service: str, is_dry_run: bool, transport: httpx.BaseTransport | None = None) -> dict:
    job = f"{service}-rollback"
    auth = (os.environ.get("JENKINS_USER", ""), os.environ.get("JENKINS_API_TOKEN", ""))
    base = os.environ.get("JENKINS_URL", "http://jenkins:8080")
    with httpx.Client(base_url=base, auth=auth, timeout=REQUEST_TIMEOUT_SECONDS, transport=transport) as client:
        client.get(f"/job/{job}/api/json").raise_for_status()
        queued = None
        if not is_dry_run:
            response = client.post(f"/job/{job}/build", headers=_crumb_headers(client))
            response.raise_for_status()
            queued = response.headers.get("location")
    return {"action": "deployment_rollback", "dry_run": is_dry_run, "service": service, "job": job, "queue_item": queued}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--service", required=True, choices=sorted(ALLOWED_SERVICES))
    parser.add_argument("--result-file", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        report, code = rollback(args.service, args.dry_run), 0
    except httpx.HTTPError as exc:
        report, code = {"action": "deployment_rollback", "error": str(exc)}, EXIT_FAILED
    with open(args.result_file, "w", encoding="utf-8") as handle:
        json.dump(report, handle)
    print(json.dumps(report))
    return code


if __name__ == "__main__":
    sys.exit(main())
