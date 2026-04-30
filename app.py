#!/usr/bin/env python3

import json
import os
import socket
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


BASE_DIR = Path(__file__).resolve().parent
INDEX_FILE = BASE_DIR / "index.html"
HOSTNAME = os.environ.get("DASHBOARD_HOST") or f"{socket.gethostname()}.local"
PORT = int(os.environ.get("PORT", "8080"))
HIDE_UNPUBLISHED = os.environ.get("DASHBOARD_HIDE_UNPUBLISHED", "true").lower() == "true"


def run_command(args):
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "command failed")
    return result.stdout


def guess_protocol(host_port, labels):
    if "dashboard.protocol" in labels:
        return labels["dashboard.protocol"]
    if host_port in {"443", "8443"}:
        return "https"
    return "http"


def guess_host(labels):
    return labels.get("dashboard.host", HOSTNAME)


def guess_path(labels):
    return labels.get("dashboard.path", "")


def display_name(container):
    labels = container.get("Config", {}).get("Labels", {}) or {}
    configured = labels.get("dashboard.name")
    if configured:
        return configured

    compose_name = labels.get("com.docker.compose.service")
    if compose_name:
        return compose_name

    raw_name = container.get("Name", "").lstrip("/")
    return raw_name or container.get("Config", {}).get("Image", "unknown")


def description(container):
    labels = container.get("Config", {}).get("Labels", {}) or {}
    if "dashboard.description" in labels:
        return labels["dashboard.description"]
    return container.get("Config", {}).get("Image", "")


def should_hide(container):
    labels = container.get("Config", {}).get("Labels", {}) or {}
    return labels.get("dashboard.hide", "false").lower() == "true"


def discover_services():
    ids = [line.strip() for line in run_command(["docker", "ps", "-q"]).splitlines() if line.strip()]
    if not ids:
        return {"defaultHost": HOSTNAME, "services": []}

    inspect_output = run_command(["docker", "inspect", *ids])
    containers = json.loads(inspect_output)

    services = []
    for container in containers:
        if should_hide(container):
            continue

        labels = container.get("Config", {}).get("Labels", {}) or {}
        ports = container.get("NetworkSettings", {}).get("Ports", {}) or {}
        container_name = display_name(container)
        container_description = description(container)

        for container_port, bindings in ports.items():
            if not bindings:
                if HIDE_UNPUBLISHED:
                    continue
                continue

            for binding in bindings:
                host_port = binding.get("HostPort")
                if not host_port:
                    continue

                host = guess_host(labels)
                protocol = guess_protocol(host_port, labels)
                path = guess_path(labels)

                services.append(
                    {
                        "name": container_name,
                        "port": int(host_port),
                        "host": host,
                        "protocol": protocol,
                        "path": path,
                        "description": container_description,
                        "containerPort": container_port,
                    }
                )

    services.sort(key=lambda item: (item["name"].lower(), item["port"]))
    return {"defaultHost": HOSTNAME, "services": services}


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path in {"/", "/index.html"}:
            self.serve_index()
            return

        if parsed.path == "/services.json":
            self.serve_services()
            return

        self.send_response(404)
        self.end_headers()

    def serve_index(self):
        content = INDEX_FILE.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def serve_services(self):
        try:
            payload = json.dumps(discover_services()).encode("utf-8")
            self.send_response(200)
        except Exception as exc:
            payload = json.dumps({"error": str(exc), "services": []}).encode("utf-8")
            self.send_response(500)

        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), DashboardHandler)
    print(f"Serving dashboard on http://0.0.0.0:{PORT} for host {HOSTNAME}")
    server.serve_forever()
