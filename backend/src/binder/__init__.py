"""Binder: AI administrative agent, 100% local."""

from importlib.metadata import PackageNotFoundError, version

try:
    # Releases set the version from the tag ("Release" workflow).
    __version__ = version("binder")
except PackageNotFoundError:  # pragma: no cover - sources not installed
    __version__ = "0.0.0"
