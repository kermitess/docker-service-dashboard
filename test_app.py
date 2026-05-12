import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app


class CaddyRouteTests(unittest.TestCase):
    def test_read_caddy_routes_handles_multiple_sites_and_matchers(self):
        caddyfile = """
        https://foo.example.com, bar.example.com:8443 {
            reverse_proxy /api/* api:8080
        }
        """

        with tempfile.NamedTemporaryFile("w", delete=False) as handle:
            handle.write(caddyfile)
            caddy_path = handle.name

        self.addCleanup(lambda: Path(caddy_path).unlink(missing_ok=True))

        with patch.object(app, "CADDYFILE_PATH", caddy_path):
            routes = app.read_caddy_routes()

        self.assertEqual(
            routes,
            [
                {
                    "sites": [
                        {"host": "foo.example.com", "protocol": "https", "port": 443, "path": ""},
                        {"host": "bar.example.com", "protocol": "https", "port": 8443, "path": ""},
                    ],
                    "upstreams": [{"host": "api", "port": 8080}],
                }
            ],
        )


class DiscoverServicesTests(unittest.TestCase):
    def test_discover_services_combines_published_ports_and_caddy_routes(self):
        containers = [{"Id": "abc"}]
        inspected = {
            "Id": "abc",
            "Name": "/demo",
            "Config": {
                "Image": "demo:latest",
                "Hostname": "demo",
                "Labels": {},
            },
            "NetworkSettings": {
                "Ports": {"3000/tcp": [{"HostPort": "3000"}]},
                "Networks": {"default": {"Aliases": ["demo"]}},
            },
        }
        routes = [
            {
                "sites": [{"host": "demo.example.com", "protocol": "https", "port": 443, "path": ""}],
                "upstreams": [{"host": "demo", "port": 3000}],
            }
        ]

        with patch.object(app, "HOSTNAME", "host.local"):
            with patch.object(app, "list_containers", return_value=containers):
                with patch.object(app, "inspect_container", return_value=inspected) as inspect_mock:
                    with patch.object(app, "read_caddy_routes", return_value=routes):
                        payload = app.discover_services()

        self.assertEqual(payload["defaultHost"], "host.local")
        self.assertEqual(
            payload["services"],
            [
                {
                    "name": "demo",
                    "port": 443,
                    "host": "demo.example.com",
                    "protocol": "https",
                    "path": "",
                    "description": "demo:latest",
                    "containerPort": "caddy",
                },
                {
                    "name": "demo",
                    "port": 3000,
                    "host": "host.local",
                    "protocol": "http",
                    "path": "",
                    "description": "demo:latest",
                    "containerPort": "3000/tcp",
                },
            ],
        )
        inspect_mock.assert_called_once_with("abc", unittest.mock.ANY)


class HandlerTests(unittest.TestCase):
    def test_serve_services_hides_internal_exception_details(self):
        handler = app.DashboardHandler.__new__(app.DashboardHandler)
        status_codes = []
        headers = []
        body = bytearray()

        handler.send_response = status_codes.append
        handler.send_header = lambda key, value: headers.append((key, value))
        handler.end_headers = lambda: None
        handler.wfile = type("Writer", (), {"write": body.extend})()

        with patch.object(app, "discover_services", side_effect=RuntimeError("socket missing")):
            handler.serve_services()

        self.assertEqual(status_codes, [500])
        self.assertIn(("Content-Type", "application/json; charset=utf-8"), headers)

        payload = json.loads(body.decode("utf-8"))
        self.assertEqual(payload["error"], app.SERVICE_DISCOVERY_ERROR)
        self.assertEqual(payload["services"], [])


if __name__ == "__main__":
    unittest.main()
