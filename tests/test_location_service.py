import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp_server.google_client import GoogleGeocodingClient, GoogleGeocodingError
from mcp_server.location_service import GoogleLocationService


class GoogleGeocodingClientTests(unittest.TestCase):
    def test_geocode_returns_first_result(self):
        client = GoogleGeocodingClient(api_key="test-key", base_url="https://example.com")
        response = Mock()
        response.json.return_value = {
            "status": "OK",
            "results": [
                {
                    "formatted_address": "Florianopolis, SC, Brazil",
                    "geometry": {"location": {"lat": -27.5954, "lng": -48.5480}},
                    "place_id": "abc123",
                }
            ],
        }
        response.raise_for_status.return_value = None
        client.session.get = Mock(return_value=response)

        result = client.geocode("Florianopolis")

        self.assertEqual(result["formatted_address"], "Florianopolis, SC, Brazil")

    def test_missing_key_raises_clear_error(self):
        client = GoogleGeocodingClient(api_key="", base_url="https://example.com")

        with self.assertRaises(GoogleGeocodingError):
            client.geocode("Florianopolis")


class GoogleLocationServiceTests(unittest.TestCase):
    def test_normalizes_google_payload(self):
        client = Mock()
        client.reverse_geocode.return_value = {
            "formatted_address": "Garopaba, State of Santa Catarina, Brazil",
            "geometry": {"location": {"lat": -28.0226, "lng": -48.6138}},
            "place_id": "place-999",
        }
        service = GoogleLocationService(client=client)

        result = service.reverse_geocode(-28.0226, -48.6138)

        self.assertEqual(
            result,
            {
                "formatted_address": "Garopaba, State of Santa Catarina, Brazil",
                "lat": -28.0226,
                "lon": -48.6138,
                "place_id": "place-999",
            },
        )


if __name__ == "__main__":
    unittest.main()
