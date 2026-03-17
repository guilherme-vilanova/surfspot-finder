import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app as surf_app
from persistent_cache import PersistentTTLCache


class AppLocationFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.original_disk_cache = surf_app.disk_cache
        surf_app.disk_cache = PersistentTTLCache(Path(self.temp_dir.name) / "cache.json")
        self.client = surf_app.app.test_client()
        surf_app.search_cache.clear()
        surf_app.beach_discovery_cache.clear()
        surf_app.marine_cache.clear()
        surf_app.forecast_cache.clear()

    def tearDown(self):
        surf_app.disk_cache = self.original_disk_cache
        self.temp_dir.cleanup()

    def test_requires_location_when_no_origin_is_provided(self):
        response = self.client.post("/", data={})

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Enter a location or use your current location.", response.data)

    def test_home_limits_radius_options_to_google_places_range(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'id="location-autocomplete"', response.data)
        self.assertIn(b'>30 km<', response.data)
        self.assertIn(b'>50 km<', response.data)
        self.assertNotIn(b'>120 km<', response.data)
        self.assertNotIn(b'>160 km<', response.data)
        self.assertNotIn(b'>220 km<', response.data)

    @patch.object(surf_app, "build_rankings_with_radius_fallback")
    @patch.object(surf_app.location_service, "geocode_address")
    def test_manual_location_search_uses_google_resolution(self, geocode_mock, rankings_mock):
        geocode_mock.return_value = {
            "formatted_address": "Florianopolis, State of Santa Catarina, Brazil",
            "lat": -27.5954,
            "lon": -48.5480,
            "place_id": "place-123",
        }
        rankings_mock.return_value = (
            {
                "name": "Florianopolis, State of Santa Catarina, Brazil",
                "lat": -27.5954,
                "lon": -48.5480,
                "source": "manual",
            },
            [],
            50,
            None,
        )

        response = self.client.post(
            "/",
            data={
                "location_query": "Florianopolis",
                "max_distance_km": "50",
                "result_limit": "5",
                "skill_level": "beginner",
            },
        )

        self.assertEqual(response.status_code, 200)
        geocode_mock.assert_called_once_with("Florianopolis")
        rankings_mock.assert_called_once()

    @patch.object(surf_app, "build_rankings_with_radius_fallback")
    @patch.object(surf_app.location_service, "geocode_address")
    def test_manual_location_search_clamps_radius_to_google_limit(self, geocode_mock, rankings_mock):
        geocode_mock.return_value = {
            "formatted_address": "Florianopolis, State of Santa Catarina, Brazil",
            "lat": -27.5954,
            "lon": -48.5480,
            "place_id": "place-123",
        }
        rankings_mock.return_value = (
            {
                "name": "Florianopolis, State of Santa Catarina, Brazil",
                "lat": -27.5954,
                "lon": -48.5480,
                "source": "manual",
            },
            [],
            50,
            None,
        )

        self.client.post(
            "/",
            data={
                "location_query": "Florianopolis",
                "max_distance_km": "120",
                "result_limit": "5",
                "skill_level": "beginner",
            },
        )

        self.assertEqual(rankings_mock.call_args.kwargs["max_distance_km"], 50)

    @patch.object(surf_app.location_service, "reverse_geocode")
    def test_reverse_geocode_endpoint(self, reverse_mock):
        reverse_mock.return_value = {
            "formatted_address": "Joaquina Beach, Florianopolis - SC, Brazil",
            "lat": -27.6293,
            "lon": -48.4490,
            "place_id": "place-456",
        }

        response = self.client.post("/api/reverse-geocode", json={"lat": -27.6293, "lon": -48.4490})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["formatted_address"], "Joaquina Beach, Florianopolis - SC, Brazil")

    @patch.object(surf_app.location_service, "autocomplete_places")
    def test_location_autocomplete_endpoint_uses_google_places(self, autocomplete_mock):
        autocomplete_mock.return_value = [
            {
                "value": "Laguna, State of Santa Catarina, Brazil",
                "label": "Laguna, State of Santa Catarina, Brazil",
                "meta": "State of Santa Catarina, Brazil",
                "place_id": "place-1",
            }
        ]

        response = self.client.get("/api/location-autocomplete?q=Lagu")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["suggestions"][0]["place_id"], "place-1")
        autocomplete_mock.assert_called_once_with("Lagu")

    @patch.object(surf_app, "evaluate_beach")
    @patch.object(surf_app.location_service, "find_nearby_beaches")
    def test_build_rankings_uses_google_places_beaches_within_radius(self, places_mock, evaluate_mock):
        places_mock.return_value = [
            {
                "name": "Praia de Ipanema",
                "region": "Porto Alegre",
                "lat": -30.1568,
                "lon": -51.2188,
                "best_wind_label": "Any",
                "best_wind_degrees": [0, 45, 90, 135, 180, 225, 270, 315],
                "preferred_swell_label": "E / SE",
                "preferred_swell_degrees": [90, 135],
                "notes": "Beach discovered dynamically from Google Places near your selected location.",
                "source": "google_places",
            }
        ]
        evaluate_mock.side_effect = lambda beach, skill_level: {
            "name": beach["name"],
            "region": beach["region"],
            "source": beach.get("source", "local"),
            "distance_km": beach["distance_km"],
            "wave_height": 1.2,
            "wave_direction": 90,
            "wave_direction_visual": "E",
            "wave_period": 10,
            "preferred_swell_label": beach.get("preferred_swell_label", "Any"),
            "wind_speed": 8,
            "wind_direction": 270,
            "wind_direction_visual": "W",
            "temperature_c": 24,
            "precipitation": 0,
            "weather_code": 0,
            "weather_label": "Clear sky",
            "best_wind_label": beach["best_wind_label"],
            "notes": beach["notes"],
            "wave_score": 5,
            "swell_score": 2,
            "wind_score": 6,
            "score": 13,
            "has_marine_signal": True,
            "condition_label": "Excellent",
            "condition_color": "green",
        }

        origin = {"name": "Porto Alegre", "lat": -30.0346, "lon": -51.2177, "source": "manual"}
        _, results = surf_app.build_beach_rankings(origin, 20, 5, "advanced")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "Praia de Ipanema")
        places_mock.assert_called_once_with(-30.0346, -51.2177, 20)

    @patch.object(surf_app.location_service, "find_nearby_beaches")
    def test_find_candidate_beaches_raises_when_google_places_fails(self, places_mock):
        places_mock.side_effect = surf_app.LocationServiceError("Google Places unavailable")
        origin = {"name": "Florianopolis", "lat": -27.5954, "lon": -48.5480, "source": "manual"}

        with self.assertRaises(surf_app.LocationServiceError):
            surf_app.find_candidate_beaches(origin, 20)

    @patch.object(surf_app.location_service, "geocode_address")
    @patch.object(surf_app.location_service, "find_nearby_beaches")
    def test_home_shows_google_places_error_when_search_fails(self, places_mock, geocode_mock):
        geocode_mock.return_value = {
            "formatted_address": "Florianopolis, State of Santa Catarina, Brazil",
            "lat": -27.5954,
            "lon": -48.5480,
            "place_id": "place-123",
        }
        places_mock.side_effect = surf_app.LocationServiceError("Places API not enabled")

        response = self.client.post(
            "/",
            data={
                "location_query": "Florianopolis",
                "max_distance_km": "50",
                "result_limit": "5",
                "skill_level": "beginner",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Places API not enabled", response.data)

    @patch.object(surf_app.location_service, "find_nearby_beaches")
    def test_find_candidate_beaches_returns_google_places_results(self, places_mock):
        places_mock.return_value = [
            {
                "name": "Tramandai",
                "region": "Tramandai",
                "lat": -30.0017,
                "lon": -50.1345,
                "best_wind_label": "Any",
                "best_wind_degrees": [0, 45, 90, 135, 180, 225, 270, 315],
                "preferred_swell_label": "E / SE",
                "preferred_swell_degrees": [90, 135],
                "notes": "Dynamic spot",
                "source": "google_places",
            }
        ]
        origin = {"name": "Porto Alegre", "lat": -30.0346, "lon": -51.2177, "source": "manual"}

        nearby = surf_app.find_candidate_beaches(origin, 160)

        self.assertTrue(any(beach["name"] == "Tramandai" for beach in nearby))
        places_mock.assert_called_once_with(-30.0346, -51.2177, 160)

    @patch.object(surf_app.location_service, "find_nearby_beaches")
    def test_find_candidate_beaches_deduplicates_equivalent_google_places_names(self, places_mock):
        places_mock.return_value = [
            {
                "name": "Praia da Silveira",
                "region": "Garopaba",
                "lat": -28.0240,
                "lon": -48.6210,
                "best_wind_label": "Any",
                "best_wind_degrees": [0, 45, 90, 135, 180, 225, 270, 315],
                "preferred_swell_label": "SE / S",
                "preferred_swell_degrees": [135, 180],
                "notes": "Dynamic spot",
                "source": "google_places",
            },
            {
                "name": "Silveira",
                "region": "Garopaba",
                "lat": -28.0244,
                "lon": -48.6212,
                "best_wind_label": "Any",
                "best_wind_degrees": [0, 45, 90, 135, 180, 225, 270, 315],
                "preferred_swell_label": "SE / S",
                "preferred_swell_degrees": [135, 180],
                "notes": "Dynamic spot duplicate",
                "source": "google_places",
            },
        ]
        origin = {"name": "Garopaba", "lat": -28.0226, "lon": -48.6138, "source": "manual"}

        nearby = surf_app.find_candidate_beaches(origin, 50)

        self.assertEqual(len(nearby), 1)
        self.assertEqual(nearby[0]["name"], "Praia da Silveira")

    @patch.object(surf_app, "evaluate_beach")
    @patch.object(surf_app.location_service, "find_nearby_beaches")
    def test_build_rankings_filters_dynamic_beach_without_marine_signal(self, places_mock, evaluate_mock):
        places_mock.return_value = [
            {
                "name": "Praia sem mar aberto",
                "region": "Nearby area",
                "lat": -30.1000,
                "lon": -51.2000,
                "best_wind_label": "Any",
                "best_wind_degrees": [0, 45, 90, 135, 180, 225, 270, 315],
                "preferred_swell_label": "Any",
                "preferred_swell_degrees": [],
                "notes": "Dynamic spot",
                "source": "google_places",
            }
        ]
        evaluate_mock.return_value = {
            "name": "Praia sem mar aberto",
            "region": "Nearby area",
            "source": "google_places",
            "distance_km": 8.0,
            "wave_height": None,
            "wave_direction": None,
            "wave_direction_visual": "N/A",
            "wave_period": None,
            "preferred_swell_label": "Any",
            "wind_speed": 10,
            "wind_direction": 90,
            "wind_direction_visual": "E",
            "temperature_c": 22,
            "precipitation": 0,
            "weather_code": 1,
            "weather_label": "Mostly clear",
            "best_wind_label": "Any",
            "notes": "Dynamic spot",
            "wave_score": 0,
            "swell_score": 0,
            "wind_score": 2,
            "score": 2,
            "has_marine_signal": False,
            "condition_label": "Poor",
            "condition_color": "red",
        }

        origin = {"name": "Porto Alegre", "lat": -30.0346, "lon": -51.2177, "source": "manual"}
        _, results = surf_app.build_beach_rankings(origin, 20, 5, "advanced")

        self.assertEqual(results, [])

    @patch.object(surf_app, "build_beach_rankings")
    def test_build_rankings_with_radius_fallback_keeps_requested_radius_when_initial_radius_is_empty(self, rankings_mock):
        origin = {"name": "Porto Alegre", "lat": -30.0346, "lon": -51.2177, "source": "browser"}
        rankings_mock.return_value = (origin, [])

        _, beaches, final_radius, info_message = surf_app.build_rankings_with_radius_fallback(
            origin,
            50,
            5,
            "advanced",
        )

        self.assertEqual(final_radius, 50)
        self.assertEqual(beaches, [])
        self.assertIsNone(info_message)

    @patch.object(surf_app, "evaluate_beach")
    @patch.object(surf_app, "find_candidate_beaches")
    def test_build_rankings_limits_external_evaluation_to_closest_candidates(self, find_candidates_mock, evaluate_mock):
        origin = {"name": "Florianopolis", "lat": -27.5954, "lon": -48.5480, "source": "manual"}
        find_candidates_mock.return_value = [
            {
                "name": f"Beach {index}",
                "region": "Florianopolis",
                "lat": -27.5,
                "lon": -48.4,
                "distance_km": float(index),
                "best_wind_label": "Any",
                "best_wind_degrees": [0, 45, 90, 135, 180, 225, 270, 315],
                "preferred_swell_label": "Any",
                "preferred_swell_degrees": [],
                "notes": "Candidate",
                "source": "google_places",
            }
            for index in range(1, 31)
        ]
        evaluate_mock.side_effect = lambda beach, skill_level: {
            "name": beach["name"],
            "region": beach["region"],
            "source": beach["source"],
            "distance_km": beach["distance_km"],
            "wave_height": 1.0,
            "wave_direction": 90,
            "wave_direction_visual": "E",
            "wave_period": 10,
            "preferred_swell_label": "Any",
            "wind_speed": 10,
            "wind_direction": 270,
            "wind_direction_visual": "W",
            "temperature_c": 23,
            "precipitation": 0,
            "weather_code": 0,
            "weather_label": "Clear sky",
            "best_wind_label": "Any",
            "notes": "Candidate",
            "wave_score": 5,
            "swell_score": 0,
            "wind_score": 4,
            "score": 9,
            "has_marine_signal": True,
            "condition_label": "Excellent",
            "condition_color": "green",
        }

        _, results = surf_app.build_beach_rankings(origin, 80, 5, "advanced")

        self.assertEqual(evaluate_mock.call_count, 15)
        self.assertEqual(len(results), 5)


class BeachDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.original_disk_cache = surf_app.disk_cache
        surf_app.disk_cache = PersistentTTLCache(Path(self.temp_dir.name) / "cache.json")

    def tearDown(self):
        surf_app.disk_cache = self.original_disk_cache
        self.temp_dir.cleanup()

    def test_persistent_cache_persists_values_on_disk(self):
        with TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "cache.json"
            cache = PersistentTTLCache(cache_path)
            cache.set("marine", ["lat", "lon"], {"wave_height": 1.2}, 600)

            reloaded_cache = PersistentTTLCache(cache_path)
            cached_value = reloaded_cache.get("marine", ["lat", "lon"])

            self.assertEqual(cached_value["wave_height"], 1.2)

    def test_layered_cache_get_reads_from_disk_when_memory_is_empty(self):
        with TemporaryDirectory() as temp_dir:
            original_disk_cache = surf_app.disk_cache
            surf_app.disk_cache = PersistentTTLCache(Path(temp_dir) / "cache.json")
            try:
                key = (1.2345, 2.3456)
                surf_app.layered_cache_set("marine", surf_app.marine_cache, key, {"wave_height": 0.9})
                surf_app.marine_cache.clear()

                cached_value = surf_app.layered_cache_get("marine", surf_app.marine_cache, key)

                self.assertEqual(cached_value["wave_height"], 0.9)
            finally:
                surf_app.disk_cache = original_disk_cache

    def test_has_surf_marine_signal_requires_meaningful_wave_reading(self):
        self.assertFalse(surf_app.has_surf_marine_signal({"wave_height": None, "wave_period": None}))
        self.assertFalse(surf_app.has_surf_marine_signal({"wave_height": 0.1, "wave_period": 2}))
        self.assertTrue(surf_app.has_surf_marine_signal({"wave_height": 0.5, "wave_period": 3}))
        self.assertTrue(surf_app.has_surf_marine_signal({"wave_height": 0.2, "wave_period": 6}))

    def test_swell_quality_score_rewards_matching_direction(self):
        self.assertEqual(surf_app.swell_quality_score(135, [135, 180]), 3)
        self.assertEqual(surf_app.swell_quality_score(110, [135, 180]), 2)
        self.assertEqual(surf_app.swell_quality_score(70, [135, 180]), 1)
        self.assertEqual(surf_app.swell_quality_score(270, [135, 180]), 0)

    @patch.object(surf_app, "get_google_maps_api_key", return_value="test-key")
    def test_build_beach_map_urls_use_place_id_when_available(self, api_key_mock):
        beach = {
            "name": "Praia da Silveira",
            "region": "Garopaba",
            "lat": -28.024,
            "lon": -48.621,
            "place_id": "place-123",
        }

        embed_url = surf_app.build_beach_map_embed_url(beach)
        maps_url = surf_app.build_beach_google_maps_url(beach)

        self.assertIn("maps/embed/v1/place", embed_url)
        self.assertIn("place_id%3Aplace-123", embed_url)
        self.assertIn("query_place_id=place-123", maps_url)
        api_key_mock.assert_called()

    def test_build_beach_map_urls_fall_back_to_coordinates_without_place_id(self):
        beach = {
            "name": "Joaquina",
            "region": "Florianopolis",
            "lat": -27.6293,
            "lon": -48.4490,
        }

        embed_url = surf_app.build_beach_map_embed_url(beach)
        maps_url = surf_app.build_beach_google_maps_url(beach)

        self.assertIn("loc:-27.6293,-48.449", embed_url)
        self.assertIn("query=-27.6293,-48.449", maps_url)

    @patch.object(surf_app.requests, "get")
    def test_safe_get_retries_timeout_before_succeeding(self, requests_get_mock):
        response = unittest.mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"ok": True}
        requests_get_mock.side_effect = [
            requests.Timeout("slow response"),
            response,
        ]

        result = surf_app.safe_get("https://example.com", {"q": "test"}, timeout=1, retries=2)

        self.assertIs(result, response)
        self.assertEqual(requests_get_mock.call_count, 2)

    @patch.object(surf_app, "get_forecast_conditions")
    @patch.object(surf_app, "get_marine_conditions")
    def test_evaluate_beach_skips_forecast_for_google_spot_when_marine_fails(self, marine_mock, forecast_mock):
        marine_mock.side_effect = requests.Timeout("marine timeout")
        forecast_mock.return_value = {
            "wind_speed": 11,
            "wind_direction": 90,
            "temperature_c": 23,
            "precipitation": 0,
            "weather_code": 1,
        }

        result = surf_app.evaluate_beach(
            {
                "name": "Praia da Silveira",
                "region": "Garopaba",
                "lat": -27.6293,
                "lon": -48.4490,
                "distance_km": 4.5,
                "best_wind_label": "Any",
                "best_wind_degrees": [0, 45, 90, 135, 180, 225, 270, 315],
                "preferred_swell_label": "SE / S",
                "preferred_swell_degrees": [135, 180],
                "notes": "Dynamic spot",
                "source": "google_places",
            },
            "advanced",
        )

        self.assertIsNone(result["wind_speed"])
        self.assertEqual(result["temperature_c"], None)
        forecast_mock.assert_not_called()

    @patch.object(surf_app, "get_forecast_conditions")
    @patch.object(surf_app, "get_marine_conditions")
    def test_evaluate_beach_adds_swell_weight_when_spot_metadata_matches(self, marine_mock, forecast_mock):
        marine_mock.return_value = {
            "wave_height": 1.3,
            "wave_direction": 135,
            "wave_period": 10,
        }
        forecast_mock.return_value = {
            "wind_speed": 8,
            "wind_direction": 270,
            "temperature_c": 23,
            "precipitation": 0,
            "weather_code": 1,
        }

        result = surf_app.evaluate_beach(
            {
                "name": "Praia da Silveira",
                "region": "Garopaba",
                "lat": -28.024,
                "lon": -48.621,
                "distance_km": 2.0,
                "best_wind_label": "Any",
                "best_wind_degrees": [270, 315],
                "preferred_swell_label": "SE / S",
                "preferred_swell_degrees": [135, 180],
                "notes": "Dynamic spot",
                "source": "google_places",
            },
            "advanced",
        )

        self.assertEqual(result["swell_score"], 3)
        self.assertEqual(result["preferred_swell_label"], "SE / S")
        self.assertEqual(result["score"], result["wave_score"] + result["swell_score"] + result["wind_score"])


if __name__ == "__main__":
    unittest.main()
