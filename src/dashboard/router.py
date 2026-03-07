"""Route registration table and dispatcher for the dashboard HTTP server."""

from __future__ import annotations

from typing import Any, Callable

RouteHandler = Callable[["DashboardHandler"], None]  # type: ignore[name-defined]

_GET_ROUTES: dict[str, RouteHandler] = {}
_POST_ROUTES: dict[str, RouteHandler] = {}
_PUT_ROUTES: dict[str, RouteHandler] = {}


def get(path: str):
    """Register a GET route handler."""
    def decorator(fn: RouteHandler) -> RouteHandler:
        _GET_ROUTES[path] = fn
        return fn
    return decorator


def post(path: str):
    """Register a POST route handler."""
    def decorator(fn: RouteHandler) -> RouteHandler:
        _POST_ROUTES[path] = fn
        return fn
    return decorator


def put(path: str):
    """Register a PUT route handler."""
    def decorator(fn: RouteHandler) -> RouteHandler:
        _PUT_ROUTES[path] = fn
        return fn
    return decorator


def dispatch_get(path: str) -> RouteHandler | None:
    return _GET_ROUTES.get(path)


def dispatch_post(path: str) -> RouteHandler | None:
    return _POST_ROUTES.get(path)


def dispatch_put(path: str) -> RouteHandler | None:
    return _PUT_ROUTES.get(path)


def all_routes() -> dict[str, list[str]]:
    """Return summary of registered routes (for debugging)."""
    return {
        "GET": sorted(_GET_ROUTES.keys()),
        "POST": sorted(_POST_ROUTES.keys()),
        "PUT": sorted(_PUT_ROUTES.keys()),
    }
