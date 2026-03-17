import json
import threading
import time
from pathlib import Path


class PersistentTTLCache:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._store = self._load()

    def _load(self):
        if not self.path.exists():
            return {}

        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self):
        self.path.write_text(json.dumps(self._store), encoding="utf-8")

    @staticmethod
    def _normalize_key(namespace, key):
        return json.dumps([namespace, key], sort_keys=True)

    def get(self, namespace, key):
        normalized_key = self._normalize_key(namespace, key)

        with self._lock:
            entry = self._store.get(normalized_key)
            if not entry:
                return None

            if time.time() > entry["expires_at"]:
                del self._store[normalized_key]
                self._save()
                return None

            return entry["value"]

    def set(self, namespace, key, value, ttl_seconds):
        normalized_key = self._normalize_key(namespace, key)

        with self._lock:
            self._store[normalized_key] = {
                "expires_at": time.time() + ttl_seconds,
                "value": value,
            }
            self._save()

    def clear(self):
        with self._lock:
            self._store = {}
            self._save()
