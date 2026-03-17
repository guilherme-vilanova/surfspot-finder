from typing import Dict, List, Optional

from .google_client import (
    GoogleGeocodingClient,
    GoogleGeocodingError,
    GooglePlacesClient,
    GooglePlacesError,
)
from surf_metadata import apply_surf_metadata, canonical_beach_name


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

    def find_nearby_beaches(self, lat: float, lon: float, radius_km: float) -> List[Dict[str, object]]:
        try:
            places = self.places_client.nearby_search(lat, lon, radius_km * 1000.0, included_types=["beach"])
            return self._normalize_beaches(places)
        except GooglePlacesError as exc:
            raise LocationServiceError(str(exc)) from exc

    def autocomplete_places(self, query: str) -> List[Dict[str, object]]:
        try:
            suggestions = self.places_client.autocomplete(query)
            return self._normalize_autocomplete_suggestions(suggestions)
        except GooglePlacesError as exc:
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

    def _normalize_beaches(self, places: List[Dict[str, object]]) -> List[Dict[str, object]]:
        beaches = []
        seen = set()

        for place in places:
            location = place.get("location") or {}
            name = ((place.get("displayName") or {}).get("text") or "").strip()
            lat = location.get("latitude")
            lon = location.get("longitude")
            primary_type = place.get("primaryType")
            types = place.get("types") or []

            if not name or lat is None or lon is None:
                continue

            if primary_type != "beach" and "beach" not in types:
                continue

            key = canonical_beach_name(name)
            if key in seen:
                continue

            seen.add(key)
            beaches.append(
                apply_surf_metadata(
                    {
                        "name": name,
                        "region": self._pick_region(place),
                        "lat": lat,
                        "lon": lon,
                        "place_id": place.get("id"),
                        "best_wind_label": "Any",
                        "best_wind_degrees": [0, 45, 90, 135, 180, 225, 270, 315],
                        "notes": "Beach discovered dynamically from Google Places near your selected location.",
                        "source": "google_places",
                    }
                )
            )

        return beaches

    def _pick_region(self, place: Dict[str, object]) -> str:
        address = (place.get("shortFormattedAddress") or place.get("formattedAddress") or "").strip()
        if not address:
            return "Nearby area"

        parts = [part.strip() for part in address.split(",") if part.strip()]
        if not parts:
            return "Nearby area"

        region = parts[0]
        if " - " in region:
            region = region.split(" - ", 1)[0].strip()

        return region or "Nearby area"

    def _normalize_autocomplete_suggestions(self, suggestions: List[Dict[str, object]]) -> List[Dict[str, object]]:
        normalized = []
        seen = set()

        for item in suggestions:
            prediction = item.get("placePrediction") or {}
            text = ((prediction.get("text") or {}).get("text") or "").strip()
            structured = prediction.get("structuredFormat") or {}
            main_text = ((structured.get("mainText") or {}).get("text") or "").strip()
            secondary_text = ((structured.get("secondaryText") or {}).get("text") or "").strip()
            place_id = prediction.get("placeId")

            value = text or main_text
            if not value:
                continue

            label = value
            if not label and secondary_text:
                label = f"{main_text}, {secondary_text}"
            meta = secondary_text or "Google Place"
            key = (label.casefold(), place_id)
            if key in seen:
                continue

            seen.add(key)
            normalized.append(
                {
                    "value": label,
                    "label": label,
                    "meta": meta,
                    "place_id": place_id,
                }
            )

        return normalized
