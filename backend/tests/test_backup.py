"""Restoring a backup refuses, in words, an archive that is not one Binder wrote."""

import json
import zipfile
from pathlib import Path

import pytest

from binder.services import backup


@pytest.mark.parametrize(
    "recovery", [b"not json", b"[]", json.dumps({"salt": "x"}).encode(), b'{"salt":1,"wrapped":2}']
)
def test_a_damaged_recovery_file_is_not_a_backup(tmp_path: Path, recovery: bytes) -> None:
    archive = tmp_path / f"Binder{backup.EXTENSION}"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("binder.db", b"")
        z.writestr("recovery.json", recovery)
    with pytest.raises(ValueError, match=backup.T("not_backup")) as raised:
        backup.restore(archive, "ABCD-EFGH")
    assert not isinstance(raised.value, backup.WrongCode)
