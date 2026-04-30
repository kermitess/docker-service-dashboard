#!/usr/bin/env python3

import json
import os
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


BASE_DIR = Path(__file__).resolve().parent
INDEX_FILE = BASE_DIR / "index.html"
HOSTNAME = os.environ.get("DASHBOARD_HOST") or f"{socket.gethostname()}.local"
PORT = int(os.environ.get("PORT", "8080"))
HIDE_UNPUBLISHED = os.environ.get("DASHBOARD_HIDE_UNPUBLISHED", "true").lower() == "true"
DOCKER_SOCKET = os.environ.get("DOCKER_SOCKET", "/var/run/docker.sock")


def parse_headers(header_bytes):
    lines = header_bytes.split(b"\r\n")
    headers = {}
    for line in lines[1:]:
        if b":" not in line:
            continue
        key, value = line.split(b":", 1)
        headers[key.decode("iso-8859-1").strip().lower()] = value.decode("iso-8859-1").strip()
    return headers


def decode_chunked_body(body):
    decoded = bytearray()
    remaining = body

    while remaining:
        line_end = remaining.find(b"\r\n")
        if line_end == -1:
            raise RuntimeError("Invalid chunked response from Docker API")

        chunk_size_line = remaining[:line_end].split(b";", 1)[0]
        try:
            chunk_size = int(chunk_size_line, 16)
        except ValueError as exc:
            raise RuntimeError("Invalid chunk size from Docker API") from exc

        remaining = remaining[line_end + 2 :]
        if chunk_size == 0:
            return bytes(decoded)

        if len(remaining) < chunk_size + 2:
            raise RuntimeError("Incomplete chunked response from Docker API")

        decoded.extend(remaining[:chunk_size])
        remaining = remaining[chunk_size + 2 :]

    raise RuntimeError("Incomplete chunked response from Docker API")


def docker_get_json(path):
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(DOCKER_SOCKET)
            request = (
                f"GET {path} HTTP/1.1\r\n"
                "Host: docker\r\n"
                "Connection: close\r\n"
                "\r\n"
            )
            client.sendall(request.encode("ascii"))

            chunks = []
            while True:
                chunk = client.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Docker socket not found at {DOCKER_SOCKET}") from exc
    except PermissionError as exc:
        raise RuntimeError(f"Permission denied opening Docker socket at {DOCKER_SOCKET}") from exc
    except OSError as exc:
        raise RuntimeError(f"Could not connect to Docker socket at {DOCKER_SOCKET}: {exc}") from exc

    response = b"".join(chunks)
    try:
        header_bytes, body = response.split(b"\r\n\r\n", 1)
    except ValueError as exc:
        raise RuntimeError("Invalid response from Docker API") from exc

    headers = parse_headers(header_bytes)
    status_line = header_bytes.split(b"\r\n", 1)[0].decode("iso-8859-1", errors="replace")
    parts = status_line.split(" ", 2)
    if len(parts) < 2 or not parts[1].isdigit():
        raise RuntimeError(f"Unexpected Docker API status line: {status_line}")

    status_code = int(parts[1])
    if headers.get("transfer-encoding", "").lower() == "chunked":
        body = decode_chunked_body(body)

    if status_code >= 400:
        message = body.decode("utf-8", errors="replace").strip() or status_line
        raise RuntimeError(f"Docker API error {status_code}: {message}")

    if not body:
        return None

    try:
        return json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("Docker API returned invalid JSON") from exc


def guess_protocol(host_port, labels):
    if "dashboard.protocol" in labels:
        return labels["dashboard.protocol"]
    if host_port in {"443", "8443", "9443"}:
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
    containers = docker_get_json("/containers/json")
    if not containers:
        return {"defaultHost": HOSTNAME, "services": []}

    services = []
    seen = set()
    for summary in containers:
        container_id = summary.get("Id")
        if not container_id:
            continue

        container = docker_get_json(f"/containers/{container_id}/json")
        if should_hide(container):
            continue

        labels = container.get("Config", {}).get("Labels", {}) or {}
        ports = container.get("NetworkSettings", {}).get("Ports", {}) or {}
        container_name = display_name(container)
        container_description = description(container)

        for container_port, bindings in ports.items():
            if not container_port.endswith("/tcp"):
                continue

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
                service_key = (container_name, host, host_port, protocol, path)
                if service_key in seen:
                    continue
                seen.add(service_key)

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
