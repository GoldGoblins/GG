"""Small, safe OSIRIS-style public intelligence collector for GG AI Desktop.

The upstream OSIRIS project is a broad web application.  This module keeps
the native desktop surface deliberately narrower: it reads a fixed allowlist
of public feeds, bounds every response, and never accepts a user supplied URL
or target.  That gives the desktop the useful observation layer without
turning a dashboard into an arbitrary network scanner.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import threading
import time
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET


SCHEMA = "gg.ai-desktop.osiris-snapshot.v1"
SAFE_SCOPE = "PUBLIC_READ_ONLY"
CACHE_TTL_SECONDS = 90.0
MAX_RESPONSE_BYTES = 5_000_000
MAX_ROWS = 160
MAX_NEWS_ROWS = 32
MAX_CAMERA_ROWS = 80
MAX_STREAM_ROWS = 28
MAX_GDELT_ROWS = 40
MAX_SATELLITES = 72
MAX_FIRE_ROWS = 120
MAX_EARTHQUAKES = 80
MAX_HISTORY = 60
HTTP_TIMEOUT_SECONDS = 5.0
USER_AGENT = "gg-ai-desktop/osiris-native/1.0"

USGS_URL = (
    "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/"
    "2.5_day.geojson"
)
OPENSKY_URL = "https://opensky-network.org/api/states/all"
EONET_URL = (
    "https://eonet.gsfc.nasa.gov/api/v3/events?status=open&limit=100"
)
CELESTRAK_URL = (
    "https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=json"
)
NOAA_URL = "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json"
BBC_URL = "https://feeds.bbci.co.uk/news/world/rss.xml"
GDELT_URL = "https://api.gdeltproject.org/api/v1/gkg_geojson?TIMESPAN=180"
OSIRIS_REPOSITORY_URL = "https://github.com/simplifaisoul/osiris"
DEFLOCK_URL = "https://deflock.org/"
ALPR_SAMPLE_PATH = (
    Path(__file__).resolve().parents[1] / "qml/osint-map/data/alpr.geojson"
)

SOURCE_CATALOG = (
    {
        "id": "earthquakes",
        "label": "SEISMIC",
        "provider": "USGS",
        "url": USGS_URL,
    },
    {
        "id": "aircraft",
        "label": "FLIGHTS",
        "provider": "OPENSKY",
        "url": OPENSKY_URL,
    },
    {
        "id": "fires",
        "label": "FIRES",
        "provider": "NASA EONET",
        "url": EONET_URL,
    },
    {
        "id": "satellites",
        "label": "SPACE",
        "provider": "CELESTRAK",
        "url": CELESTRAK_URL,
    },
    {
        "id": "solar",
        "label": "SOLAR",
        "provider": "NOAA SWPC",
        "url": NOAA_URL,
    },
    {
        "id": "news",
        "label": "NEWS",
        "provider": "BBC WORLD",
        "url": BBC_URL,
    },
    {
        "id": "gdelt",
        "label": "GLOBAL NEWS GEO",
        "provider": "GDELT",
        "url": GDELT_URL,
    },
    {
        "id": "cameras",
        "label": "ALPR PINS",
        "provider": "OSM / DEFLOCK SAMPLE",
        "url": DEFLOCK_URL,
    },
    {
        "id": "conflicts",
        "label": "WATCHLIST",
        "provider": "OSIRIS REFERENCE",
        "url": OSIRIS_REPOSITORY_URL,
    },
)

ALLOWED_SOURCE_URLS = frozenset(
    str(source["url"]) for source in SOURCE_CATALOG
)
MAP_API_HOSTS = frozenset(
    {
        "nominatim.openstreetmap.org",
        "router.project-osrm.org",
    }
)
MAX_ROUTE_PLACES = 26

# These are deliberately labelled as reference locations.  They are not a
# claim that the desktop has independently verified a live conflict status.
REFERENCE_ZONES = (
    {"id": "ukraine", "label": "UKRAINE", "lat": 49.0, "lon": 32.0, "severity": 5},
    {"id": "gaza", "label": "GAZA / LEVANT", "lat": 31.4, "lon": 34.4, "severity": 5},
    {"id": "sudan", "label": "SUDAN", "lat": 15.6, "lon": 32.5, "severity": 4},
    {"id": "myanmar", "label": "MYANMAR", "lat": 21.0, "lon": 96.0, "severity": 4},
    {"id": "drc", "label": "EASTERN DRC", "lat": -1.6, "lon": 29.2, "severity": 4},
    {"id": "yemen", "label": "YEMEN / RED SEA", "lat": 15.5, "lon": 48.5, "severity": 4},
    {"id": "syria", "label": "SYRIA", "lat": 35.0, "lon": 38.0, "severity": 3},
    {"id": "sahel", "label": "SAHEL", "lat": 14.0, "lon": 0.0, "severity": 4},
    {"id": "somalia", "label": "SOMALIA", "lat": 5.2, "lon": 46.2, "severity": 3},
    {"id": "taiwan", "label": "TAIWAN STRAIT", "lat": 23.7, "lon": 120.7, "severity": 3},
    {"id": "korean-dmz", "label": "KOREAN DMZ", "lat": 38.0, "lon": 127.0, "severity": 3},
    {"id": "south-caucasus", "label": "SOUTH CAUCASUS", "lat": 40.2, "lon": 45.0, "severity": 2},
    {"id": "lebanon", "label": "LEBANON", "lat": 33.9, "lon": 35.7, "severity": 4},
)

# Longest match first. Used to pin BBC headlines onto the globe.
PLACE_COORDS: tuple[tuple[str, float, float], ...] = tuple(
    sorted(
        (
            ("united states", 39.8, -98.5),
            ("washington", 38.9, -77.0),
            ("new york", 40.7, -74.0),
            ("california", 36.8, -119.4),
            ("ukraine", 49.0, 32.0),
            ("russia", 55.8, 37.6),
            ("moscow", 55.8, 37.6),
            ("gaza", 31.4, 34.4),
            ("israel", 31.5, 34.9),
            ("lebanon", 33.9, 35.7),
            ("syria", 35.0, 38.0),
            ("iran", 32.4, 53.7),
            ("iraq", 33.3, 44.4),
            ("yemen", 15.5, 48.5),
            ("sudan", 15.6, 32.5),
            ("sahel", 14.0, 0.0),
            ("somalia", 5.2, 46.2),
            ("ethiopia", 9.0, 38.7),
            ("kenya", -1.3, 36.8),
            ("nigeria", 9.1, 8.7),
            ("egypt", 26.8, 30.8),
            ("libya", 26.3, 17.2),
            ("algeria", 28.0, 2.0),
            ("morocco", 31.8, -7.1),
            ("south africa", -28.5, 24.7),
            ("congo", -2.9, 23.8),
            ("china", 35.9, 104.2),
            ("taiwan", 23.7, 120.9),
            ("japan", 36.2, 138.3),
            ("korea", 37.5, 127.0),
            ("india", 21.1, 79.0),
            ("pakistan", 30.4, 69.3),
            ("afghanistan", 33.9, 67.7),
            ("myanmar", 21.0, 96.0),
            ("australia", -25.3, 133.8),
            ("indonesia", -2.2, 118.0),
            ("philippines", 12.9, 121.8),
            ("united kingdom", 54.0, -2.0),
            ("britain", 54.0, -2.0),
            ("london", 51.5, -0.1),
            ("france", 46.2, 2.2),
            ("paris", 48.9, 2.3),
            ("germany", 51.2, 10.4),
            ("berlin", 52.5, 13.4),
            ("spain", 40.5, -3.7),
            ("italy", 42.8, 12.6),
            ("poland", 52.1, 19.4),
            ("sweden", 60.1, 18.6),
            ("norway", 60.5, 8.5),
            ("finland", 64.0, 26.0),
            ("turkey", 39.0, 35.2),
            ("greece", 39.1, 21.8),
            ("brazil", -14.2, -51.9),
            ("argentina", -38.4, -63.6),
            ("mexico", 23.6, -102.5),
            ("canada", 56.1, -106.3),
            ("venezuela", 6.4, -66.6),
            ("colombia", 4.6, -74.1),
        ),
        key=lambda item: len(item[0]),
        reverse=True,
    )
)

_lock = threading.RLock()
_last_collect_at = 0.0
_last_generated_at = ""
_collections: dict[str, list[dict[str, Any]]] = {
    "aircraft": [],
    "earthquakes": [],
    "fires": [],
    "satellites": [],
    "news": [],
    "cameras": [],
    "gdelt": [],
}
_solar: dict[str, Any] = {}
_sources: dict[str, dict[str, Any]] = {
    str(source["id"]): {
        **source,
        "status": "IDLE",
        "count": 0,
        "error": "",
        "last_updated": "",
    }
    for source in SOURCE_CATALOG
}
_histories: dict[str, list[int]] = {
    "aircraft": [],
    "earthquakes": [],
    "fires": [],
    "satellites": [],
    "news": [],
    "cameras": [],
    "gdelt": [],
}
_alpr_total = 0


def _cached_alpr_total() -> int:
    global _alpr_total
    if _alpr_total:
        return _alpr_total
    try:
        payload = json.loads(ALPR_SAMPLE_PATH.read_text(encoding="utf-8"))
        _alpr_total = len(payload.get("features") or [])
    except (OSError, TypeError, ValueError):
        _alpr_total = 0
    return _alpr_total


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _bounded_text(value: Any, limit: int = 240) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


def _float(value: Any, fallback: float | None = None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    if number != number or number in (float("inf"), float("-inf")):
        return fallback
    return number


def _int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _iso_from_millis(value: Any) -> str:
    stamp = _float(value)
    if stamp is None:
        return ""
    try:
        return (
            datetime.fromtimestamp(stamp / 1000.0, tz=timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
    except (OverflowError, OSError, ValueError):
        return ""


def _read_public(url: str, timeout: float | None = None) -> bytes:
    """Read one allowlisted public endpoint with strict bounds."""
    if url not in ALLOWED_SOURCE_URLS:
        raise ValueError("source is not allowlisted")
    request = Request(
        url,
        headers={
            "Accept": "application/json, application/xml, text/xml",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urlopen(
            request, timeout=timeout if timeout is not None else HTTP_TIMEOUT_SECONDS
        ) as response:
            status = int(getattr(response, "status", 200) or 200)
            if status >= 400:
                raise OSError(f"HTTP {status}")
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        raise OSError(f"HTTP {exc.code}") from exc
    except URLError as exc:
        raise OSError(str(exc.reason or "network error")) from exc
    if len(body) > MAX_RESPONSE_BYTES:
        raise OSError("response exceeded size limit")
    return body


def _read_json(url: str, timeout: float | None = None) -> Any:
    return json.loads(
        _read_public(url, timeout=timeout).decode("utf-8", errors="replace")
    )


def _read_map_api(url: str, timeout: float = 8.0) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in MAP_API_HOSTS:
        raise ValueError("map api host is not allowlisted")
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200) or 200)
            if status >= 400:
                raise OSError(f"HTTP {status}")
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        raise OSError(f"HTTP {exc.code}") from exc
    except URLError as exc:
        raise OSError(str(exc.reason or "network error")) from exc
    if len(body) > MAX_RESPONSE_BYTES:
        raise OSError("response exceeded size limit")
    return body


def geocode_place(query: str, gps: dict[str, Any] | None = None) -> dict[str, Any]:
    text = _bounded_text(query, 120)
    if gps and (not text or text.lower() == "gps"):
        lat = _float(gps.get("lat"))
        lon = _float(gps.get("lon"))
        if lat is None or lon is None:
            raise OSError("GPS fix missing")
        return {"lat": round(lat, 5), "lon": round(lon, 5), "name": "GPS"}
    if not text:
        raise OSError("empty place")
    url = (
        "https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&q="
        + quote(text)
    )
    hits = json.loads(_read_map_api(url).decode("utf-8", errors="replace"))
    if not isinstance(hits, list) or not hits:
        raise OSError("place not found: " + text)
    hit = hits[0] if isinstance(hits[0], dict) else {}
    lat = _float(hit.get("lat"))
    lon = _float(hit.get("lon"))
    if lat is None or lon is None:
        raise OSError("place not found: " + text)
    return {
        "lat": round(lat, 5),
        "lon": round(lon, 5),
        "name": _bounded_text(hit.get("display_name") or text, 120),
    }


def plan_driving_route(
    places: list[str],
    gps: dict[str, Any] | None = None,
) -> dict[str, Any]:
    names = [_bounded_text(item, 120) for item in places if _bounded_text(item, 120)]
    if len(names) < 2:
        return {"ok": False, "error": "Need at least two places.", "points": []}
    if len(names) > MAX_ROUTE_PLACES:
        names = names[:MAX_ROUTE_PLACES]
    points: list[dict[str, Any]] = []
    try:
        for index, name in enumerate(names):
            points.append(geocode_place(name, gps if index == 0 else None))
        path = ";".join(f"{point['lon']},{point['lat']}" for point in points)
        payload = json.loads(
            _read_map_api(
                "https://router.project-osrm.org/route/v1/driving/"
                + path
                + "?overview=full&geometries=geojson",
                timeout=12.0,
            ).decode("utf-8", errors="replace")
        )
    except Exception as exc:
        return {
            "ok": False,
            "error": _bounded_text(exc, 160),
            "points": points,
        }
    route = (payload.get("routes") or [None])[0]
    if not isinstance(route, dict) or not route.get("geometry"):
        return {"ok": False, "error": "No driving route for those places.", "points": points}
    return {
        "ok": True,
        "error": "",
        "points": points,
        "geometry": route.get("geometry"),
        "distance_m": _float(route.get("distance"), 0.0) or 0.0,
        "duration_s": _float(route.get("duration"), 0.0) or 0.0,
    }


def _read_xml(url: str) -> ET.Element:
    return ET.fromstring(_read_public(url))


def _normalize_earthquakes(payload: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    features = payload.get("features", []) if isinstance(payload, dict) else []
    for feature in features[:MAX_EARTHQUAKES]:
        if not isinstance(feature, dict):
            continue
        props = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        coords = geometry.get("coordinates") or []
        lon = _float(coords[0] if len(coords) > 0 else None)
        lat = _float(coords[1] if len(coords) > 1 else None)
        if lat is None or lon is None:
            continue
        magnitude = _float(props.get("mag"), 0.0)
        rows.append(
            {
                "id": _bounded_text(feature.get("id"), 80),
                "place": _bounded_text(props.get("place"), 180),
                "magnitude": round(float(magnitude or 0.0), 1),
                "depth_km": round(float(_float(coords[2], 0.0) or 0.0), 1)
                if len(coords) > 2
                else 0.0,
                "lat": round(lat, 4),
                "lon": round(lon, 4),
                "time": _iso_from_millis(props.get("time")),
                "tsunami": bool(props.get("tsunami")),
                "alert": _bounded_text(props.get("alert"), 32),
                "url": _bounded_text(props.get("url"), 300),
                "type": "earthquake",
            }
        )
    rows.sort(key=lambda row: float(row.get("magnitude") or 0), reverse=True)
    return rows


def _normalize_aircraft(payload: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    raw_states = payload.get("states", []) if isinstance(payload, dict) else []
    usable: list[Any] = [
        state
        for state in raw_states
        if isinstance(state, list) and len(state) >= 11
    ]
    airborne = [state for state in usable if not bool(state[8])]
    pool = airborne or usable
    if len(pool) > MAX_ROWS:
        step = len(pool) / float(MAX_ROWS)
        pool = [pool[int(index * step)] for index in range(MAX_ROWS)]
    for state in pool:
        lon = _float(state[5])
        lat = _float(state[6])
        if lat is None or lon is None:
            continue
        callsign = _bounded_text(state[1], 24) or _bounded_text(state[0], 16)
        rows.append(
            {
                "id": _bounded_text(state[0], 24),
                "callsign": callsign,
                "country": _bounded_text(state[2], 48),
                "lat": round(lat, 4),
                "lon": round(lon, 4),
                "alt_m": round(float(_float(state[7], 0.0) or 0.0)),
                "speed_mps": round(float(_float(state[9], 0.0) or 0.0), 1),
                "heading": round(float(_float(state[10], 0.0) or 0.0)),
                "on_ground": bool(state[8]),
                "last_contact": _iso_from_millis(
                    _int(state[4], 0) * 1000 if len(state) > 4 else 0
                ),
                "type": "aircraft",
            }
        )
    return rows


def _coordinate_from_eonet(geometry: Any) -> tuple[float, float] | None:
    if not isinstance(geometry, dict):
        return None
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list):
        return None
    # Point is the normal EONET shape.  For a polygon/line, use the first
    # coordinate that looks like [longitude, latitude].
    candidates: list[Any] = [coordinates]
    while candidates:
        candidate = candidates.pop(0)
        if (
            isinstance(candidate, list)
            and len(candidate) >= 2
            and not isinstance(candidate[0], list)
        ):
            lon = _float(candidate[0])
            lat = _float(candidate[1])
            if lat is not None and lon is not None:
                return lat, lon
        elif isinstance(candidate, list):
            candidates[0:0] = candidate[:10]
    return None


def _normalize_fires(payload: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    events = payload.get("events", []) if isinstance(payload, dict) else []
    for event in events[:MAX_FIRE_ROWS]:
        if not isinstance(event, dict):
            continue
        categories = event.get("categories") or []
        category_names = " ".join(
            _bounded_text(item.get("title") or item.get("id"), 40)
            for item in categories
            if isinstance(item, dict)
        ).lower()
        title = _bounded_text(event.get("title"), 180)
        if not any(
            token in (category_names + " " + title.lower())
            for token in ("wildfire", "wildfires", "fire", "volcano")
        ):
            continue
        geometries = event.get("geometry") or []
        geometry = geometries[-1] if geometries else {}
        coord = _coordinate_from_eonet(geometry)
        if coord is None:
            continue
        lat, lon = coord
        rows.append(
            {
                "id": _bounded_text(event.get("id"), 80),
                "title": title,
                "category": _bounded_text(category_names, 80) or "EVENT",
                "lat": round(lat, 4),
                "lon": round(lon, 4),
                "date": _bounded_text(geometry.get("date"), 40)
                if isinstance(geometry, dict)
                else "",
                "url": _bounded_text(event.get("link"), 300),
                "type": "fire",
            }
        )
    return rows


def _normalize_satellites(payload: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    values = payload if isinstance(payload, list) else []
    for satellite in values[:MAX_SATELLITES]:
        if not isinstance(satellite, dict):
            continue
        name = _bounded_text(satellite.get("OBJECT_NAME"), 80)
        if not name:
            continue
        rows.append(
            {
                "id": _bounded_text(satellite.get("NORAD_CAT_ID"), 24),
                "name": name,
                "norad": _int(satellite.get("NORAD_CAT_ID"), 0),
                "inclination": round(
                    float(_float(satellite.get("INCLINATION"), 0.0) or 0.0), 1
                ),
                "mean_motion": round(
                    float(_float(satellite.get("MEAN_MOTION"), 0.0) or 0.0), 2
                ),
                "type": "satellite",
            }
        )
    return rows


def _local_name(tag: Any) -> str:
    value = str(tag or "")
    return value.rsplit("}", 1)[-1].lower()


def _child_text(node: ET.Element, name: str) -> str:
    wanted = name.lower()
    for child in list(node):
        if _local_name(child.tag) == wanted:
            return _bounded_text(child.text, 300)
    return ""


def _risk_score(text: str) -> int:
    words = (
        "war", "missile", "strike", "attack", "crisis", "conflict",
        "military", "nuclear", "invasion", "sanctions", "ceasefire",
        "drone", "weapon", "earthquake", "fire",
    )
    lowered = text.lower()
    return min(10, 1 + sum(1 for word in words if word in lowered) * 2)


def _normalize_news(root: ET.Element) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for node in root.iter():
        if _local_name(node.tag) != "item":
            continue
        title = _child_text(node, "title")
        if not title:
            continue
        description = _child_text(node, "description")
        rows.append(
            {
                "id": _bounded_text(_child_text(node, "guid") or title, 100),
                "title": title,
                "description": description,
                "source": "BBC WORLD",
                "published": _child_text(node, "pubDate"),
                "url": _child_text(node, "link"),
                "risk_score": _risk_score(title + " " + description),
                "type": "news",
            }
        )
        geo = _geocode_text(title + " " + description)
        if geo:
            rows[-1]["lat"] = geo[0]
            rows[-1]["lon"] = geo[1]
            rows[-1]["place"] = geo[2]
        if len(rows) >= MAX_NEWS_ROWS:
            break
    return rows


def _geocode_text(text: str) -> tuple[float, float, str] | None:
    lowered = f" {text.lower()} "
    for name, lat, lon in PLACE_COORDS:
        if f" {name} " in lowered or lowered.startswith(name + " ") or lowered.endswith(" " + name + " "):
            return lat, lon, name
        if name in lowered:
            return lat, lon, name
    return None


def _stream_item(
    *,
    item_id: str,
    kind: str,
    title: str,
    summary: str,
    source: str,
    time: str,
    url: str,
    lat: float | None,
    lon: float | None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "id": _bounded_text(item_id, 100),
        "kind": kind,
        "title": _bounded_text(title, 220),
        "summary": _bounded_text(summary, 400),
        "source": _bounded_text(source, 48),
        "time": _bounded_text(time, 40),
        "url": _bounded_text(url, 300),
        "risk_score": _risk_score(f"{title} {summary}"),
    }
    if lat is not None and lon is not None:
        payload["lat"] = round(float(lat), 4)
        payload["lon"] = round(float(lon), 4)
    if extra:
        payload.update(extra)
    return payload


def _build_stream() -> list[dict[str, Any]]:
    buckets = [
        [
            _stream_item(
                item_id=str(row.get("id") or row.get("title")),
                kind="gdelt",
                title=str(row.get("title") or "GDELT"),
                summary=str(row.get("summary") or ""),
                source="GDELT",
                time=str(row.get("time") or ""),
                url=str(row.get("url") or ""),
                lat=row.get("lat"),
                lon=row.get("lon"),
                extra={"place": row.get("place") or ""},
            )
            for row in (_collections.get("gdelt") or [])[:8]
        ],
        [
            _stream_item(
                item_id=str(row.get("id") or "quake"),
                kind="earthquakes",
                title=f"M{row.get('magnitude')} {row.get('place') or 'earthquake'}",
                summary=f"Depth {row.get('depth_km')} km",
                source="USGS",
                time=str(row.get("time") or ""),
                url=str(row.get("url") or ""),
                lat=row.get("lat"),
                lon=row.get("lon"),
                extra={"magnitude": row.get("magnitude"), "depth_km": row.get("depth_km")},
            )
            for row in (_collections.get("earthquakes") or [])[:6]
        ],
        [
            _stream_item(
                item_id=str(row.get("id") or "fire"),
                kind="fires",
                title=str(row.get("title") or "Fire"),
                summary=str(row.get("category") or "EONET"),
                source="NASA EONET",
                time=str(row.get("time") or ""),
                url=str(row.get("url") or ""),
                lat=row.get("lat"),
                lon=row.get("lon"),
            )
            for row in (_collections.get("fires") or [])[:6]
        ],
        [
            _stream_item(
                item_id=str(row.get("id")),
                kind="conflicts",
                title=str(row.get("label")),
                summary="Reference watchlist location, not independently verified live status.",
                source="WATCHLIST",
                time="",
                url=OSIRIS_REPOSITORY_URL,
                lat=row.get("lat"),
                lon=row.get("lon"),
                extra={"severity": row.get("severity")},
            )
            for row in REFERENCE_ZONES[:8]
        ],
        [
            _stream_item(
                item_id=str(row.get("id") or row.get("title")),
                kind="news",
                title=str(row.get("title") or "News"),
                summary=str(row.get("description") or ""),
                source=str(row.get("source") or "BBC WORLD"),
                time=str(row.get("published") or ""),
                url=str(row.get("url") or ""),
                lat=row.get("lat"),
                lon=row.get("lon"),
                extra={"place": row.get("place") or ""},
            )
            for row in (_collections.get("news") or [])[:6]
        ],
    ]
    items: list[dict[str, Any]] = []
    index = 0
    while len(items) < MAX_STREAM_ROWS:
        added = False
        for bucket in buckets:
            if index < len(bucket):
                items.append(bucket[index])
                added = True
                if len(items) >= MAX_STREAM_ROWS:
                    break
        if not added:
            break
        index += 1
    return items


def _human_themes(text: str) -> str:
    parts: list[str] = []
    for raw in str(text or "").split(";"):
        token = raw.strip()
        if not token or token.startswith(("TAX_", "WB_", "EPU_", "CRISISLEX_", "UNGP_")):
            continue
        parts.append(token.replace("_", " ").title())
        if len(parts) >= 4:
            break
    return "; ".join(parts)


def _normalize_gdelt(payload: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    features = payload.get("features", []) if isinstance(payload, dict) else []
    features = sorted(
        [feature for feature in features if isinstance(feature, dict)],
        key=lambda feat: (
            0 if "," in str((feat.get("properties") or {}).get("name") or "") else 1
        ),
    )
    seen: set[str] = set()
    for feature in features:
        if len(rows) >= MAX_GDELT_ROWS:
            break
        coords = ((feature.get("geometry") or {}).get("coordinates")) or []
        lon = _float(coords[0] if len(coords) > 0 else None)
        lat = _float(coords[1] if len(coords) > 1 else None)
        if lat is None or lon is None:
            continue
        props = feature.get("properties") or {}
        title = _bounded_text(props.get("name") or "GDELT", 180)
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        url = _bounded_text(props.get("url") or props.get("urlSrc") or "", 300)
        rows.append(
            {
                "id": _bounded_text(url or f"{lat},{lon}", 100),
                "title": title,
                "summary": _human_themes(str(props.get("mentionedthemes") or "")),
                "place": title,
                "time": _bounded_text(
                    props.get("urlpubtimedate") or props.get("seendate") or "", 40
                ),
                "url": url,
                "lat": round(lat, 4),
                "lon": round(lon, 4),
                "type": "gdelt",
            }
        )
    return rows


def _solar_value(item: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in item:
            return item[name]
    return None


def _normalize_solar(payload: Any) -> dict[str, Any]:
    rows = payload if isinstance(payload, list) else []
    latest = rows[-1] if rows and isinstance(rows[-1], dict) else {}
    kp = _float(_solar_value(latest, "kp_index", "Kp", "kp"), 0.0) or 0.0
    if kp >= 8:
        level = "EXTREME"
    elif kp >= 7:
        level = "SEVERE"
    elif kp >= 6:
        level = "STRONG"
    elif kp >= 5:
        level = "MODERATE"
    elif kp >= 4:
        level = "MINOR"
    elif kp >= 3:
        level = "UNSETTLED"
    else:
        level = "QUIET"
    return {
        "kp_index": round(kp, 1),
        "storm_level": level,
        "time": _bounded_text(_solar_value(latest, "time_tag", "time"), 40),
        "samples": len(rows),
    }


def _collect_earthquakes() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = _normalize_earthquakes(_read_json(USGS_URL))
    return rows, {}


def _collect_aircraft() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = _normalize_aircraft(_read_json(OPENSKY_URL))
    return rows, {"region": "GLOBAL SAMPLE"}


def _collect_fires() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return _normalize_fires(_read_json(EONET_URL)), {}


def _collect_satellites() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return _normalize_satellites(_read_json(CELESTRAK_URL)), {}


def _collect_solar() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payload = _read_json(NOAA_URL)
    return [], {"solar": _normalize_solar(payload)}


def _collect_news() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return _normalize_news(_read_xml(BBC_URL)), {}


def _collect_gdelt() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return _normalize_gdelt(_read_json(GDELT_URL, timeout=12.0)), {}


def _load_local_alpr() -> list[dict[str, Any]]:
    """Load the bundled OSM/DeFlock ALPR location sample. Pins only, no video."""
    payload = json.loads(ALPR_SAMPLE_PATH.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    for feature in payload.get("features") or []:
        if not isinstance(feature, dict):
            continue
        coords = ((feature.get("geometry") or {}).get("coordinates")) or []
        lon = _float(coords[0] if len(coords) > 0 else None)
        lat = _float(coords[1] if len(coords) > 1 else None)
        if lat is None or lon is None:
            continue
        props = feature.get("properties") or {}
        osm_id = _int(props.get("osm"), 0)
        brand = _bounded_text(props.get("brand"), 48) or "ALPR"
        rows.append(
            {
                "id": str(osm_id or f"{lat:.4f},{lon:.4f}"),
                "label": brand,
                "brand": brand,
                "zone": _bounded_text(props.get("zone"), 32),
                "lat": round(lat, 4),
                "lon": round(lon, 4),
                "osm_id": osm_id,
                "url": (
                    f"https://www.openstreetmap.org/node/{osm_id}"
                    if osm_id
                    else DEFLOCK_URL
                ),
                "type": "alpr",
                "live_video": False,
            }
        )
    return rows


def _collect_cameras() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = _load_local_alpr()
    return rows[:MAX_CAMERA_ROWS], {
        "total": len(rows),
        "mode": "LOCATION_PINS_ONLY",
    }


_COLLECTORS: dict[str, Callable[[], tuple[list[dict[str, Any]], dict[str, Any]]]] = {
    "earthquakes": _collect_earthquakes,
    "aircraft": _collect_aircraft,
    "fires": _collect_fires,
    "satellites": _collect_satellites,
    "solar": _collect_solar,
    "news": _collect_news,
    "gdelt": _collect_gdelt,
    "cameras": _collect_cameras,
}


def _history_push(key: str, value: int) -> None:
    values = _histories.setdefault(key, [])
    values.append(max(0, int(value)))
    if len(values) > MAX_HISTORY:
        del values[: len(values) - MAX_HISTORY]


def _snapshot_locked(page: str) -> dict[str, Any]:
    source_rows = [dict(row) for row in _sources.values()]
    healthy = sum(1 for row in source_rows if row["status"] in ("OK", "REFERENCE"))
    live = sum(1 for row in source_rows if row["status"] == "OK")
    failed = sum(1 for row in source_rows if row["status"] == "ERROR")
    if live == len(_COLLECTORS):
        status = "LIVE"
    elif live > 0:
        status = "DEGRADED"
    elif failed > 0:
        status = "OFFLINE"
    else:
        status = "READY"
    return {
        "schema": SCHEMA,
        "scope": SAFE_SCOPE,
        "page": str(page or "OVERVIEW").upper(),
        "status": status,
        "generated_at": _last_generated_at,
        "stale": bool(failed or not _last_generated_at),
        "source_count": len(source_rows),
        "healthy_sources": healthy,
        "counts": {
            "aircraft": len(_collections["aircraft"]),
            "earthquakes": len(_collections["earthquakes"]),
            "fires": len(_collections["fires"]),
            "satellites": len(_collections["satellites"]),
            "news": len(_collections["news"]),
            "gdelt": len(_collections["gdelt"]),
            "cameras": _cached_alpr_total(),
            "conflicts": len(REFERENCE_ZONES),
        },
        "aircraft": [dict(row) for row in _collections["aircraft"]],
        "earthquakes": [dict(row) for row in _collections["earthquakes"]],
        "fires": [dict(row) for row in _collections["fires"]],
        "satellites": [dict(row) for row in _collections["satellites"]],
        "news": [dict(row) for row in _collections["news"]],
        "gdelt": [dict(row) for row in _collections["gdelt"]],
        "cameras": [dict(row) for row in _collections["cameras"]],
        "solar": dict(_solar),
        "conflicts": [dict(row) for row in REFERENCE_ZONES],
        "stream": _build_stream(),
        "sources": source_rows,
        "histories": {key: list(value) for key, value in _histories.items()},
        "focus": {
            "label": "GLOBAL",
            "lat": 22.0,
            "lon": 18.0,
            "note": "OpenSky sample plus public OSM/DeFlock ALPR location pins.",
        },
        "recon": {
            "mode": "SAFE_BOUNDARY",
            "status": "PUBLIC FEEDS ONLY",
            "available": [
                "SOURCE HEALTH",
                "EVENT MAP",
                "FLIGHT SNAPSHOT",
                "SEISMIC / FIRE / SPACE / NEWS VIEWS",
                "ALPR LOCATION PINS (OSM / DEFLOCK SAMPLE)",
                "CLICK STREAM TO FLY GLOBE",
                "OSM / OSRM NAVIGATION",
            ],
            "not_enabled": [
                "PORT SCANS",
                "IP SWEEPS",
                "LIVE CAMERA TAKEOVER",
                "ARBITRARY TARGET PROBING",
                "CREDENTIAL ACCESS",
            ],
        },
    }


def empty_snapshot(page: str = "OVERVIEW") -> dict[str, Any]:
    """Return the current local snapshot without causing network activity."""
    with _lock:
        return _snapshot_locked(page)


def snapshot(page: str = "OVERVIEW") -> dict[str, Any]:
    return empty_snapshot(page)


def collect_snapshot(page: str = "OVERVIEW", force: bool = False) -> dict[str, Any]:
    """Collect allowlisted feeds concurrently and return a native snapshot."""
    global _last_collect_at, _last_generated_at, _solar, _alpr_total
    now = time.monotonic()
    with _lock:
        if (
            not force
            and _last_generated_at
            and now - _last_collect_at < CACHE_TTL_SECONDS
        ):
            return _snapshot_locked(page)

    results: dict[str, tuple[list[dict[str, Any]], dict[str, Any]]] = {}
    errors: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=len(_COLLECTORS), thread_name_prefix="gg-osiris") as pool:
        futures = {
            pool.submit(collector): source_id
            for source_id, collector in _COLLECTORS.items()
        }
        for future in as_completed(futures):
            source_id = futures[future]
            try:
                results[source_id] = future.result()
            except Exception as exc:  # a dead public feed must not kill the UI
                errors[source_id] = _bounded_text(exc, 160)

    stamp = _utc_now()
    with _lock:
        _last_collect_at = time.monotonic()
        _last_generated_at = stamp
        for source in SOURCE_CATALOG:
            source_id = str(source["id"])
            row = _sources[source_id]
            row["last_updated"] = stamp
            if source_id == "conflicts":
                row["status"] = "REFERENCE"
                row["count"] = len(REFERENCE_ZONES)
                row["error"] = ""
                continue
            if source_id in errors:
                row["status"] = "ERROR"
                row["error"] = errors[source_id]
                continue
            rows, extras = results.get(source_id, ([], {}))
            if source_id in _collections:
                _collections[source_id] = rows[:MAX_ROWS]
                _history_push(source_id, len(_collections[source_id]))
                row["count"] = len(_collections[source_id])
            if source_id == "solar":
                _solar = dict(extras.get("solar") or {})
                _history_push("solar", int(round(float(_solar.get("kp_index") or 0) * 10)))
                row["count"] = 1 if _solar else 0
            if source_id == "aircraft":
                region = extras.get("region")
                if region:
                    row["region"] = str(region)
            if source_id == "cameras":
                _alpr_total = int(extras.get("total") or len(rows))
                row["count"] = _alpr_total
                row["status"] = "LOCAL"
                row["error"] = ""
                continue
            row["status"] = "OK"
            row["error"] = ""
    return empty_snapshot(page)

