from typing import Dict, Optional

import requests

from .config import get_google_geocoding_base_url, get_google_maps_api_key


class GoogleGeocodingError(Exception):
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
