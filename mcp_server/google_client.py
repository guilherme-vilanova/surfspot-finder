from typing import Dict, List, Optional

import requests

from .config import (
    get_google_geocoding_base_url,
    get_google_maps_api_key,
    get_google_places_autocomplete_base_url,
    get_google_places_nearby_base_url,
)


class GoogleGeocodingError(Exception):
    pass


class GooglePlacesError(Exception):
    pass


class GoogleGeocodingClient:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, timeout: int = 10):
        self.api_key = api_key if api_key is not None else get_google_maps_api_key()
        self.base_url = base_url if base_url is not None else get_google_geocoding_base_url()
        self.timeout = timeout
        self.session = requests.Session()

    def _request(self, params: Dict[str, str]):
        if not self.api_key:
            raise GoogleGeocodingError(
                "Google Maps API key is missing. Set GOOGLE_MAPS_API_KEY before searching."
            )

        query_params = dict(params)
        query_params["key"] = self.api_key

        try:
            response = self.session.get(self.base_url, params=query_params, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise GoogleGeocodingError(
                "Google Geocoding API is unavailable right now. Please try again."
            ) from exc

        payload = response.json()
        status = payload.get("status")
        if status == "OK":
            return payload
        if status == "ZERO_RESULTS":
            raise GoogleGeocodingError("Location not found. Try a more specific address or city.")
        if status == "REQUEST_DENIED":
            raise GoogleGeocodingError(
                "Google rejected the request. Check whether the API key and API restrictions are correct."
            )
        if status == "OVER_QUERY_LIMIT":
            raise GoogleGeocodingError("Google API quota reached. Try again later or review your quota settings.")
        if status == "INVALID_REQUEST":
            raise GoogleGeocodingError("The Google geocoding request was invalid.")

        error_message = payload.get("error_message")
        if error_message:
            raise GoogleGeocodingError(error_message)

        raise GoogleGeocodingError(f"Google geocoding failed with status {status}.")

    def geocode(self, query: str):
        payload = self._request({"address": query})
        return payload["results"][0]

    def reverse_geocode(self, lat: float, lon: float):
        payload = self._request({"latlng": f"{lat},{lon}"})
        return payload["results"][0]


class GooglePlacesClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        nearby_base_url: Optional[str] = None,
        autocomplete_base_url: Optional[str] = None,
        timeout: int = 10,
    ):
        self.api_key = api_key if api_key is not None else get_google_maps_api_key()
        self.nearby_base_url = (
            nearby_base_url if nearby_base_url is not None else get_google_places_nearby_base_url()
        )
        self.autocomplete_base_url = (
            autocomplete_base_url
            if autocomplete_base_url is not None
            else get_google_places_autocomplete_base_url()
        )
        self.timeout = timeout
        self.session = requests.Session()

    def _headers(self, field_mask: str) -> Dict[str, str]:
        if not self.api_key:
            raise GooglePlacesError(
                "Google Maps API key is missing. Set GOOGLE_MAPS_API_KEY before searching."
            )

        return {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": field_mask,
        }

    def _google_error_message(self, response: requests.Response, default_message: str) -> str:
        try:
            payload = response.json()
        except ValueError:
            return default_message

        error = payload.get("error") or {}
        return error.get("message") or default_message

    def nearby_search(
        self,
        lat: float,
        lon: float,
        radius_m: float,
        included_types: Optional[List[str]] = None,
        max_result_count: int = 20,
        rank_preference: str = "DISTANCE",
    ):
        headers = self._headers(
            ",".join(
                [
                    "places.displayName",
                    "places.formattedAddress",
                    "places.shortFormattedAddress",
                    "places.location",
                    "places.types",
                    "places.primaryType",
                    "places.id",
                ]
            )
        )
        payload = {
            "includedTypes": included_types or ["beach"],
            "maxResultCount": max(1, min(max_result_count, 20)),
            "rankPreference": rank_preference,
            "locationRestriction": {
                "circle": {
                    "center": {
                        "latitude": lat,
                        "longitude": lon,
                    },
                    "radius": max(1.0, min(float(radius_m), 50000.0)),
                }
            },
        }

        try:
            response = self.session.post(
                self.nearby_base_url,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise GooglePlacesError(
                "Google Places API is unavailable right now. Please try again."
            ) from exc

        if not response.ok:
            raise GooglePlacesError(
                self._google_error_message(response, "Google Places search failed.")
            )

        payload = response.json()
        if "error" in payload:
            message = payload["error"].get("message") or "Google Places search failed."
            raise GooglePlacesError(message)

        return payload.get("places", [])

    def autocomplete(self, text_input: str, included_primary_types: Optional[List[str]] = None):
        headers = self._headers(
            ",".join(
                [
                    "suggestions.placePrediction.placeId",
                    "suggestions.placePrediction.text.text",
                    "suggestions.placePrediction.structuredFormat.mainText.text",
                    "suggestions.placePrediction.structuredFormat.secondaryText.text",
                    "suggestions.placePrediction.types",
                ]
            )
        )
        payload = {
            "input": text_input,
            "includeQueryPredictions": False,
        }
        if included_primary_types:
            payload["includedPrimaryTypes"] = included_primary_types

        try:
            response = self.session.post(
                self.autocomplete_base_url,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise GooglePlacesError(
                "Google Places autocomplete is unavailable right now. Please try again."
            ) from exc

        if not response.ok:
            raise GooglePlacesError(
                self._google_error_message(response, "Google Places autocomplete failed.")
            )

        payload = response.json()
        if "error" in payload:
            message = payload["error"].get("message") or "Google Places autocomplete failed."
            raise GooglePlacesError(message)

        return payload.get("suggestions", [])
