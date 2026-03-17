import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional local convenience dependency
    def load_dotenv(*args, **kwargs):
        return False

from env_loader import load_local_env

BASE_DIR = Path(__file__).resolve().parents[1]
if not load_dotenv(BASE_DIR / ".env"):
    load_local_env(BASE_DIR / ".env")


def get_google_maps_api_key():
    return os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()


def get_google_geocoding_base_url():
    return os.environ.get(
        "GOOGLE_GEOCODING_BASE_URL",
        "https://maps.googleapis.com/maps/api/geocode/json",
    ).strip()


def get_google_places_textsearch_base_url():
    return os.environ.get(
        "GOOGLE_PLACES_TEXTSEARCH_BASE_URL",
        "https://places.googleapis.com/v1/places:searchText",
    ).strip()
