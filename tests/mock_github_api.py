"""Minimal in-memory mock of the GitHub repository webhooks REST API.

It implements the subset of the endpoints used by the operator and its tests:

* ``GET    /repos/{owner}/{repo}/hooks``
* ``POST   /repos/{owner}/{repo}/hooks``
* ``DELETE /repos/{owner}/{repo}/hooks/{hook_id}``

A non-empty ``Authorization: Bearer <token>`` header is required, otherwise the
request is rejected with ``401`` so the tests still check that the operator
sends a token. The webhook state lives in memory, which is enough because a
single mock instance is used for the whole test session.
"""

import json
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Match /repos/{owner}/{repo}/hooks with an optional trailing /{hook_id}.
HOOKS_RE = re.compile(r"^/repos/[^/]+/[^/]+/hooks(?:/(\d+))?/?$")

_LOCK = threading.Lock()
_HOOKS: dict[int, dict] = {}
_NEXT_ID = 1


class MockGitHubHandler(BaseHTTPRequestHandler):
    """Serve the mocked GitHub webhooks endpoints."""

    server_version = "MockGitHubAPI/1.0"

    def _path(self) -> str:
        return self.path.split("?", 1)[0]

    def _authorized(self) -> bool:
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return False
        return len(auth.split(" ", 1)[1].strip()) > 0

    def _send(self, code: int, body: object | None = None) -> None:
        payload = b"" if body is None else json.dumps(body).encode()
        self.send_response(code)
        if body is not None:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if payload:
            self.wfile.write(payload)

    def _unauthorized(self) -> None:
        self._send(401, {"message": "Requires authentication"})

    def _not_found(self) -> None:
        self._send(404, {"message": "Not Found"})

    def do_GET(self) -> None:  # noqa: N802
        path = self._path()
        if path == "/healthz":
            self._send(200, {"status": "ok"})
            return
        match = HOOKS_RE.match(path)
        if match is None:
            self._not_found()
            return
        if not self._authorized():
            self._unauthorized()
            return
        hook_id = match.group(1)
        with _LOCK:
            if hook_id is None:
                self._send(200, list(_HOOKS.values()))
                return
            hook = _HOOKS.get(int(hook_id))
        if hook is None:
            self._not_found()
        else:
            self._send(200, hook)

    def do_POST(self) -> None:  # noqa: N802
        match = HOOKS_RE.match(self._path())
        # Only the collection endpoint (no hook id) supports creation.
        if match is None or match.group(1) is not None:
            self._not_found()
            return
        if not self._authorized():
            self._unauthorized()
            return
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        try:
            data = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._send(422, {"message": "Validation Failed"})
            return
        config = data.get("config", {})
        global _NEXT_ID  # noqa: PLW0603
        with _LOCK:
            hook_id = _NEXT_ID
            _NEXT_ID += 1
            hook = {
                "id": hook_id,
                "name": "web",
                "active": data.get("active", True),
                "events": data.get("events", ["push"]),
                "config": {
                    "url": config.get("url", ""),
                    "content_type": config.get("content_type", "form"),
                    "secret": config.get("secret", ""),
                },
            }
            _HOOKS[hook_id] = hook
        self._send(201, hook)

    def do_DELETE(self) -> None:  # noqa: N802
        match = HOOKS_RE.match(self._path())
        if match is None or match.group(1) is None:
            self._not_found()
            return
        if not self._authorized():
            self._unauthorized()
            return
        with _LOCK:
            _HOOKS.pop(int(match.group(1)), None)
        self._send(204)


def main() -> None:
    """Run the mock server forever."""
    port = int(os.environ.get("MOCK_PORT", "8080"))
    httpd = ThreadingHTTPServer(("0.0.0.0", port), MockGitHubHandler)  # noqa: S104
    httpd.serve_forever()


if __name__ == "__main__":
    main()
