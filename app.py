from flask import Flask, render_template, request
import requests
import time
import os
from math import radians, sin, cos, sqrt, atan2
from concurrent.futures import ThreadPoolExecutor, as_completed
from beaches_sc import BEACHES, MUNICIPALITIES

app = Flask(__name__)

MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

CACHE_TTL_SECONDS = 600  # 10 minutes
marine_cache = {}
forecast_cache = {}


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


def cache_set(cache_dict, key, value, ttl=CACHE_TTL_SECONDS):
    cache_dict[key] = (time.time() + ttl, value)


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)

    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return r * c


def first_value(hourly_dict, key):
    values = hourly_dict.get(key, [])
    return values[0] if values else None


def get_marine_conditions(lat: float, lon: float):
    cache_key = get_cache_key(lat, lon)
    cached = cache_get(marine_cache, cache_key)
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

    cache_set(marine_cache, cache_key, result)
    return result


def get_forecast_conditions(lat: float, lon: float):
    cache_key = get_cache_key(lat, lon)
    cached = cache_get(forecast_cache, cache_key)
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

    cache_set(forecast_cache, cache_key, result)
    return result


def angle_diff(a, b):
    diff = abs(a - b) % 360
    return min(diff, 360 - diff)


def wind_quality_score(wind_speed, wind_direction, preferred_directions):
    if wind_speed is None or wind_direction is None:
        return 0

    if not preferred_directions:
        preferred_directions = [0, 45, 90, 135, 180, 225, 270, 315]

    nearest_diff = min(angle_diff(wind_direction, d) for d in preferred_directions)

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
        # More conservative beginner thresholds
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

    else:  # advanced
        if 1.0 <= wave_height <= 2.0:
            score += 5
        elif 0.8 <= wave_height < 1.0 or 2.0 < wave_height <= 2.4:
            score += 3
        elif 0.6 <= wave_height < 0.8 or 2.4 < wave_height <= 3.0:
            score += 1
        elif wave_height > 3.0:
            score += 0

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
        ("↑ N", 0),
        ("↗ NE", 45),
        ("→ E", 90),
        ("↘ SE", 135),
        ("↓ S", 180),
        ("↙ SW", 225),
        ("← W", 270),
        ("↖ NW", 315),
    ]

    normalized = degrees % 360
    closest = min(
        directions,
        key=lambda item: min(abs(normalized - item[1]), 360 - abs(normalized - item[1]))
    )
    return closest[0]


def weather_label(weather_code, precipitation):
    if weather_code is None:
        return "N/A"

    if precipitation is not None and precipitation > 0:
        return "🌧️ Rain"

    mapping = {
        0: "☀️ Clear sky",
        1: "🌤️ Mostly clear",
        2: "⛅ Partly cloudy",
        3: "☁️ Cloudy",
        45: "🌫️ Fog",
        48: "🌫️ Fog",
        51: "🌦️ Drizzle",
        53: "🌦️ Drizzle",
        55: "🌦️ Drizzle",
        61: "🌧️ Rain",
        63: "🌧️ Rain",
        65: "🌧️ Heavy rain",
        71: "❄️ Snow",
        80: "🌧️ Rain showers",
        81: "🌧️ Rain showers",
        82: "🌧️ Heavy showers",
        95: "⛈️ Thunderstorm",
    }

    return mapping.get(weather_code, "🌤️ Mixed weather")


def evaluate_beach(beach, skill_level):
    try:
        marine = get_marine_conditions(beach["lat"], beach["lon"])
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

    wave_score = wave_quality_score(
        marine["wave_height"],
        marine["wave_period"],
        skill_level
    )

    wind_score = wind_quality_score(
        forecast["wind_speed"],
        forecast["wind_direction"],
        beach.get("best_wind_degrees", [0, 45, 90, 135, 180, 225, 270, 315]),
    )

    total_score = wave_score + wind_score

    return {
        "name": beach["name"],
        "region": beach.get("region", "Santa Catarina"),
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
        "condition_label": classify_condition(total_score),
        "condition_color": classify_color(total_score),
    }


def build_beach_rankings(municipality: str, max_distance_km: int, result_limit: int, skill_level: str):
    origin = MUNICIPALITIES.get(municipality)
    if not origin:
        return None, []

    origin_data = {
        "name": municipality,
        "lat": origin["lat"],
        "lon": origin["lon"],
    }

    nearby_beaches = []
    for beach in BEACHES:
        distance_km = haversine_km(origin["lat"], origin["lon"], beach["lat"], beach["lon"])
        if distance_km <= max_distance_km:
            beach_copy = beach.copy()
            beach_copy["distance_km"] = round(distance_km, 1)
            nearby_beaches.append(beach_copy)

    nearby_beaches.sort(key=lambda beach: (beach["distance_km"], beach["name"]))

    if not nearby_beaches:
        return origin_data, []

    results = []
    max_workers = min(4, len(nearby_beaches))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(evaluate_beach, beach, skill_level): beach
            for beach in nearby_beaches
        }

        for future in as_completed(futures):
            try:
                result = future.result()
                results.append(result)
            except Exception as exc:
                beach = futures[future]
                print(f"Unexpected error evaluating {beach['name']}: {exc}")

    results.sort(
        key=lambda item: (
            -item["score"],
            -item["wave_score"],
            -item["wind_score"],
            item["distance_km"],
            item["name"],
        )
    )

    return origin_data, results[:result_limit]


@app.route("/", methods=["GET", "POST"])
def home():
    municipality = ""
    max_distance_km = 80
    result_limit = 5
    skill_level = "beginner"

    origin = None
    beaches = []
    has_searched = False

    if request.method == "POST":
        has_searched = True
        municipality = request.form.get("municipality", "")
        max_distance_km = int(request.form.get("max_distance_km", 80))
        result_limit = int(request.form.get("result_limit", 5))
        skill_level = request.form.get("skill_level", "beginner")

        try:
            origin, beaches = build_beach_rankings(
                municipality=municipality,
                max_distance_km=max_distance_km,
                result_limit=result_limit,
                skill_level=skill_level,
            )
        except Exception as exc:
            print(f"Application error: {exc}")
            origin, beaches = None, []

    return render_template(
        "index.html",
        municipality=municipality,
        municipalities=sorted(MUNICIPALITIES.keys()),
        max_distance_km=max_distance_km,
        result_limit=result_limit,
        skill_level=skill_level,
        origin=origin,
        beaches=beaches,
        has_searched=has_searched,
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)