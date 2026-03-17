import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp_server.google_client import (
    GoogleGeocodingClient,
    GoogleGeocodingError,
    GooglePlacesClient,
)
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


class GooglePlacesClientTests(unittest.TestCase):
    def test_nearby_search_posts_expected_payload(self):
        client = GooglePlacesClient(api_key="test-key", nearby_base_url="https://example.com")
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "places": [
                {
                    "id": "beach-1",
                    "displayName": {"text": "Praia da Silveira"},
                    "shortFormattedAddress": "Garopaba - State of Santa Catarina",
                    "formattedAddress": "Praia da Silveira, Garopaba - State of Santa Catarina, Brazil",
                    "location": {"latitude": -28.024, "longitude": -48.621},
                    "primaryType": "beach",
                    "types": ["beach", "tourist_attraction"],
                }
            ]
        }
        client.session.post = Mock(return_value=response)

        result = client.nearby_search(-28.024, -48.621, 120000)

        self.assertEqual(result[0]["id"], "beach-1")
        _, kwargs = client.session.post.call_args
        self.assertEqual(kwargs["json"]["includedTypes"], ["beach"])
        self.assertEqual(kwargs["json"]["rankPreference"], "DISTANCE")
        self.assertEqual(kwargs["json"]["locationRestriction"]["circle"]["radius"], 50000.0)
        self.assertEqual(kwargs["headers"]["X-Goog-Api-Key"], "test-key")

    def test_autocomplete_posts_expected_payload(self):
        client = GooglePlacesClient(
            api_key="test-key",
            autocomplete_base_url="https://example.com/autocomplete",
        )
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "suggestions": [
                {
                    "placePrediction": {
                        "placeId": "place-1",
                        "text": {"text": "Laguna, State of Santa Catarina, Brazil"},
                        "structuredFormat": {
                            "mainText": {"text": "Laguna"},
                            "secondaryText": {"text": "State of Santa Catarina, Brazil"},
                        },
                        "types": ["locality"],
                    }
                }
            ]
        }
        client.session.post = Mock(return_value=response)

        result = client.autocomplete("Lagu")

        self.assertEqual(result[0]["placePrediction"]["placeId"], "place-1")
        _, kwargs = client.session.post.call_args
        self.assertEqual(kwargs["json"]["input"], "Lagu")
        self.assertEqual(kwargs["headers"]["X-Goog-Api-Key"], "test-key")


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

    def test_normalizes_google_places_payload_into_beaches(self):
        places_client = Mock()
        places_client.nearby_search.return_value = [
            {
                "id": "beach-1",
                "displayName": {"text": "Praia da Silveira"},
                "shortFormattedAddress": "Garopaba - State of Santa Catarina",
                "formattedAddress": "Praia da Silveira, Garopaba - State of Santa Catarina, Brazil",
                "location": {"latitude": -28.024, "longitude": -48.621},
                "primaryType": "beach",
                "types": ["beach", "tourist_attraction"],
            }
        ]
        service = GoogleLocationService(client=Mock(), places_client=places_client)

        result = service.find_nearby_beaches(-28.024, -48.621, 25)

        self.assertEqual(
            result,
            [
                {
                    "name": "Praia da Silveira",
                    "region": "Garopaba",
                    "lat": -28.024,
                    "lon": -48.621,
                    "place_id": "beach-1",
                    "best_wind_label": "Any",
                    "best_wind_degrees": [0, 45, 90, 135, 180, 225, 270, 315],
                    "preferred_swell_label": "SE / S",
                    "preferred_swell_degrees": [135, 180],
                    "notes": "Beach discovered dynamically from Google Places near your selected location.",
                    "source": "google_places",
                }
            ],
        )

    def test_normalizes_google_places_payload_deduplicates_equivalent_beach_names(self):
        places_client = Mock()
        places_client.nearby_search.return_value = [
            {
                "id": "beach-1",
                "displayName": {"text": "Praia da Silveira"},
                "shortFormattedAddress": "Garopaba - State of Santa Catarina",
                "formattedAddress": "Praia da Silveira, Garopaba - State of Santa Catarina, Brazil",
                "location": {"latitude": -28.024, "longitude": -48.621},
                "primaryType": "beach",
                "types": ["beach"],
            },
            {
                "id": "beach-2",
                "displayName": {"text": "Silveira"},
                "shortFormattedAddress": "Garopaba - State of Santa Catarina",
                "formattedAddress": "Silveira, Garopaba - State of Santa Catarina, Brazil",
                "location": {"latitude": -28.0245, "longitude": -48.6213},
                "primaryType": "beach",
                "types": ["beach"],
            },
        ]
        service = GoogleLocationService(client=Mock(), places_client=places_client)

        result = service.find_nearby_beaches(-28.024, -48.621, 25)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Praia da Silveira")

    def test_normalizes_google_places_payload_applies_expanded_swell_metadata(self):
        places_client = Mock()
        places_client.nearby_search.return_value = [
            {
                "id": "beach-3",
                "displayName": {"text": "Praia da Ferrugem"},
                "shortFormattedAddress": "Garopaba - State of Santa Catarina",
                "formattedAddress": "Praia da Ferrugem, Garopaba - State of Santa Catarina, Brazil",
                "location": {"latitude": -28.064, "longitude": -48.622},
                "primaryType": "beach",
                "types": ["beach"],
            }
        ]
        service = GoogleLocationService(client=Mock(), places_client=places_client)

        result = service.find_nearby_beaches(-28.064, -48.622, 25)

        self.assertEqual(result[0]["preferred_swell_label"], "S / SE")
        self.assertEqual(result[0]["preferred_swell_degrees"], [180, 135])

    def test_normalizes_google_places_payload_applies_metadata_for_alias_name(self):
        places_client = Mock()
        places_client.nearby_search.return_value = [
            {
                "id": "beach-4",
                "displayName": {"text": "Moçambique"},
                "shortFormattedAddress": "Florianopolis - State of Santa Catarina",
                "formattedAddress": "Moçambique, Florianopolis - State of Santa Catarina, Brazil",
                "location": {"latitude": -27.503, "longitude": -48.398},
                "primaryType": "beach",
                "types": ["beach"],
            }
        ]
        service = GoogleLocationService(client=Mock(), places_client=places_client)

        result = service.find_nearby_beaches(-27.503, -48.398, 25)

        self.assertEqual(result[0]["preferred_swell_label"], "E / SE")
        self.assertEqual(result[0]["preferred_swell_degrees"], [90, 135])

    def test_normalizes_google_places_autocomplete_payload(self):
        places_client = Mock()
        places_client.autocomplete.return_value = [
            {
                "placePrediction": {
                    "placeId": "place-1",
                    "text": {"text": "Laguna, State of Santa Catarina, Brazil"},
                    "structuredFormat": {
                        "mainText": {"text": "Laguna"},
                        "secondaryText": {"text": "State of Santa Catarina, Brazil"},
                    },
                }
            }
        ]
        service = GoogleLocationService(client=Mock(), places_client=places_client)

        result = service.autocomplete_places("Lagu")

        self.assertEqual(
            result,
            [
                {
                    "value": "Laguna, State of Santa Catarina, Brazil",
                    "label": "Laguna, State of Santa Catarina, Brazil",
                    "meta": "State of Santa Catarina, Brazil",
                    "place_id": "place-1",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
