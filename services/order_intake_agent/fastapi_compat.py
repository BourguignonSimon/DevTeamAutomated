from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict


class HTTPException(Exception):
    def __init__(self, status_code: int, detail: Any = None):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class _Status:
    HTTP_404_NOT_FOUND = 404


status = _Status()


def Depends(dep):
    return dep


def Form(default=None):
    return default


def File(default=None):
    return default


class UploadFile:
    def __init__(self, filename: str, content: bytes, content_type: str | None = None):
        self.filename = filename
        self._content = content
        self.content_type = content_type or "application/octet-stream"

    async def read(self) -> bytes:
        return self._content


class JSONResponse:
    def __init__(self, content: Any, status_code: int = 200):
        self._content = content
        self.status_code = status_code

    def json(self):
        return self._content


class FastAPI:
    def __init__(self):
        self.routes: Dict[tuple[str, str], Callable[..., Any]] = {}

    def post(self, path: str):
        def decorator(func: Callable[..., Any]):
            self.routes[("POST", path)] = func
            return func

        return decorator

    def get(self, path: str):
        def decorator(func: Callable[..., Any]):
            self.routes[("GET", path)] = func
            return func

        return decorator


class TestClient:
    def __init__(self, app: FastAPI):
        self.app = app

    def _match(self, method: str, path: str):
        if (method, path) in self.app.routes:
            return self.app.routes[(method, path)], {}
        for (meth, route_path), handler in self.app.routes.items():
            if meth != method:
                continue
            route_parts = route_path.strip("/").split("/")
            path_parts = path.strip("/").split("/")
            if len(route_parts) != len(path_parts):
                continue
            params: Dict[str, Any] = {}
            matched = True
            for r, p in zip(route_parts, path_parts):
                if r.startswith("{") and r.endswith("}"):
                    params[r.strip("{} ")] = p
                elif r != p:
                    matched = False
                    break
            if matched:
                return handler, params
        return None, None

    def _call(self, method: str, path: str, *, files=None, data=None, json_data=None):
        handler, path_params = self._match(method, path)
        if not handler:
            return JSONResponse({"error": "not_found"}, status_code=404)
        kwargs: Dict[str, Any] = {**(path_params or {})}
        if files:
            uploads = []
            iterable = files.items() if isinstance(files, dict) else files
            for _, file_tuple in iterable:
                filename, content, content_type = file_tuple
                uploads.append(UploadFile(filename, content, content_type))
            kwargs["files"] = uploads
        if data:
            kwargs.update(data)
        if json_data is not None:
            kwargs["corrections"] = json_data
        result = handler(**kwargs)
        if asyncio.iscoroutine(result):
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            result = loop.run_until_complete(result)
        if isinstance(result, JSONResponse):
            return result
        if isinstance(result, dict):
            return JSONResponse(result)
        return JSONResponse(result)

    def post(self, path: str, *, files=None, data=None, json=None):  # type: ignore[override]
        return self._call("POST", path, files=files, data=data, json_data=json)

    def get(self, path: str):
        return self._call("GET", path)


__all__ = [
    "FastAPI",
    "Form",
    "File",
    "UploadFile",
    "HTTPException",
    "status",
    "Depends",
    "JSONResponse",
    "TestClient",
]
