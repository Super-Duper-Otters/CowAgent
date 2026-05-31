# encoding:utf-8
import hashlib
import os
import threading
import time
from dataclasses import dataclass


IMAGE_MEDIA_CACHE_TTL_SECONDS = 70 * 60 * 60


@dataclass(frozen=True)
class LocalImageMediaKey:
    path: str
    mtime_ns: int
    size: int
    sha256: str


@dataclass
class ImageMediaCacheEntry:
    media_id: str
    expires_at: float


class ImageMediaCache:
    def __init__(self, ttl_seconds=IMAGE_MEDIA_CACHE_TTL_SECONDS, now_func=None):
        self.ttl_seconds = ttl_seconds
        self._now = now_func or time.time
        self._cache = {}
        self._lock = threading.RLock()

    def get(self, key):
        if key is None:
            return None
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            if entry.expires_at <= self._now():
                self._cache.pop(key, None)
                return None
            return entry.media_id

    def set(self, key, media_id):
        if key is None or not media_id:
            return
        with self._lock:
            self._cache[key] = ImageMediaCacheEntry(
                media_id=media_id,
                expires_at=self._now() + self.ttl_seconds,
            )

    def clear(self):
        with self._lock:
            self._cache.clear()


def local_image_media_key(value):
    if not isinstance(value, str):
        return None
    if value.startswith("file://"):
        value = value[7:]
    if not os.path.exists(value):
        return None
    try:
        stat_result = os.stat(value)
    except OSError:
        return None
    try:
        file_hash = hashlib.sha256()
        with open(value, "rb") as image_file:
            for chunk in iter(lambda: image_file.read(1024 * 1024), b""):
                file_hash.update(chunk)
    except OSError:
        return None
    return LocalImageMediaKey(
        path=os.path.abspath(value),
        mtime_ns=getattr(stat_result, "st_mtime_ns", int(stat_result.st_mtime * 1000000000)),
        size=stat_result.st_size,
        sha256=file_hash.hexdigest(),
    )


image_media_cache = ImageMediaCache()
