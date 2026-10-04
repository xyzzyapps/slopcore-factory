"""A tiny service locator.

The pipeline asks the locator for the implementation of an interface by name.
Production code registers the real providers; tests register fakes. This keeps
the feature slices free of import-time coupling to concrete providers.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class ServiceLocator:
    """Registry of factories keyed by a service name."""

    def __init__(self) -> None:
        self._factories: dict[str, Callable[..., Any]] = {}
        self._instances: dict[str, Any] = {}

    def register(self, name: str, factory: Callable[..., Any], *, cache: bool = True) -> None:
        """Register a factory (a class or a callable) under ``name``."""
        self._factories[name] = factory
        if cache and name in self._instances:
            del self._instances[name]

    def register_instance(self, name: str, instance: Any) -> None:
        """Register a ready-made instance (used by tests)."""
        self._instances[name] = instance

    def get(self, name: str, **kwargs: Any) -> Any:
        """Resolve a service, constructing and caching it on first use."""
        if name in self._instances:
            return self._instances[name]
        if name not in self._factories:
            raise KeyError(f"service not registered: {name}")
        instance = self._factories[name](**kwargs)
        self._instances[name] = instance
        return instance

    def has(self, name: str) -> bool:
        return name in self._factories or name in self._instances

    def clear(self) -> None:
        self._instances.clear()
        self._factories.clear()


# A process-wide default locator. Tests may build their own.
locator = ServiceLocator()
