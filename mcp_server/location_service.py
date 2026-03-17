from typing import Dict, Optional

from .google_client import GoogleGeocodingClient, GoogleGeocodingError


class LocationServiceError(Exception):
    pass


class GoogleLocationService:
    def __init__(self, client: Optional[GoogleGeocodingClient] = None):
        self.client = client or GoogleGeocodingClient()

    @classmethod
    def from_env(cls):
        return cls()

    def geocode_address(self, query: str) -> Dict[str, object]:
        try:
            result = self.client.geocode(query)
            return self._normalize(result)
        except GoogleGeocodingError as exc:
            raise LocationServiceError(str(exc)) from exc

    def reverse_geocode(self, lat: float, lon: float) -> Dict[str, object]:
        try:
            result = self.client.reverse_geocode(lat, lon)
            return self._normalize(result)
        except GoogleGeocodingError as exc:
            raise LocationServiceError(str(exc)) from exc

    def _normalize(self, result: Dict[str, object]) -> Dict[str, object]:
        geometry = result.get("geometry", {})
        location = geometry.get("location", {})

        return {
            "formatted_address": result.get("formatted_address", "Unknown location"),
            "lat": location.get("lat"),
            "lon": location.get("lng"),
            "place_id": result.get("place_id"),
        }
