from typing import Dict, Optional

from .google_client import (
    GoogleGeocodingClient,
    GoogleGeocodingError,
    GooglePlacesClient,
    GooglePlacesError,
)


class LocationServiceError(Exception):
    pass


class GoogleLocationService:
    def __init__(
        self,
        client: Optional[GoogleGeocodingClient] = None,
        places_client: Optional[GooglePlacesClient] = None,
    ):
        self.client = client or GoogleGeocodingClient()
        self.places_client = places_client or GooglePlacesClient()

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

    def find_place(self, query: str, lat: Optional[float] = None, lon: Optional[float] = None) -> Dict[str, object]:
        try:
            result = self.places_client.text_search(query, lat=lat, lon=lon)
            return self._normalize(result)
        except GooglePlacesError as exc:
            raise LocationServiceError(str(exc)) from exc

    def _normalize(self, result: Dict[str, object]) -> Dict[str, object]:
        geometry = result.get("geometry", {})
        location = geometry.get("location", {}) or result.get("location", {})

        return {
            "formatted_address": result.get("formatted_address", result.get("formattedAddress", "Unknown location")),
            "lat": location.get("lat", location.get("latitude")),
            "lon": location.get("lng", location.get("longitude")),
            "place_id": result.get("place_id", result.get("id")),
        }
