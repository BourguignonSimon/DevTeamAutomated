"""Minimal HTTP gateway to seed PROJECT.INITIAL_REQUEST_RECEIVED via curl.

This avoids needing direct Redis commands for quick demos. Start the server
while docker-compose is running, then POST JSON payloads to publish events.
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from uuid import uuid4

from core.config import Settings
from core.event_utils import envelope
from core.redis_streams import build_redis_client


settings = Settings()
redis_client = build_redis_client(settings.redis_host, settings.redis_port, settings.redis_db)


class GatewayHandler(BaseHTTPRequestHandler):
    def _send_response(self, status: int, payload: dict) -> None:
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args) -> None:  # pragma: no cover - stdlib logging noise
        return

    def do_POST(self) -> None:  # noqa: N802 - stdlib interface
        if self.path != "/initial-request":
            self._send_response(404, {"error": "not_found"})
            return

        length = int(self.headers.get("Content-Length", 0))
        try:
            raw_body = self.rfile.read(length) if length else b"{}"
            body = json.loads(raw_body.decode())
        except json.JSONDecodeError:
            self._send_response(400, {"error": "invalid_json"})
            return

        request_text = body.get("request_text")
        project_id = body.get("project_id") or str(uuid4())
        if not request_text:
            self._send_response(400, {"error": "request_text_required"})
            return

        env = envelope(
            event_type="PROJECT.INITIAL_REQUEST_RECEIVED",
            payload={
                "project_id": project_id,
                "request_text": request_text,
                "requester": body.get("requester") or {"name": "demo"},
            },
            source="http_gateway",
            correlation_id=str(uuid4()),
            causation_id=None,
        )
        redis_id = redis_client.xadd(settings.stream_name, {"event": json.dumps(env)})
        self._send_response(201, {"event_id": env["event_id"], "redis_id": redis_id, "project_id": project_id})


def main() -> None:
    port = int(os.getenv("GATEWAY_PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), GatewayHandler)
    print(f"HTTP gateway listening on :{port} -> stream {settings.stream_name}")
    server.serve_forever()


if __name__ == "__main__":
    main()
