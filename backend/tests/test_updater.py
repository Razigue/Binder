"""Automatic update (Velopack): what Binder reads from its update manager."""

from types import SimpleNamespace

from binder import updater


def release_info(full: int, deltas: list[int]) -> SimpleNamespace:
    return SimpleNamespace(
        TargetFullRelease=SimpleNamespace(Size=full),
        DeltasToTarget=[SimpleNamespace(Size=size) for size in deltas],
    )


def test_download_size_prefers_deltas() -> None:
    assert updater.download_size(release_info(500, [20, 30])) == 50


def test_download_size_falls_back_on_full_package() -> None:
    assert updater.download_size(release_info(500, [])) == 500


def test_not_installed_from_sources() -> None:
    assert updater.installed() is None
