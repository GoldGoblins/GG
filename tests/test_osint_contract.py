#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))


def main() -> int:
    from backend import osint_contract

    assert osint_contract.SAFE_SCOPE == "PUBLIC_READ_ONLY"
    assert len(osint_contract.SOURCE_CATALOG) == 9
    assert all(
        source["url"] in osint_contract.ALLOWED_SOURCE_URLS
        for source in osint_contract.SOURCE_CATALOG
    )
    try:
        osint_contract._read_public("https://example.invalid/not-allowlisted")
    except ValueError:
        pass
    else:
        raise AssertionError("arbitrary OSINT URL was accepted")
    try:
        osint_contract._read_map_api("https://example.invalid/route")
    except ValueError:
        pass
    else:
        raise AssertionError("arbitrary map API host was accepted")
    empty_route = osint_contract.plan_driving_route(["gothenburg"])
    assert empty_route["ok"] is False

    earthquakes = osint_contract._normalize_earthquakes(
        {
            "features": [
                {
                    "id": "test-quake",
                    "geometry": {"coordinates": [18.1, 59.3, 12.5]},
                    "properties": {
                        "mag": 4.2,
                        "place": "Test region",
                        "time": 1788897600000,
                        "tsunami": 0,
                    },
                }
            ]
        }
    )
    assert earthquakes[0]["magnitude"] == 4.2
    assert earthquakes[0]["lat"] == 59.3
    assert earthquakes[0]["lon"] == 18.1

    sampled = osint_contract._normalize_aircraft(
        {
            "states": [
                [
                    f"icao{index:03d}",
                    f"CS{index:03d}",
                    "Sweden",
                    None,
                    1_700_000_000,
                    18.0 + index,
                    59.0,
                    9000,
                    False,
                    200.0,
                    90.0,
                ]
                for index in range(400)
            ]
        }
    )
    assert len(sampled) == osint_contract.MAX_ROWS
    assert sampled[0]["heading"] == 90
    assert sampled[0]["on_ground"] is False

    fires = osint_contract._normalize_fires(
        {
            "events": [
                {
                    "id": "eonet-test",
                    "title": "Test wildfire",
                    "categories": [{"id": "wildfires", "title": "Wildfires"}],
                    "geometry": [
                        {
                            "date": "2026-09-08T12:00:00Z",
                            "coordinates": [17.9, 59.4],
                        }
                    ],
                    "link": "https://example.invalid/event",
                }
            ]
        }
    )
    assert fires[0]["type"] == "fire"
    assert fires[0]["lon"] == 17.9

    satellites = osint_contract._normalize_satellites(
        [
            {
                "OBJECT_NAME": "ISS (ZARYA)",
                "NORAD_CAT_ID": 25544,
                "INCLINATION": 51.6,
                "MEAN_MOTION": 15.5,
            }
        ]
    )
    assert satellites[0]["norad"] == 25544
    assert satellites[0]["name"] == "ISS (ZARYA)"

    news_root = osint_contract.ET.fromstring(
        "<rss><channel><item><title>Test world event</title>"
        "<description>Short report</description><link>https://example.invalid</link>"
        "<pubDate>today</pubDate></item></channel></rss>"
    )
    news = osint_contract._normalize_news(news_root)
    assert news[0]["source"] == "BBC WORLD"
    assert news[0]["title"] == "Test world event"

    pinned = osint_contract._normalize_news(
        osint_contract.ET.fromstring(
            "<rss><channel><item><title>Strike reported near Ukraine border</title>"
            "<description>Field report</description><link>https://example.invalid/u</link>"
            "<pubDate>today</pubDate></item></channel></rss>"
        )
    )
    assert pinned[0]["lat"] == 49.0
    assert pinned[0]["lon"] == 32.0

    solar = osint_contract._normalize_solar(
        [{"time_tag": "2026-09-08T12:00:00Z", "kp_index": 4.3}]
    )
    assert solar["kp_index"] == 4.3
    assert solar["storm_level"] == "MINOR"

    empty = osint_contract.empty_snapshot("MAP")
    assert empty["schema"] == osint_contract.SCHEMA
    assert empty["scope"] == "PUBLIC_READ_ONLY"
    assert empty["page"] == "MAP"
    assert len(empty["conflicts"]) == 13
    assert empty["recon"]["mode"] == "SAFE_BOUNDARY"
    assert "PORT SCANS" in empty["recon"]["not_enabled"]
    assert "LIVE CAMERA TAKEOVER" in empty["recon"]["not_enabled"]
    assert empty["counts"]["cameras"] >= 100
    assert empty["stream"]
    assert any(item.get("lat") is not None for item in empty["stream"])
    gdelt = osint_contract._normalize_gdelt(
        {
            "features": [
                {
                    "geometry": {"coordinates": [32.0, 49.0]},
                    "properties": {
                        "name": "Kyiv",
                        "url": "https://example.invalid/g",
                        "urlpubtimedate": "2026-09-09",
                    },
                }
            ]
        }
    )
    assert gdelt[0]["lat"] == 49.0
    assert gdelt[0]["title"] == "Kyiv"
    alpr = osint_contract._load_local_alpr()
    assert alpr[0]["live_video"] is False
    assert alpr[0]["lat"] is not None

    qml = (PROJECT / "qml/components/OsintSurface.qml").read_text(
        encoding="utf-8"
    )
    globe = (PROJECT / "qml/components/OsintGlobe.qml").read_text(
        encoding="utf-8"
    )
    workspace = (PROJECT / "qml/components/WorkspaceSurface.qml").read_text(
        encoding="utf-8"
    )
    settings = (
        PROJECT / "qml/components/SettingsWorkspaceModule.qml"
    ).read_text(encoding="utf-8")
    for marker in (
        'objectName: "workspaceOsintPane"',
        'text: "PUBLIC READ-ONLY RECON"',
        'leftLegend: "EVENT MAP"',
        'leftLegend: "SOURCE HEALTH"',
        'leftLegend: "RECON BOUNDARY"',
        "osintSnapshot",
        "osintRefresh",
    ):
        assert marker in qml or marker in workspace, marker
    assert 'objectName: "workspaceOsintPane"' in workspace
    assert 'active: !root.settingsOpen && root.hostKind === "OSINT"' in workspace
    assert 'objectName: "workspaceKindOSINT"' in workspace
    assert workspace.index('text: "TMOG"') < workspace.index('text: "OSINT"')
    assert workspace.index('text: "OSINT"') < workspace.index('text: "MEDIA"')
    assert '"OSINT"' in settings
    assert 'text: "OSINT"' in qml
    assert "color: root.ledgerGold" in qml
    assert "user-supplied target" in qml.lower()
    html = (PROJECT / "qml/osint-map/index.html").read_text(encoding="utf-8")
    script = (PROJECT / "qml/osint-map/map.js").read_text(encoding="utf-8")
    countries = PROJECT / "qml/osint-map/data/countries.geojson"
    alpr_path = PROJECT / "qml/osint-map/data/alpr.geojson"
    vendor = PROJECT / "qml/osint-map/vendor/maplibre-gl.js"
    assert countries.is_file() and countries.stat().st_size > 50_000
    assert alpr_path.is_file() and alpr_path.stat().st_size > 20_000
    assert vendor.is_file() and vendor.stat().st_size > 200_000
    assert osint_contract.OPENSKY_URL == "https://opensky-network.org/api/states/all"
    assert '"type":"FeatureCollection"' in countries.read_text(encoding="utf-8")[:80]
    for marker in (
        "import QtWebEngine",
        'objectName: "osintGlobe"',
        "WebEngineView",
        "setOsintPoints",
        'url: Qt.resolvedUrl("../osint-map/index.html")',
        "webGLEnabled: true",
        "function focusPoint",
    ):
        assert marker in globe, marker
    for marker in (
        "tiles.openfreemap.org/styles/dark",
        "data/countries.geojson",
        "data/alpr.geojson",
        "window.setOsintPoints",
        "window.focusOsintPoint",
        "window.setOsintRoute",
        "router.project-osrm.org",
        "source: 'waypoints'",
        "setRouteData(route.geometry, points)",
        "nominatim.openstreetmap.org",
        "setProjection",
        "LineString",
        "conflict-label",
        "minzoom: 4",
    ):
        assert marker in script, marker
    assert "tiles.openfreemap.org" in html
    assert "nominatim.openstreetmap.org" in html
    assert 'id="nav"' in html
    assert "osintSharedPane" in qml
    assert "function commitNavPlace" in qml
    assert "function moveNavPlace" in qml
    assert 'color: root.navMode ? "#1a1a1a" : "#181818"' in qml
    assert "TYPE A PLACE + ENTER" in qml
    assert "function applyRoute" in globe
    assert "osintPlanRoute" in qml
    gdelt_dup = osint_contract._normalize_gdelt(
        {
            "features": [
                {
                    "geometry": {"coordinates": [32.0, 49.0]},
                    "properties": {"name": "Kyiv", "url": "https://example.invalid/a", "mentionedthemes": ";WAR;TAX_ETHNICITY_X;"},
                },
                {
                    "geometry": {"coordinates": [32.1, 49.1]},
                    "properties": {"name": "Kyiv", "url": "https://example.invalid/b", "mentionedthemes": ";WAR;"},
                },
            ]
        }
    )
    assert len(gdelt_dup) == 1
    assert "TAX_" not in gdelt_dup[0]["summary"]
    assert "vendor/maplibre-gl.js" in html
    main_py = (PROJECT / "main.py").read_text(encoding="utf-8")
    assert "QTWEBENGINE_CHROMIUM_FLAGS" in main_py
    assert "--disable-gpu" not in main_py
    assert "--enable-webgl" in main_py

    from PySide6.QtCore import QObject, QUrl, Slot, qInstallMessageHandler
    from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
    from PySide6.QtGui import QGuiApplication
    from backend.osint_host import OsintHost

    app = QGuiApplication.instance() or QGuiApplication([])
    host = OsintHost()
    payload = json.loads(host.snapshot("SOURCES"))
    assert payload["page"] == "SOURCES"
    assert payload["schema"] == osint_contract.SCHEMA
    host.shutdown()
    app.processEvents()

    fixture = osint_contract.empty_snapshot("OVERVIEW")
    fixture["counts"] = {
        "aircraft": 1,
        "earthquakes": 1,
        "fires": 1,
        "satellites": 1,
        "news": 1,
        "conflicts": 1,
    }
    fixture["aircraft"] = [{
        "id": "abc123", "callsign": "GGTEST", "country": "Sweden",
        "lat": 59.3, "lon": 18.1, "alt_m": 9000,
        "heading": 240, "speed_mps": 220.0, "on_ground": False,
    }]
    fixture["earthquakes"] = [{
        "id": "quake", "place": "Test region", "magnitude": 3.2,
        "depth_km": 10, "lat": 59.3, "lon": 18.1,
        "time": "2026-09-08T12:00:00Z", "url": "https://example.invalid/q",
    }]
    fixture["fires"] = [{
        "id": "fire", "title": "Test fire", "category": "WILDFIRE",
        "lat": 59.4, "lon": 17.9, "url": "https://example.invalid/f",
    }]
    fixture["satellites"] = [{
        "id": "25544", "name": "ISS", "norad": 25544,
        "inclination": 51.6,
    }]
    fixture["news"] = [{
        "id": "news", "title": "Test world event", "source": "BBC WORLD",
        "published": "today", "url": "https://example.invalid/n",
        "risk_score": 2,
    }]
    fixture["conflicts"] = [
        {"id": "test-zone", "label": "TEST ZONE", "lat": 59.0,
         "lon": 18.0, "severity": 2}
    ]

    class FakeSurfaceHost(QObject):
        @Slot(str, result=str)
        def osintSnapshot(self, page: str = "OVERVIEW") -> str:
            payload = dict(fixture)
            payload["page"] = str(page or "OVERVIEW").upper()
            return json.dumps(payload)

        @Slot(str, result=bool)
        def osintRefresh(self, page: str = "OVERVIEW") -> bool:
            return False

        @Slot(str)
        def osintCopy(self, value: str) -> None:
            return None

        @Slot(str, result=str)
        def osintPlanRoute(self, spec_json: str = "{}") -> str:
            return json.dumps({"ok": False, "error": "test-skip", "points": []})

    engine = QQmlApplicationEngine()
    component = QQmlComponent(
        engine,
        QUrl.fromLocalFile(str(PROJECT / "qml/components/OsintSurface.qml")),
    )
    assert not component.errors(), [error.toString() for error in component.errors()]
    surface = component.create()
    assert surface is not None
    fake = FakeSurfaceHost()
    assert surface.setProperty("surfaceHost", fake)
    assert surface.setProperty("width", 1100)
    assert surface.setProperty("height", 720)
    assert surface.setProperty("payload", fixture)
    assert surface.setProperty("visible", True)
    messages: list[str] = []
    qInstallMessageHandler(
        lambda _kind, _context, message: messages.append(str(message))
    )
    app.processEvents()
    assert surface.findChild(QObject, "osintMapPage") is not None
    assert surface.findChild(QObject, "osintSourcesPage") is not None
    globe = surface.findChild(QObject, "osintGlobe")
    assert globe is not None
    assert int(globe.property("pointCount")) == 4
    assert surface.setProperty("page", "MAP")
    app.processEvents()
    assert str(surface.property("page")) == "MAP"
    bad_messages = [
        message for message in messages
        if any(token in message for token in (
            "ReferenceError", "TypeError", "Cannot assign", "Unable to assign",
        ))
    ]
    assert not bad_messages, bad_messages
    qInstallMessageHandler(None)
    surface.deleteLater()
    app.processEvents()
    print("OSINT_CONTRACT_TEST=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
