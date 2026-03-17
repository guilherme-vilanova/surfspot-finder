import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app as surf_app
import beach_source
from beach_source import BeachDiscoveryError
from persistent_cache import PersistentTTLCache


class AppLocationFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.original_disk_cache = surf_app.disk_cache
        surf_app.disk_cache = PersistentTTLCache(Path(self.temp_dir.name) / "cache.json")
        self.client = surf_app.app.test_client()
        surf_app.search_cache.clear()
        surf_app.beach_discovery_cache.clear()
        surf_app.beach_map_cache.clear()
        surf_app.marine_cache.clear()
        surf_app.forecast_cache.clear()

    def tearDown(self):
        surf_app.disk_cache = self.original_disk_cache
        self.temp_dir.cleanup()

    def test_requires_location_when_no_origin_is_provided(self):
        response = self.client.post("/", data={})

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Enter a location or use your current location.", response.data)

    def test_home_renders_local_autocomplete_suggestions(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'id="location-autocomplete"', response.data)
        self.assertIn(b'Laguna, Santa Catarina, Brazil', response.data)
        self.assertIn(b'Tramandai, Rio Grande do Sul, Brazil', response.data)

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

    @patch.object(surf_app, "evaluate_beach")
    @patch.object(surf_app, "discover_beaches")
    def test_build_rankings_uses_dynamic_beaches_within_radius(self, discover_mock, evaluate_mock):
        discover_mock.return_value = [
            {
                "name": "Praia de Ipanema",
                "region": "Porto Alegre",
                "lat": -30.1568,
                "lon": -51.2188,
                "best_wind_label": "Any",
                "best_wind_degrees": [0, 45, 90, 135, 180, 225, 270, 315],
                "notes": "Beach discovered dynamically from OpenStreetMap near your selected location.",
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
            "wind_score": 6,
            "score": 11,
            "has_marine_signal": True,
            "condition_label": "Excellent",
            "condition_color": "green",
        }

        origin = {"name": "Porto Alegre", "lat": -30.0346, "lon": -51.2177, "source": "manual"}
        _, results = surf_app.build_beach_rankings(origin, 20, 5, "advanced")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "Praia de Ipanema")
        discover_mock.assert_called_once_with(-30.0346, -51.2177, 20)

    @patch.object(surf_app, "discover_beaches")
    def test_build_rankings_falls_back_to_local_dataset_if_discovery_fails(self, discover_mock):
        discover_mock.side_effect = BeachDiscoveryError("Overpass unavailable")
        origin = {"name": "Florianopolis", "lat": -27.5954, "lon": -48.5480, "source": "manual"}

        nearby = surf_app.find_candidate_beaches(origin, 20)

        self.assertTrue(any(beach["name"] == "Joaquina" for beach in nearby))

    @patch.object(surf_app, "discover_beaches")
    def test_find_candidate_beaches_for_porto_alegre_with_50km_has_no_local_rs_fallback(self, discover_mock):
        discover_mock.return_value = []
        origin = {"name": "Porto Alegre", "lat": -30.0346, "lon": -51.2177, "source": "manual"}

        nearby = surf_app.find_candidate_beaches(origin, 50)

        self.assertEqual(nearby, [])
        discover_mock.assert_called_once()

    @patch.object(surf_app, "discover_beaches")
    def test_find_candidate_beaches_skips_dynamic_lookup_when_local_fallback_is_sufficient(self, discover_mock):
        origin = {"name": "Florianopolis", "lat": -27.5954, "lon": -48.5480, "source": "manual"}

        nearby = surf_app.find_candidate_beaches(origin, 80)

        self.assertGreaterEqual(len(nearby), surf_app.LOCAL_DISCOVERY_SUFFICIENT_RESULTS)
        discover_mock.assert_not_called()

    @patch.object(surf_app, "evaluate_beach")
    @patch.object(surf_app, "discover_beaches")
    def test_build_rankings_filters_dynamic_beach_without_marine_signal(self, discover_mock, evaluate_mock):
        discover_mock.return_value = [
            {
                "name": "Praia sem mar aberto",
                "region": "Nearby area",
                "lat": -30.1000,
                "lon": -51.2000,
                "best_wind_label": "Any",
                "best_wind_degrees": [0, 45, 90, 135, 180, 225, 270, 315],
                "notes": "Dynamic spot",
                "source": "osm",
            }
        ]
        evaluate_mock.return_value = {
            "name": "Praia sem mar aberto",
            "region": "Nearby area",
            "source": "osm",
            "distance_km": 8.0,
            "wave_height": None,
            "wave_direction": None,
            "wave_direction_visual": "N/A",
            "wave_period": None,
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

    @patch.object(surf_app.location_service, "find_place")
    def test_resolve_beach_map_target_uses_google_places_for_winner(self, find_place_mock):
        find_place_mock.return_value = {
            "formatted_address": "Joaquina, Florianopolis, State of Santa Catarina, Brazil",
            "lat": -27.6293,
            "lon": -48.4490,
            "place_id": "place-joaquina",
        }
        beach = {
            "name": "Joaquina",
            "region": "Florianopolis",
            "lat": -27.6200,
            "lon": -48.4400,
        }

        resolved = surf_app.resolve_beach_map_target(beach)

        self.assertEqual(resolved["map_lat"], -27.6293)
        self.assertEqual(resolved["map_lon"], -48.4490)
        self.assertEqual(resolved["map_place_id"], "place-joaquina")
        find_place_mock.assert_called_once_with(
            "Joaquina, Florianopolis, Santa Catarina, Brazil",
            lat=-27.6200,
            lon=-48.4400,
        )

    @patch.object(surf_app.location_service, "find_place")
    def test_resolve_beach_map_target_uses_cached_google_result(self, find_place_mock):
        find_place_mock.return_value = {
            "formatted_address": "Joaquina, Florianopolis, State of Santa Catarina, Brazil",
            "lat": -27.6293,
            "lon": -48.4490,
            "place_id": "place-joaquina",
        }
        beach = {
            "name": "Joaquina",
            "region": "Florianopolis",
            "lat": -27.6200,
            "lon": -48.4400,
        }

        first = surf_app.resolve_beach_map_target(beach)
        second = surf_app.resolve_beach_map_target(beach)

        self.assertEqual(first["map_lat"], second["map_lat"])
        self.assertEqual(find_place_mock.call_count, 1)

    @patch.object(surf_app, "get_google_maps_api_key", return_value="test-key")
    def test_build_beach_map_urls_use_place_id_when_available(self, api_key_mock):
        beach = {
            "name": "Joaquina",
            "region": "Florianopolis",
            "lat": -27.6293,
            "lon": -48.4490,
            "map_lat": -27.6293,
            "map_lon": -48.4490,
            "map_place_id": "place-joaquina",
        }

        embed_url = surf_app.build_beach_map_embed_url(beach)
        maps_url = surf_app.build_beach_google_maps_url(beach)

        self.assertIn("maps/embed/v1/place", embed_url)
        self.assertIn("place_id%3Aplace-joaquina", embed_url)
        self.assertIn("query_place_id=place-joaquina", maps_url)
        api_key_mock.assert_called_once()

    @patch.object(surf_app, "evaluate_beach")
    def test_build_rankings_keeps_local_beach_even_without_marine_signal(self, evaluate_mock):
        evaluate_mock.return_value = {
            "name": "Joaquina",
            "region": "Florianopolis",
            "source": "local",
            "distance_km": 4.5,
            "wave_height": None,
            "wave_direction": None,
            "wave_direction_visual": "N/A",
            "wave_period": None,
            "wind_speed": 10,
            "wind_direction": 90,
            "wind_direction_visual": "E",
            "temperature_c": 22,
            "precipitation": 0,
            "weather_code": 1,
            "weather_label": "Mostly clear",
            "best_wind_label": "W / NW",
            "notes": "Fallback local spot",
            "wave_score": 0,
            "wind_score": 2,
            "score": 2,
            "has_marine_signal": False,
            "condition_label": "Poor",
            "condition_color": "red",
        }

        origin = {"name": "Florianopolis", "lat": -27.5954, "lon": -48.5480, "source": "manual"}
        surf_app.beach_discovery_cache_set((round(origin["lat"], 4), round(origin["lon"], 4), 20), [
            {
                "name": "Joaquina",
                "region": "Florianopolis",
                "lat": -27.6293,
                "lon": -48.4490,
                "distance_km": 4.5,
                "best_wind_label": "W / NW",
                "best_wind_degrees": [270, 315],
                "notes": "Fallback local spot",
                "source": "local",
            }
        ])

        _, results = surf_app.build_beach_rankings(origin, 20, 5, "advanced")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "Joaquina")

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
                "notes": "Candidate",
                "source": "osm",
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

    @patch.object(beach_source, "_safe_post")
    def test_discover_beaches_filters_inland_beaches_without_surf_signal(self, safe_post_mock):
        payload = {
            "elements": [
                {
                    "lat": -30.1200,
                    "lon": -51.2600,
                    "tags": {
                        "name": "Praia do Guaiba",
                        "natural": "beach",
                        "description": "Urban beach on the riverfront of Porto Alegre",
                    },
                },
                {
                    "lat": -29.9800,
                    "lon": -50.1200,
                    "tags": {
                        "name": "Praia de Atlântida",
                        "natural": "beach",
                        "description": "Atlantic Ocean surf beach with open coast exposure",
                    },
                },
            ]
        }

        response = unittest.mock.Mock()
        response.json.return_value = payload
        safe_post_mock.return_value = response

        beaches = beach_source.discover_beaches(-30.0346, -51.2177, 50)

        self.assertEqual([beach["name"] for beach in beaches], ["Praia de Atlântida"])


if __name__ == "__main__":
    unittest.main()
