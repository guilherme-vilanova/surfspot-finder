import os

import requests


OVERPASS_URL = os.environ.get("OVERPASS_API_URL", "https://overpass-api.de/api/interpreter")
OVERPASS_TIMEOUT_SECONDS = 30
SURF_POSITIVE_KEYWORDS = (
    "surf",
    "break",
    "ocean",
    "sea",
    "atlantic",
    "coast",
    "coastal",
    "mar",
    "costa",
    "oceano",
)
INLAND_NEGATIVE_KEYWORDS = (
    "lake",
    "lagoon",
    "laguna",
    "lagoa",
    "river",
    "rio",
    "arroio",
    "reservoir",
    "represa",
    "canal",
    "stream",
    "creek",
)


class BeachDiscoveryError(Exception):
    pass


def _safe_post(url, data, timeout=OVERPASS_TIMEOUT_SECONDS, retries=2):
    last_error = None

    for _ in range(retries):
        try:
            response = requests.post(url, data=data, timeout=timeout)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_error = exc

    raise BeachDiscoveryError(f"Beach discovery failed: {last_error}")


def _build_overpass_query(lat, lon, radius_km):
    radius_m = max(int(radius_km * 1000), 1000)
    return f"""
[out:json][timeout:25];
(
  node(around:{radius_m},{lat},{lon})["natural"="beach"];
  way(around:{radius_m},{lat},{lon})["natural"="beach"];
  relation(around:{radius_m},{lat},{lon})["natural"="beach"];
  node(around:{radius_m},{lat},{lon})["place"="beach"];
  way(around:{radius_m},{lat},{lon})["place"="beach"];
  relation(around:{radius_m},{lat},{lon})["place"="beach"];
);
out center tags;
""".strip()


def _pick_name(tags):
    return (
        tags.get("name")
        or tags.get("name:pt")
        or tags.get("official_name")
        or tags.get("short_name")
        or ""
    ).strip()


def _pick_region(tags):
    return (
        tags.get("addr:city")
        or tags.get("addr:municipality")
        or tags.get("is_in:city")
        or tags.get("addr:state")
        or tags.get("is_in:state")
        or tags.get("region")
        or "Nearby area"
    ).strip()


def _build_notes(tags):
    description = (tags.get("description") or tags.get("note") or "").strip()
    if description:
        return description

    if tags.get("natural") == "beach":
        return "Beach discovered dynamically from OpenStreetMap near your selected location."

    return "Nearby beach area discovered dynamically from OpenStreetMap."


def _element_coordinates(element):
    if "lat" in element and "lon" in element:
        return element["lat"], element["lon"]

    center = element.get("center") or {}
    return center.get("lat"), center.get("lon")


def _tag_text(tags, name):
    parts = [name]

    for key in (
        "description",
        "note",
        "alt_name",
        "official_name",
        "loc_name",
        "is_in",
        "is_in:city",
        "is_in:state",
    ):
        value = tags.get(key)
        if value:
            parts.append(str(value))

    return " ".join(parts).casefold()


def _contains_keyword(text, keywords):
    return any(keyword in text for keyword in keywords)


def _is_surf_relevant(tags, name):
    text = _tag_text(tags, name)
    positive_score = 0

    if tags.get("sport") == "surf" or tags.get("surf") in {"yes", "designated"}:
        positive_score += 3

    if tags.get("natural") == "beach":
        positive_score += 1

    if tags.get("place") == "beach":
        positive_score += 1

    if _contains_keyword(text, SURF_POSITIVE_KEYWORDS):
        positive_score += 2

    inland_block = _contains_keyword(text, INLAND_NEGATIVE_KEYWORDS)
    if inland_block and positive_score < 3:
        return False

    return positive_score > 0


def discover_beaches(lat, lon, radius_km):
    query = _build_overpass_query(lat, lon, radius_km)
    response = _safe_post(OVERPASS_URL, {"data": query})
    payload = response.json()

    beaches = []
    seen = set()

    for element in payload.get("elements", []):
        tags = element.get("tags") or {}
        name = _pick_name(tags)
        beach_lat, beach_lon = _element_coordinates(element)

        if not name or beach_lat is None or beach_lon is None:
            continue

        if not _is_surf_relevant(tags, name):
            continue

        key = (name.casefold(), round(beach_lat, 4), round(beach_lon, 4))
        if key in seen:
            continue

        seen.add(key)
        beaches.append(
            {
                "name": name,
                "region": _pick_region(tags),
                "lat": beach_lat,
                "lon": beach_lon,
                "best_wind_label": "Any",
                "best_wind_degrees": [0, 45, 90, 135, 180, 225, 270, 315],
                "notes": _build_notes(tags),
                "source": "osm",
            }
        )

    return beaches
