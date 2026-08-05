"""Multi-tenant plumbing for the synthetic twin.

Each *shop* is an isolated synthetic brand with its own data directory; one codebase serves them all.
This is the public demo of the real engine's data-source-per-tenant design — here every shop's source is
a CSV dir under data/shops/<slug>/; in production a shop's source can be a warehouse schema or a Postgres
DSN behind the same interface. The three moving parts:

  - a request-scoped "current shop" (contextvar), set once per request by the server from ?shop= / cookie;
  - a per-shop cache decorator so one shop's data can never bleed into another's;
  - a registry loaded from data/shops/index.json (slug, display name, niche, competitors, ...).
"""
import contextvars
import json
import os
from functools import wraps

SHOPS_DIR = "data/shops"
_current = contextvars.ContextVar("shop", default=None)
_REGISTRY = None


def _load_registry():
    path = os.path.join(SHOPS_DIR, "index.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return {s["slug"]: s for s in json.load(f)}
    return {}


def registry():
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _load_registry()
    return _REGISTRY


def reload_registry():
    global _REGISTRY
    _REGISTRY = None
    return registry()


def default_shop():
    return next(iter(registry()), "aurora")


def valid_shop(slug):
    return slug in registry()


def set_shop(slug):
    """Set the current request's shop; unknown/blank falls back to the default (never trust the input)."""
    _current.set(slug if valid_shop(slug) else default_shop())


def current_shop():
    return _current.get() or default_shop()


def shop_dir(shop=None):
    return os.path.join(SHOPS_DIR, shop or current_shop())


def shop_config(shop=None):
    return registry().get(shop or current_shop(), {})


def list_shops():
    return list(registry().values())


def shop_cache(fn):
    """lru_cache-style memoization PARTITIONED by the current shop (and the call args). The whole point
    of multi-tenancy: shop A's cached decision queue must never be returned for shop B."""
    caches = {}

    @wraps(fn)
    def wrapper(*args, **kwargs):
        key = (current_shop(), args, tuple(sorted(kwargs.items())))
        if key not in caches:
            caches[key] = fn(*args, **kwargs)
        return caches[key]

    wrapper.cache_clear = caches.clear
    return wrapper
