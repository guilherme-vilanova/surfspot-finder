from flask import Flask, jsonify, render_template, request
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from math import atan2, cos, radians, sin, sqrt
from pathlib import Path
from urllib.parse import quote_plus

import requests

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional local convenience dependency
    def load_dotenv(*args, **kwargs):
        return False

from env_loader import load_local_env
from mcp_server.config import get_google_maps_api_key
from mcp_server.location_service import GoogleLocationService, LocationServiceError
from persistent_cache import PersistentTTLCache
from surf_metadata import canonical_beach_name

BASE_DIR = Path(__file__).resolve().parent
if not load_dotenv(BASE_DIR / ".env"):
    load_local_env(BASE_DIR / ".env")

app = Flask(__name__)

MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

CACHE_TTL_SECONDS = 600
SEARCH_CACHE_TTL = 600
HTTP_RETRIES = 3
MARINE_TIMEOUT_SECONDS = 12
FORECAST_TIMEOUT_SECONDS = 10
MIN_RADIUS_KM = 30
MAX_RADIUS_KM = 50
MIN_BEACHES_TO_EVALUATE = 12
MAX_BEACHES_TO_EVALUATE = 18
DEFAULT_RADIUS_KM = 50
RADIUS_EXPANSION_STEPS = ()
SEARCH_CACHE_NAMESPACE = "search_v2"
BEACH_DISCOVERY_CACHE_NAMESPACE = "beach_discovery_v2"

marine_cache = {}
forecast_cache = {}
search_cache = {}
beach_discovery_cache = {}
disk_cache = PersistentTTLCache(BASE_DIR / ".cache" / "surfspot_cache.json")

location_service = GoogleLocationService.from_env()


def safe_get(url, params, timeout=10, retries=HTTP_RETRIES):
    last_error = None

    for _ in range(retries):
        try:
            response = requests.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            return response
        except requests.Timeout as exc:
            last_error = exc
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
    return layered_cache_get(SEARCH_CACHE_NAMESPACE, search_cache, key)


def search_cache_set(key, value):
    layered_cache_set(SEARCH_CACHE_NAMESPACE, search_cache, key, value, SEARCH_CACHE_TTL)


def beach_discovery_cache_get(key):
    return layered_cache_get(BEACH_DISCOVERY_CACHE_NAMESPACE, beach_discovery_cache, key)


def beach_discovery_cache_set(key, value):
    layered_cache_set(BEACH_DISCOVERY_CACHE_NAMESPACE, beach_discovery_cache, key, value, SEARCH_CACHE_TTL)


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


def is_dynamic_beach_source(source):
    return source == "google_places"


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

    response = safe_get(MARINE_URL, params=params, timeout=MARINE_TIMEOUT_SECONDS, retries=HTTP_RETRIES)
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

    response = safe_get(
        FORECAST_URL,
        params=params,
        timeout=FORECAST_TIMEOUT_SECONDS,
        retries=HTTP_RETRIES,
    )
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


def swell_quality_score(wave_direction, preferred_directions):
    if wave_direction is None or not preferred_directions:
        return 0

    nearest_diff = min(angle_diff(wave_direction, direction) for direction in preferred_directions)

    if nearest_diff <= 20:
        return 3
    if nearest_diff <= 45:
        return 2
    if nearest_diff <= 70:
        return 1

    return 0


def classify_condition(score):
    if score >= 11:
        return "Excellent"
    if score >= 7:
        return "Good"
    if score >= 4:
        return "Fair"
    return "Poor"


def classify_color(score):
    if score >= 11:
        return "green"
    if score >= 7:
        return "yellow"
    if score >= 4:
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
    marine = {"wave_height": None, "wave_direction": None, "wave_period": None}
    forecast = {
        "wind_speed": None,
        "wind_direction": None,
        "temperature_c": None,
        "precipitation": None,
        "weather_code": None,
    }
    has_marine_signal = False

    try:
        marine = get_marine_conditions(beach["lat"], beach["lon"])
        has_marine_signal = has_surf_marine_signal(marine)
    except Exception as exc:
        print(f"Failed to fetch marine conditions for {beach['name']}: {exc}")

    should_fetch_forecast = not (is_dynamic_beach_source(beach.get("source")) and not has_marine_signal)
    if should_fetch_forecast:
        try:
            forecast = get_forecast_conditions(beach["lat"], beach["lon"])
        except Exception as exc:
            print(f"Failed to fetch forecast conditions for {beach['name']}: {exc}")

    wave_score = wave_quality_score(marine["wave_height"], marine["wave_period"], skill_level)
    swell_score = swell_quality_score(
        marine["wave_direction"],
        beach.get("preferred_swell_degrees"),
    )
    wind_score = wind_quality_score(
        forecast["wind_speed"],
        forecast["wind_direction"],
        beach.get("best_wind_degrees", [0, 45, 90, 135, 180, 225, 270, 315]),
    )
    total_score = wave_score + swell_score + wind_score

    return {
        "name": beach["name"],
        "region": beach.get("region", "Santa Catarina"),
        "source": beach.get("source", "local"),
        "place_id": beach.get("place_id"),
        "lat": beach["lat"],
        "lon": beach["lon"],
        "distance_km": beach["distance_km"],
        "wave_height": marine["wave_height"],
        "wave_direction": marine["wave_direction"],
        "wave_direction_visual": degrees_to_cardinal_arrow(marine["wave_direction"]),
        "wave_period": marine["wave_period"],
        "preferred_swell_label": beach.get("preferred_swell_label", "Any"),
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
        "swell_score": swell_score,
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


def clamp_radius_km(value):
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return DEFAULT_RADIUS_KM

    return max(MIN_RADIUS_KM, min(numeric, MAX_RADIUS_KM))


def build_coordinate_label(lat, lon):
    return f"Current location ({lat:.4f}, {lon:.4f})"


def build_beach_map_embed_url(beach):
    api_key = get_google_maps_api_key()
    place_id = beach.get("place_id")
    if api_key and place_id:
        return (
            "https://www.google.com/maps/embed/v1/place"
            f"?key={quote_plus(api_key)}&q={quote_plus(f'place_id:{place_id}')}&zoom=12"
        )

    return f"https://maps.google.com/maps?q=loc:{beach['lat']},{beach['lon']}&z=12&output=embed"


def build_beach_google_maps_url(beach):
    place_id = beach.get("place_id")
    if place_id:
        query = f"{beach['name']}, {beach.get('region', 'Brazil')}"
        return (
            "https://www.google.com/maps/search/?api=1"
            f"&query={quote_plus(query)}&query_place_id={quote_plus(place_id)}"
        )

    return f"https://www.google.com/maps/search/?api=1&query={beach['lat']},{beach['lon']}"


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

    dynamic_beaches = location_service.find_nearby_beaches(origin["lat"], origin["lon"], max_distance_km)

    if not dynamic_beaches:
        beach_discovery_cache_set(cache_key, [])
        return []

    combined = {}
    for beach in dynamic_beaches:
        distance_km = haversine_km(origin["lat"], origin["lon"], beach["lat"], beach["lon"])
        if distance_km > max_distance_km:
            continue

        beach_copy = beach.copy()
        beach_copy["distance_km"] = round(distance_km, 1)
        beach_copy.setdefault("source", "local")
        beach_key = canonical_beach_name(beach_copy["name"])
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

    local_results = [item for item in results if not is_dynamic_beach_source(item.get("source", "local"))]
    dynamic_results = [
        item for item in results
        if is_dynamic_beach_source(item.get("source")) and item.get("has_marine_signal", False)
    ]
    results = local_results + dynamic_results

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


@app.route("/api/location-autocomplete")
def location_autocomplete():
    query = (request.args.get("q") or "").strip()
    if len(query) < 2:
        return jsonify({"suggestions": []})

    try:
        suggestions = location_service.autocomplete_places(query)
    except LocationServiceError as exc:
        return jsonify({"error": str(exc), "suggestions": []}), 502

    return jsonify({"suggestions": suggestions[:6]})


@app.route("/api/reverse-geocode", methods=["POST"])
def reverse_geocode():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        payload = request.form.to_dict() if request.form else {}
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
    winner_map_embed_url = None
    winner_google_maps_url = None

    if request.method == "POST":
        has_searched = True
        location_query = request.form.get("location_query", "").strip()
        max_distance_km = clamp_radius_km(request.form.get("max_distance_km", DEFAULT_RADIUS_KM))
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
            except LocationServiceError as exc:
                error_message = str(exc)
            except Exception as exc:
                print(f"Application error: {exc}")
                error_message = "We could not load surf conditions right now. Please try again."

    if beaches:
        winner_map_embed_url = build_beach_map_embed_url(beaches[0])
        winner_google_maps_url = build_beach_google_maps_url(beaches[0])

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
        winner_map_embed_url=winner_map_embed_url,
        winner_google_maps_url=winner_google_maps_url,
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
