from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
import urllib.request
import uuid
import zipfile


def request(api: str, path: str, token: str, method: str = "GET", payload: dict | None = None):
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    req = urllib.request.Request(api.rstrip("/") + path, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.loads(response.read())


def verify(args) -> int:
    repo_path = Path(args.repo)
    if repo_path.exists():
        project = request(args.api, "/projects", args.token, "POST", {"name": "migrationguard-cli", "repository_url": None})
        boundary = uuid.uuid4().hex
        with tempfile.NamedTemporaryFile(suffix=".zip") as archive:
            with zipfile.ZipFile(archive.name, "w", zipfile.ZIP_DEFLATED) as output:
                for path in repo_path.rglob("*"):
                    if path.is_file() and ".git" not in path.parts:
                        output.write(path, path.relative_to(repo_path).as_posix())
            payload = archive.read()
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"upload\"; filename=\"repository.zip\"\r\n"
            "Content-Type: application/zip\r\n\r\n"
        ).encode() + payload + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(
            args.api.rstrip("/") + f"/projects/{project['id']}/runs/upload",
            data=body,
            headers={"Authorization": f"Bearer {args.token}", "Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as response:
            run = json.loads(response.read())
    else:
        project = request(args.api, "/projects", args.token, "POST", {"name": "migrationguard-cli", "repository_url": args.repo})
        run = request(args.api, f"/projects/{project['id']}/runs", args.token, "POST")
    print(f"run: {run['id']}")
    try:
        req = urllib.request.Request(
            args.api.rstrip("/") + f"/runs/{run['id']}/events",
            headers={"Authorization": f"Bearer {args.token}"},
        )
        with urllib.request.urlopen(req, timeout=3600) as response:
            for line in response:
                text = line.decode(errors="replace").strip()
                if text.startswith("data: "):
                    print(text[6:])
    except Exception as exc:
        print(f"progress stream ended: {exc}", file=sys.stderr)
    result = request(args.api, f"/runs/{run['id']}/report", args.token)
    verdict = result["content"]["verdict"]
    print(f"verdict: {verdict['value']}")
    for reason in verdict["reasons"]:
        print(f"- {reason['rule_id']}: {reason['message']}")
    return 1 if verdict["value"] in args.fail_on else 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="migrationguard")
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--repo", required=True)
    verify_parser.add_argument("--target", default="17")
    verify_parser.add_argument("--api", required=True)
    verify_parser.add_argument("--token", required=True)
    verify_parser.add_argument("--fail-on", default="UNSAFE,INCONCLUSIVE")
    args = parser.parse_args()
    if args.command == "verify":
        args.fail_on = {value.strip() for value in args.fail_on.split(",") if value.strip()}
        return verify(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
