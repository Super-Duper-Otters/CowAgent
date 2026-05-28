# encoding:utf-8
import hashlib
from pathlib import Path


def file_fingerprint(path: str | Path) -> str:
    value = str(path)
    target = Path(value)
    if not target.is_absolute():
        target = Path.cwd() / target
    if not target.is_file():
        return f"missing:{value}"
    digest = hashlib.sha256()
    with target.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()[:16]}"
