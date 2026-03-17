from flask import Flask, jsonify, render_template, request
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from math import atan2, cos, radians, sin, sqrt
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional local convenience dependency
    def load_dotenv(*args, **kwargs):
        return False

from beach_source import BeachDiscoveryError, discover_beaches
from beaches_rs import BEACHES_RS
from beaches_sc import BEACHES, MUNICIPALITIES
from env_loader import load_local_env
from mcp_server.location_service import GoogleLocationService, LocationServiceError
from persistent_cache import PersistentTTLCache

BASE_DIR = Path(__file__).resolve().parent
if not load_dotenv(BASE_DIR / ".env"):
    load_local_env(BASE_DIR / ".env")

app = Flask(__name__)

MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

CACHE_TTL_SECONDS = 600
SEARCH_CACHE_TTL = 600
MIN_BEACHES_TO_EVALUATE = 12
MAX_BEACHES_TO_EVALUATE = 18
DEFAULT_RADIUS_KM = 160
RADIUS_EXPANSION_STEPS = (160, 220)
LOCAL_DISCOVERY_SUFFICIENT_RESULTS = 6

marine_cache = {}
forecast_cache = {}
search_cache = {}
beach_discovery_cache = {}
disk_cache = PersistentTTLCache(BASE_DIR / ".cache" / "surfspot_cache.json")

location_service = GoogleLocationService.from_env()
ALL_FALLBACK_BEACHES = [*BEACHES, *BEACHES_RS]
BRAZIL_LABEL = "Brazil"
STATE_BY_REGION = {
    "Florianopolis": "Santa Catarina",
    "Garopaba": "Santa Catarina",
    "Imbituba": "Santa Catarina",
    "Laguna": "Santa Catarina",
    "Balneario Camboriu": "Santa Catarina",
    "Itajai": "Santa Catarina",
    "Governador Celso Ramos": "Santa Catarina",
    "Jaguaruna": "Santa Catarina",
    "Tramandai": "Rio Grande do Sul",
    "Imbe": "Rio Grande do Sul",
    "Xangri-la": "Rio Grande do Sul",
    "Capao da Canoa": "Rio Grande do Sul",
    "Torres": "Rio Grande do Sul",
    "Cidreira": "Rio Grande do Sul",
    "Balneario Pinhal": "Rio Grande do Sul",
}
EXTRA_LOCATION_SUGGESTIONS = [
    {"value": "Porto Alegre", "label": "Porto Alegre, Rio Grande do Sul, Brazil", "meta": "City"},
]


def build_search_suggestions():
    suggestions = {}

    def add_suggestion(value, label, meta):
        key = value.casefold()
        if not value or key in suggestions:
            return

        suggestions[key] = {
            "value": value,
            "label": label,
            "meta": meta,
        }

    for item in EXTRA_LOCATION_SUGGESTIONS:
        add_suggestion(item["value"], item["label"], item["meta"])

    for municipality in MUNICIPALITIES:
        add_suggestion(
            municipality,
            f"{municipality}, Santa Catarina, {BRAZIL_LABEL}",
            "City",
        )

    for beach in ALL_FALLBACK_BEACHES:
        region = beach["region"]
        state = STATE_BY_REGION.get(region, "Brazil")
        add_suggestion(
            beach["name"],
            f"{beach['name']}, {region}, {state}, {BRAZIL_LABEL}",
            "Beach",
        )
        add_suggestion(
            region,
            f"{region}, {state}, {BRAZIL_LABEL}",
            "Region",
        )

    return sorted(suggestions.values(), key=lambda item: item["label"])


SEARCH_SUGGESTIONS = build_search_suggestions()


def safe_get(url, params, timeout=25, retries=2):
    last_error = None

    for _ in range(retries):
        try:
            response = requests.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_error = exc

    raise last_error


def get_cache_key(lat, lon):
    return (round(lat, 4), round(lon, 4))


def cache_get(cache_dict, key):
    entry = cache_dict.get(key)
    if not entry:
        return None

    expires_at, value = entry
    if time.time() > expires_at:
        del cache_dict[key]
        return None

    return value


def layered_cache_get(cache_name, cache_dict, key):
    memory_value = cache_get(cache_dict, key)
    if memory_value is not None:
        return memory_value

    disk_value = disk_cache.get(cache_name, list(key) if isinstance(key, tuple) else key)
    if disk_value is not None:
        cache_set(cache_dict, key, disk_value)
        return disk_value

    return None


def cache_set(cache_dict, key, value, ttl=CACHE_TTL_SECONDS):
    cache_dict[key] = (time.time() + ttl, value)


def layered_cache_set(cache_name, cache_dict, key, value, ttl=CACHE_TTL_SECONDS):
    cache_set(cache_dict, key, value, ttl)
    disk_cache.set(cache_name, list(key) if isinstance(key, tuple) else key, value, ttl)


def search_cache_get(key):
    return layered_cache_get("search", search_cache, key)


def search_cache_set(key, value):
    layered_cache_set("search", search_cache, key, value, SEARCH_CACHE_TTL)


def beach_discovery_cache_get(key):
    return layered_cache_get("beach_discovery", beach_discovery_cache, key)


def beach_discovery_cache_set(key, value):
    layered_cache_set("beach_discovery", beach_discovery_cache, key, value, SEARCH_CACHE_TTL)


def haversine_km(lat1, lon1, lat2, lon2):
    earth_radius = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)

    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return earth_radius * c


def first_value(hourly_dict, key):
    values = hourly_dict.get(key, [])
    return values[0] if values else None


def has_surf_marine_signal(marine):
    wave_height = marine.get("wave_height")
    wave_period = marine.get("wave_period")

    if wave_height is None and wave_period is None:
        return False

    if wave_height is not None and wave_height >= 0.4:
        return True

    if wave_period is not None and wave_period >= 5:
        return True

    return False


def get_marine_conditions(lat, lon):
    cache_key = get_cache_key(lat, lon)
    cached = layered_cache_get("marine", marine_cache, cache_key)
    if cached is not None:
        return cached

    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "wave_height,wave_direction,wave_period",
        "forecast_days": 1,
        "timezone": "auto",
    }

    response = safe_get(MARINE_URL, params=params, timeout=25, retries=2)
    data = response.json()
    hourly = data.get("hourly", {})

    result = {
        "wave_height": first_value(hourly, "wave_height"),
        "wave_direction": first_value(hourly, "wave_direction"),
        "wave_period": first_value(hourly, "wave_period"),
    }

    layered_cache_set("marine", marine_cache, cache_key, result)
    return result


def get_forecast_conditions(lat, lon):
    cache_key = get_cache_key(lat, lon)
    cached = layered_cache_get("forecast", forecast_cache, cache_key)
    if cached is not None:
        return cached

    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "wind_speed_10m,wind_direction_10m,temperature_2m,precipitation,weather_code",
        "forecast_days": 1,
        "timezone": "auto",
    }

    response = safe_get(FORECAST_URL, params=params, timeout=25, retries=2)
    data = response.json()
    hourly = data.get("hourly", {})

    result = {
        "wind_speed": first_value(hourly, "wind_speed_10m"),
        "wind_direction": first_value(hourly, "wind_direction_10m"),
        "temperature_c": first_value(hourly, "temperature_2m"),
        "precipitation": first_value(hourly, "precipitation"),
        "weather_code": first_value(hourly, "weather_code"),
    }

    layered_cache_set("forecast", forecast_cache, cache_key, result)
    return result


def angle_diff(a, b):
    diff = abs(a - b) % 360
    return min(diff, 360 - diff)


def wind_quality_score(wind_speed, wind_direction, preferred_directions):
    if wind_speed is None or wind_direction is None:
        return 0

    if not preferred_directions:
        preferred_directions = [0, 45, 90, 135, 180, 225, 270, 315]

    nearest_diff = min(angle_diff(wind_direction, direction) for direction in preferred_directions)

    score = 0

    if wind_speed < 10:
        score += 3
    elif wind_speed < 18:
        score += 2
    elif wind_speed < 25:
        score += 1

    if nearest_diff <= 30:
        score += 3
    elif nearest_diff <= 60:
        score += 2
    elif nearest_diff <= 90:
        score += 1

    return score


def wave_quality_score(wave_height, wave_period, skill_level):
    if wave_height is None:
        return 0

    score = 0

    if skill_level == "beginner":
        if 0.4 <= wave_height <= 0.9:
            score += 5
        elif 0.9 < wave_height <= 1.1:
            score += 3
        elif 0.25 <= wave_height < 0.4 or 1.1 < wave_height <= 1.3:
            score += 1
        elif 1.3 < wave_height <= 1.5:
            score -= 2
        elif wave_height > 1.5:
            score -= 5
    else:
        if 1.0 <= wave_height <= 2.0:
            score += 5
        elif 0.8 <= wave_height < 1.0 or 2.0 < wave_height <= 2.4:
            score += 3
        elif 0.6 <= wave_height < 0.8 or 2.4 < wave_height <= 3.0:
            score += 1

    if wave_period is not None:
        if wave_period >= 11:
            score += 2
        elif wave_period >= 8:
            score += 1

    return score


def classify_condition(score):
    if score >= 9:
        return "Excellent"
    if score >= 6:
        return "Good"
    if score >= 3:
        return "Fair"
    return "Poor"


def classify_color(score):
    if score >= 9:
        return "green"
    if score >= 6:
        return "yellow"
    if score >= 3:
        return "orange"
    return "red"


def degrees_to_cardinal_arrow(degrees):
    if degrees is None:
        return "N/A"

    directions = [
        ("N", 0),
        ("NE", 45),
        ("E", 90),
        ("SE", 135),
        ("S", 180),
        ("SW", 225),
        ("W", 270),
        ("NW", 315),
    ]

    normalized = degrees % 360
    closest = min(
        directions,
        key=lambda item: min(abs(normalized - item[1]), 360 - abs(normalized - item[1])),
    )
    return closest[0]


def weather_label(weather_code, precipitation):
    if weather_code is None:
        return "N/A"

    if precipitation is not None and precipitation > 0:
        return "Rain"

    mapping = {
        0: "Clear sky",
        1: "Mostly clear",
        2: "Partly cloudy",
        3: "Cloudy",
        45: "Fog",
        48: "Fog",
        51: "Drizzle",
        53: "Drizzle",
        55: "Drizzle",
        61: "Rain",
        63: "Rain",
        65: "Heavy rain",
        71: "Snow",
        80: "Rain showers",
        81: "Rain showers",
        82: "Heavy showers",
        95: "Thunderstorm",
    }

    return mapping.get(weather_code, "Mixed weather")


def evaluate_beach(beach, skill_level):
    try:
        marine = get_marine_conditions(beach["lat"], beach["lon"])
        has_marine_signal = has_surf_marine_signal(marine)

        if beach.get("source") == "osm" and not has_marine_signal:
            forecast = {
                "wind_speed": None,
                "wind_direction": None,
                "temperature_c": None,
                "precipitation": None,
                "weather_code": None,
            }
        else:
            forecast = get_forecast_conditions(beach["lat"], beach["lon"])
    except Exception as exc:
        print(f"Failed to fetch conditions for {beach['name']}: {exc}")
        marine = {"wave_height": None, "wave_direction": None, "wave_period": None}
        forecast = {
            "wind_speed": None,
            "wind_direction": None,
            "temperature_c": None,
            "precipitation": None,
            "weather_code": None,
        }
        has_marine_signal = False

    wave_score = wave_quality_score(marine["wave_height"], marine["wave_period"], skill_level)
    wind_score = wind_quality_score(
        forecast["wind_speed"],
        forecast["wind_direction"],
        beach.get("best_wind_degrees", [0, 45, 90, 135, 180, 225, 270, 315]),
    )
    total_score = wave_score + wind_score

    return {
        "name": beach["name"],
        "region": beach.get("region", "Santa Catarina"),
        "source": beach.get("source", "local"),
        "lat": beach["lat"],
        "lon": beach["lon"],
        "distance_km": beach["distance_km"],
        "wave_height": marine["wave_height"],
        "wave_direction": marine["wave_direction"],
        "wave_direction_visual": degrees_to_cardinal_arrow(marine["wave_direction"]),
        "wave_period": marine["wave_period"],
        "wind_speed": forecast["wind_speed"],
        "wind_direction": forecast["wind_direction"],
        "wind_direction_visual": degrees_to_cardinal_arrow(forecast["wind_direction"]),
        "temperature_c": forecast["temperature_c"],
        "precipitation": forecast["precipitation"],
        "weather_code": forecast["weather_code"],
        "weather_label": weather_label(forecast["weather_code"], forecast["precipitation"]),
        "best_wind_label": beach.get("best_wind_label", "Any"),
        "notes": beach.get("notes", "Surf spot in Santa Catarina"),
        "wave_score": wave_score,
        "wind_score": wind_score,
        "score": total_score,
        "has_marine_signal": has_marine_signal,
        "condition_label": classify_condition(total_score),
        "condition_color": classify_color(total_score),
    }


def parse_optional_float(value):
    if value in (None, ""):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_coordinate_label(lat, lon):
    return f"Current location ({lat:.4f}, {lon:.4f})"


def resolve_origin(location_query, origin_lat, origin_lon, origin_source, resolved_location_label):
    if origin_lat is not None and origin_lon is not None:
        label = (resolved_location_label or "").strip() or build_coordinate_label(origin_lat, origin_lon)
        source = origin_source or "browser"
        return {
            "name": label,
            "lat": origin_lat,
            "lon": origin_lon,
            "source": source,
        }, None

    query = (location_query or "").strip()
    if not query:
        return None, "Enter a location or use your current location."

    try:
        resolved = location_service.geocode_address(query)
    except LocationServiceError as exc:
        return None, str(exc)

    return {
        "name": resolved["formatted_address"],
        "lat": resolved["lat"],
        "lon": resolved["lon"],
        "source": origin_source or "manual",
    }, None


def find_candidate_beaches(origin, max_distance_km):
    cache_key = (
        round(origin["lat"], 4),
        round(origin["lon"], 4),
        max_distance_km,
    )
    cached = beach_discovery_cache_get(cache_key)
    if cached is not None:
        return cached

    fallback_beaches = []
    for beach in ALL_FALLBACK_BEACHES:
        distance_km = haversine_km(origin["lat"], origin["lon"], beach["lat"], beach["lon"])
        if distance_km <= max_distance_km:
            beach_copy = beach.copy()
            beach_copy["distance_km"] = round(distance_km, 1)
            beach_copy.setdefault("source", "local")
            fallback_beaches.append(beach_copy)

    if len(fallback_beaches) >= LOCAL_DISCOVERY_SUFFICIENT_RESULTS:
        fallback_beaches.sort(key=lambda beach: (beach["distance_km"], beach["name"]))
        beach_discovery_cache_set(cache_key, fallback_beaches)
        return fallback_beaches

    try:
        dynamic_beaches = discover_beaches(origin["lat"], origin["lon"], max_distance_km)
    except BeachDiscoveryError as exc:
        print(f"Beach discovery fallback triggered: {exc}")
        beach_discovery_cache_set(cache_key, fallback_beaches)
        return fallback_beaches

    combined = {}
    for beach in [*dynamic_beaches, *fallback_beaches]:
        distance_km = haversine_km(origin["lat"], origin["lon"], beach["lat"], beach["lon"])
        if distance_km > max_distance_km:
            continue

        beach_copy = beach.copy()
        beach_copy["distance_km"] = round(distance_km, 1)
        beach_copy.setdefault("source", "local")
        beach_key = beach_copy["name"].casefold()
        existing = combined.get(beach_key)

        if existing is None or beach_copy["distance_km"] < existing["distance_km"]:
            combined[beach_key] = beach_copy

    nearby_beaches = sorted(combined.values(), key=lambda beach: (beach["distance_km"], beach["name"]))
    beach_discovery_cache_set(cache_key, nearby_beaches)
    return nearby_beaches


def build_beach_rankings(origin, max_distance_km, result_limit, skill_level):
    cache_key = (
        round(origin["lat"], 4),
        round(origin["lon"], 4),
        max_distance_km,
        result_limit,
        skill_level,
    )
    cached = search_cache_get(cache_key)
    if cached is not None:
        return cached

    nearby_beaches = find_candidate_beaches(origin, max_distance_km)

    if not nearby_beaches:
        final_result = (origin, [])
        search_cache_set(cache_key, final_result)
        return final_result

    evaluation_limit = min(
        max(result_limit * 3, MIN_BEACHES_TO_EVALUATE),
        MAX_BEACHES_TO_EVALUATE,
        len(nearby_beaches),
    )
    beaches_to_evaluate = nearby_beaches[:evaluation_limit]

    results = []
    max_workers = min(8, len(beaches_to_evaluate))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(evaluate_beach, beach, skill_level): beach for beach in beaches_to_evaluate
        }

        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                beach = futures[future]
                print(f"Unexpected error evaluating {beach['name']}: {exc}")

    local_results = [item for item in results if item.get("source", "local") != "osm"]
    osm_results = [
        item for item in results
        if item.get("source") == "osm" and item.get("has_marine_signal", False)
    ]
    results = local_results + osm_results

    results.sort(
        key=lambda item: (
            -item["score"],
            -item["wave_score"],
            -item["wind_score"],
            item["distance_km"],
            item["name"],
        )
    )

    final_result = (origin, results[:result_limit])
    search_cache_set(cache_key, final_result)
    return final_result


def build_rankings_with_radius_fallback(origin, max_distance_km, result_limit, skill_level):
    attempted_radius = max_distance_km
    origin_result, beaches = build_beach_rankings(origin, attempted_radius, result_limit, skill_level)

    if beaches:
        return origin_result, beaches, attempted_radius, None

    for expanded_radius in RADIUS_EXPANSION_STEPS:
        if expanded_radius <= attempted_radius:
            continue

        origin_result, beaches = build_beach_rankings(origin, expanded_radius, result_limit, skill_level)
        if beaches:
            message = (
                f"No surfable beaches were found within {attempted_radius} km. "
                f"Showing the nearest options within {expanded_radius} km instead."
            )
            return origin_result, beaches, expanded_radius, message

    return origin_result, beaches, attempted_radius, None


@app.route("/api/reverse-geocode", methods=["POST"])
def reverse_geocode():
    payload = request.get_json(silent=True) or {}
    lat = parse_optional_float(payload.get("lat"))
    lon = parse_optional_float(payload.get("lon"))

    if lat is None or lon is None:
        return jsonify({"error": "Latitude and longitude are required."}), 400

    try:
        resolved = location_service.reverse_geocode(lat, lon)
    except LocationServiceError as exc:
        return jsonify({"error": str(exc)}), 502

    return jsonify(resolved)


@app.route("/", methods=["GET", "POST"])
def home():
    location_query = ""
    max_distance_km = DEFAULT_RADIUS_KM
    result_limit = 5
    skill_level = "beginner"
    origin_lat = ""
    origin_lon = ""
    origin_source = "manual"
    resolved_location_label = ""

    origin = None
    beaches = []
    error_message = None
    info_message = None
    has_searched = False

    if request.method == "POST":
        has_searched = True
        location_query = request.form.get("location_query", "").strip()
        max_distance_km = int(request.form.get("max_distance_km", DEFAULT_RADIUS_KM))
        result_limit = int(request.form.get("result_limit", 5))
        skill_level = request.form.get("skill_level", "beginner")
        origin_lat = request.form.get("origin_lat", "").strip()
        origin_lon = request.form.get("origin_lon", "").strip()
        origin_source = request.form.get("origin_source", "manual").strip() or "manual"
        resolved_location_label = request.form.get("resolved_location_label", "").strip()

        resolved_origin, error_message = resolve_origin(
            location_query=location_query,
            origin_lat=parse_optional_float(origin_lat),
            origin_lon=parse_optional_float(origin_lon),
            origin_source=origin_source,
            resolved_location_label=resolved_location_label,
        )

        if resolved_origin is not None:
            try:
                origin, beaches, max_distance_km, info_message = build_rankings_with_radius_fallback(
                    origin=resolved_origin,
                    max_distance_km=max_distance_km,
                    result_limit=result_limit,
                    skill_level=skill_level,
                )
                location_query = location_query or origin["name"]
                resolved_location_label = origin["name"]
            except Exception as exc:
                print(f"Application error: {exc}")
                error_message = "We could not load surf conditions right now. Please try again."

    return render_template(
        "index.html",
        location_query=location_query,
        max_distance_km=max_distance_km,
        result_limit=result_limit,
        skill_level=skill_level,
        origin=origin,
        beaches=beaches,
        has_searched=has_searched,
        error_message=error_message,
        info_message=info_message,
        origin_lat=origin_lat,
        origin_lon=origin_lon,
        origin_source=origin_source,
        resolved_location_label=resolved_location_label,
        search_suggestions=SEARCH_SUGGESTIONS,
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
