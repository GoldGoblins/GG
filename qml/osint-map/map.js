/* MapLibre GL JS 5.24.0 (BSD-3-Clause), local runtime.
   Dark OSM/CARTO raster basemap + local Natural Earth land fallback. */
'use strict';
(() => {
    const status = document.getElementById('status');
    const retry = document.getElementById('retry');
    const empty = {type: 'FeatureCollection', features: []};
    const colors = {
        aircraft: '#2ee59d',
        earthquakes: '#e0b15a',
        fires: '#ff5b5b',
        conflicts: '#ff7a3d'
    };
    const home = {center: [18, 22], zoom: 1.65, bearing: 0, pitch: 0};
    const remoteStyle = 'https://tiles.openfreemap.org/styles/dark';
    let map, pending = [], restored = null, loaded = false, projection = 'globe';
    let conflictMarkers = [];
    let usingFallback = false;

    function finite(value) {
        return Number.isFinite(value);
    }

    function destination(lon, lat, heading, km) {
        const radius = 6371;
        const bearing = heading * Math.PI / 180;
        const angle = km / radius;
        const lat1 = lat * Math.PI / 180;
        const lon1 = lon * Math.PI / 180;
        const lat2 = Math.asin(
            Math.sin(lat1) * Math.cos(angle)
            + Math.cos(lat1) * Math.sin(angle) * Math.cos(bearing)
        );
        const lon2 = lon1 + Math.atan2(
            Math.sin(bearing) * Math.sin(angle) * Math.cos(lat1),
            Math.cos(angle) - Math.sin(lat1) * Math.sin(lat2)
        );
        return [((lon2 * 180 / Math.PI + 540) % 360) - 180, lat2 * 180 / Math.PI];
    }

    function validPoint(point) {
        return point && finite(point.lat) && finite(point.lon)
            && Math.abs(point.lat) <= 90 && Math.abs(point.lon) <= 180;
    }

    function collections() {
        const points = [];
        const tracks = [];
        const fires = [];
        const quakes = [];
        const conflicts = [];
        for (const point of pending.filter(validPoint)) {
            const kind = String(point.kind || 'event');
            const feature = {
                type: 'Feature',
                geometry: {type: 'Point', coordinates: [point.lon, point.lat]},
                properties: {
                    kind,
                    label: String(point.label || kind),
                    color: colors[kind] || String(point.color || '#7fa9c4'),
                    heading: finite(Number(point.heading)) ? Number(point.heading) : null,
                    magnitude: finite(Number(point.magnitude)) ? Number(point.magnitude) : null,
                    alt_m: finite(Number(point.alt_m)) ? Number(point.alt_m) : null
                }
            };
            points.push(feature);
            if (kind === 'fires')
                fires.push(feature);
            if (kind === 'earthquakes')
                quakes.push(feature);
            if (kind === 'conflicts')
                conflicts.push(feature);
            if (kind === 'aircraft' && !point.on_ground && finite(Number(point.heading))) {
                const heading = Number(point.heading);
                const start = destination(point.lon, point.lat, heading, -8);
                const end = destination(point.lon, point.lat, heading, 28);
                tracks.push({
                    type: 'Feature',
                    geometry: {type: 'LineString', coordinates: [start, [point.lon, point.lat], end]},
                    properties: {kind: 'track'}
                });
            }
        }
        return {
            points: {type: 'FeatureCollection', features: points},
            tracks: {type: 'FeatureCollection', features: tracks},
            fires: {type: 'FeatureCollection', features: fires},
            quakes: {type: 'FeatureCollection', features: quakes},
            conflicts: {type: 'FeatureCollection', features: conflicts}
        };
    }

    function styleSpec() {
        return {
            version: 8,
            name: 'gg-osint-earth',
            sources: {
                land: {type: 'geojson', data: 'data/countries.geojson'},
                alpr: {type: 'geojson', data: 'data/alpr.geojson'},
                tracks: {type: 'geojson', data: empty},
                fires: {type: 'geojson', data: empty},
                quakes: {type: 'geojson', data: empty},
                events: {type: 'geojson', data: empty},
                route: {type: 'geojson', data: empty},
                waypoints: {type: 'geojson', data: empty},
                focus: {type: 'geojson', data: empty}
            },
            layers: [
                {id: 'background', type: 'background', paint: {'background-color': '#05070c'}},
                {
                    id: 'land-fill',
                    type: 'fill',
                    source: 'land',
                    paint: {'fill-color': '#182230', 'fill-opacity': 1}
                },
                {
                    id: 'land-border',
                    type: 'line',
                    source: 'land',
                    paint: {'line-color': '#4d6578', 'line-width': 0.6, 'line-opacity': 0.85}
                },
                {
                    id: 'tracks',
                    type: 'line',
                    source: 'tracks',
                    minzoom: 4,
                    paint: {
                        'line-color': '#3ea0c8',
                        'line-width': ['interpolate', ['linear'], ['zoom'], 4, 1.1, 8, 1.8],
                        'line-opacity': 0.55
                    }
                },
                {
                    id: 'fire-glow',
                    type: 'circle',
                    source: 'fires',
                    paint: {
                        'circle-radius': ['interpolate', ['linear'], ['zoom'], 0, 6, 5, 11, 10, 16],
                        'circle-color': '#ff3b3b',
                        'circle-opacity': 0.16,
                        'circle-blur': 0.8
                    }
                },
                {
                    id: 'quake-glow',
                    type: 'circle',
                    source: 'quakes',
                    paint: {
                        'circle-radius': ['interpolate', ['linear'], ['zoom'], 0, 5, 5, 9, 10, 14],
                        'circle-color': '#e0b15a',
                        'circle-opacity': 0.18,
                        'circle-blur': 0.65
                    }
                },
                {
                    id: 'events',
                    type: 'circle',
                    source: 'events',
                    paint: {
                        'circle-radius': [
                            'interpolate', ['linear'], ['zoom'],
                            0, ['match', ['get', 'kind'], 'conflicts', 4.2, 'fires', 3.2, 'earthquakes', 3.1, 2.3],
                            6, ['match', ['get', 'kind'], 'conflicts', 6.5, 'fires', 5.2, 'earthquakes', 5, 3.6],
                            12, ['match', ['get', 'kind'], 'conflicts', 8, 'fires', 7, 'earthquakes', 6.5, 5]
                        ],
                        'circle-color': ['get', 'color'],
                        'circle-stroke-width': 1.1,
                        'circle-stroke-color': '#05070c',
                        'circle-opacity': 0.92
                    }
                }
            ]
        };
    }

    function report() {
        if (!loaded)
            return;
        const count = collections().points.features.length;
        const mode = projection === 'globe' ? '3D GLOBE' : '2D MAP';
        status.textContent = `${mode} · ${count} EVENTS · ZOOM ${map.getZoom().toFixed(1)}`;
    }

    function syncConflicts(features) {
        for (const marker of conflictMarkers)
            marker.remove();
        conflictMarkers = [];
        const limited = (features || []).slice(0, 16);
        for (const feature of limited) {
            const node = document.createElement('div');
            node.className = 'conflict-label';
            const mark = document.createElement('span');
            mark.className = 'mark';
            mark.textContent = '▲';
            node.appendChild(mark);
            node.appendChild(document.createTextNode(feature.properties.label));
            const marker = new maplibregl.Marker({element: node, anchor: 'bottom', pitchAlignment: 'viewport'})
                .setLngLat(feature.geometry.coordinates)
                .addTo(map);
            conflictMarkers.push(marker);
        }
    }

    function applyPoints() {
        if (!loaded)
            return;
        const data = collections();
        map.getSource('events').setData(data.points);
        map.getSource('tracks').setData(data.tracks);
        map.getSource('fires').setData(data.fires);
        map.getSource('quakes').setData(data.quakes);
        syncConflicts(data.conflicts.features);
        report();
    }

    window.setOsintPoints = points => {
        pending = Array.isArray(points) ? points : [];
        applyPoints();
    };
    window.getOsintView = () => loaded ? {
        lng: map.getCenter().lng,
        lat: map.getCenter().lat,
        zoom: map.getZoom(),
        bearing: map.getBearing(),
        pitch: map.getPitch(),
        projection
    } : null;
    window.restoreOsintView = view => {
        restored = view;
        if (!loaded || !view || !finite(view.lng) || !finite(view.lat))
            return;
        setProjection(view.projection === 'mercator' ? 'mercator' : 'globe');
        map.jumpTo({
            center: [view.lng, view.lat],
            zoom: finite(view.zoom) ? view.zoom : home.zoom,
            bearing: finite(view.bearing) ? view.bearing : 0,
            pitch: finite(view.pitch) ? view.pitch : 0
        });
    };

    function setProjection(value) {
        projection = value;
        if (loaded)
            map.setProjection({type: value});
        document.getElementById('globe').setAttribute('aria-pressed', String(value === 'globe'));
        document.getElementById('flat').setAttribute('aria-pressed', String(value === 'mercator'));
        report();
    }

    function paintSky() {
        try {
            map.setSky({
                'sky-color': '#05070c',
                'horizon-color': '#0b121c',
                'fog-color': '#05070c',
                'sky-horizon-blend': 0.35,
                'horizon-fog-blend': 0.7,
                'fog-ground-blend': 0.6
            });
        } catch (_error) {
            /* Older MapLibre builds ignore sky. */
        }
    }

    function overlayLayers() {
        return [
            {
                id: 'tracks',
                type: 'line',
                source: 'tracks',
                minzoom: 4,
                paint: {
                    'line-color': '#3ea0c8',
                    'line-width': ['interpolate', ['linear'], ['zoom'], 4, 1.1, 8, 1.8],
                    'line-opacity': 0.55
                }
            },
            {
                id: 'alpr',
                type: 'circle',
                source: 'alpr',
                minzoom: 5,
                paint: {
                    'circle-radius': ['interpolate', ['linear'], ['zoom'], 5, 2.4, 12, 5.5],
                    'circle-color': '#6ec4d8',
                    'circle-stroke-width': 0.8,
                    'circle-stroke-color': '#05070c',
                    'circle-opacity': 0.82
                }
            },
            {
                id: 'fire-glow',
                type: 'circle',
                source: 'fires',
                minzoom: 3,
                paint: {
                    'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 5, 10, 12],
                    'circle-color': '#ff3b3b',
                    'circle-opacity': 0.16
                }
            },
            {
                id: 'quake-glow',
                type: 'circle',
                source: 'quakes',
                minzoom: 3,
                paint: {
                    'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 4, 10, 11],
                    'circle-color': '#e0b15a',
                    'circle-opacity': 0.18
                }
            },
            {
                id: 'route',
                type: 'line',
                source: 'route',
                paint: {
                    'line-color': '#c8a97e',
                    'line-width': 3.2,
                    'line-opacity': 0.88
                }
            },
            {
                id: 'waypoints',
                type: 'circle',
                source: 'waypoints',
                paint: {
                    'circle-radius': [
                        'match', ['get', 'role'],
                        'start', 6.5,
                        'end', 6.5,
                        5
                    ],
                    'circle-color': [
                        'match', ['get', 'role'],
                        'start', '#e6edf3',
                        'end', '#c8a97e',
                        '#d5c4a1'
                    ],
                    'circle-stroke-width': 1.6,
                    'circle-stroke-color': '#111111',
                    'circle-opacity': 0.96
                }
            },
            {
                id: 'focus',
                type: 'circle',
                source: 'focus',
                paint: {
                    'circle-radius': 9,
                    'circle-color': '#e4c48a',
                    'circle-opacity': 0.18,
                    'circle-stroke-width': 2,
                    'circle-stroke-color': '#e4c48a'
                }
            },
            {
                id: 'events',
                type: 'circle',
                source: 'events',
                paint: {
                    'circle-radius': [
                        'interpolate', ['linear'], ['zoom'],
                        0, ['match', ['get', 'kind'], 'conflicts', 4.2, 'fires', 3.2, 'earthquakes', 3.1, 2.3],
                        6, ['match', ['get', 'kind'], 'conflicts', 6.5, 'fires', 5.2, 'earthquakes', 5, 3.6],
                        12, ['match', ['get', 'kind'], 'conflicts', 8, 'fires', 7, 'earthquakes', 6.5, 5]
                    ],
                    'circle-color': ['get', 'color'],
                    'circle-stroke-width': 1.1,
                    'circle-stroke-color': '#05070c',
                    'circle-opacity': 0.92
                }
            }
        ];
    }

    function ensureOverlays() {
        for (const id of ['tracks', 'fires', 'quakes', 'events', 'focus', 'route', 'waypoints']) {
            if (!map.getSource(id))
                map.addSource(id, {type: 'geojson', data: empty});
        }
        if (!map.getSource('alpr'))
            map.addSource('alpr', {type: 'geojson', data: 'data/alpr.geojson'});
        for (const layer of overlayLayers()) {
            if (!map.getLayer(layer.id))
                map.addLayer(layer);
        }
    }

    function bindMapEvents() {
        if (eventsBound)
            return;
        eventsBound = true;
        map.on('moveend', report);
        map.on('click', 'events', event => {
            const feature = event.features && event.features[0];
            if (!feature)
                return;
            const coords = feature.geometry.coordinates;
            pickFromFeature(feature, coords, feature.properties.kind || 'event');
        });
        map.on('mouseenter', 'events', () => { map.getCanvas().style.cursor = 'pointer'; });
        map.on('mouseleave', 'events', () => { map.getCanvas().style.cursor = ''; });
        map.on('click', 'alpr', event => {
            const feature = event.features && event.features[0];
            if (!feature)
                return;
            pickFromFeature(feature, feature.geometry.coordinates, 'cameras');
        });
        map.on('mouseenter', 'alpr', () => { map.getCanvas().style.cursor = 'pointer'; });
        map.on('mouseleave', 'alpr', () => { map.getCanvas().style.cursor = ''; });
    }

    let eventsBound = false;
    let remoteTried = false;

    function finishLoad() {
        map.setProjection({type: projection});
        paintSky();
        ensureOverlays();
        bindMapEvents();
        loaded = true;
        if (restored)
            window.restoreOsintView(restored);
        applyPoints();
        if (usingFallback)
            status.textContent = '3D GLOBE · LOCAL LAND · ' + collections().points.features.length + ' EVENTS';
        else
            report();
        if (!remoteTried)
            adoptRemoteStyle();
    }

    function adoptRemoteStyle() {
        remoteTried = true;
        fetch(remoteStyle)
            .then(response => {
                if (!response.ok)
                    throw new Error('style ' + response.status);
                return response.json();
            })
            .then(style => {
                if (!map)
                    return;
                usingFallback = false;
                map.setStyle(style, {diff: false});
                map.once('style.load', () => finishLoad());
            })
            .catch(() => {
                /* Stay on local land; remote tiles are optional. */
            });
    }

    function start(style, fallback) {
        if (map)
            map.remove();
        loaded = false;
        eventsBound = false;
        usingFallback = Boolean(fallback);
        retry.hidden = true;
        status.textContent = 'LOADING WORLD MAP…';
        try {
            map = new maplibregl.Map({
                container: 'map',
                style: style,
                ...home,
                minZoom: 0,
                maxZoom: 18,
                maxPitch: 75,
                fadeDuration: 0,
                pixelRatio: Math.min(window.devicePixelRatio || 1, 1.25),
                canvasContextAttributes: {powerPreference: 'low-power', failIfMajorPerformanceCaveat: false},
                attributionControl: {compact: true}
            });
            map.addControl(new maplibregl.NavigationControl({visualizePitch: true}), 'top-right');
            map.on('styleimagemissing', event => {
                if (!map.hasImage(event.id))
                    map.addImage(event.id, {width: 1, height: 1, data: new Uint8Array(4)});
            });
            map.once('load', () => finishLoad());
            map.on('error', event => {
                const message = String((event && event.error && event.error.message) || '');
                if (message && /webgl/i.test(message)) {
                    status.textContent = 'MAP COULD NOT START · WEBGL REQUIRED';
                    retry.hidden = false;
                }
            });
        } catch (error) {
            if (!fallback) {
                start(styleSpec(), true);
                return;
            }
            status.textContent = 'MAP COULD NOT START · WEBGL REQUIRED';
            retry.hidden = false;
        }
    }

    let lastPick = null;
    window.osintNavOpen = false;
    window.osintRouteMeta = '';
    window.osintGps = null;

    function pickFromFeature(feature, coords, kind) {
        const props = (feature && feature.properties) || {};
        lastPick = {
            id: String(props.id || props.label || coords.join(',')),
            kind: String(kind || props.kind || 'event'),
            title: String(props.label || props.brand || props.title || kind || 'Point'),
            summary: String(props.zone || props.kind || ''),
            source: String(kind || 'MAP').toUpperCase(),
            time: '',
            url: String(props.url || ''),
            lat: Number(coords[1]),
            lon: Number(coords[0])
        };
        window.osintNavOpen = false;
        window.focusOsintPoint({lat: lastPick.lat, lon: lastPick.lon, zoom: 7});
    }

    window.getOsintPick = () => lastPick;
    window.clearOsintPick = () => { lastPick = null; };

    window.focusOsintPoint = view => {
        if (!loaded || !view || !finite(Number(view.lat)) || !finite(Number(view.lon)))
            return;
        const lat = Number(view.lat);
        const lon = Number(view.lon);
        const zoom = finite(Number(view.zoom)) ? Number(view.zoom) : 5.2;
        map.flyTo({center: [lon, lat], zoom: zoom, speed: 0.85, essential: true});
        if (map.getSource('focus'))
            map.getSource('focus').setData({
                type: 'FeatureCollection',
                features: [{
                    type: 'Feature',
                    geometry: {type: 'Point', coordinates: [lon, lat]},
                    properties: {}
                }]
            });
    };

    function setRouteData(geometry, points) {
        if (!loaded)
            return;
        if (map.getSource('route'))
            map.getSource('route').setData(geometry
                ? {type: 'FeatureCollection', features: [{type: 'Feature', geometry, properties: {}}]}
                : empty);
        if (map.getSource('waypoints')) {
            const stops = Array.isArray(points) ? points : [];
            map.getSource('waypoints').setData({
                type: 'FeatureCollection',
                features: stops.filter(pair => pair && finite(pair[0]) && finite(pair[1])).map((pair, index) => ({
                    type: 'Feature',
                    geometry: {type: 'Point', coordinates: [pair[0], pair[1]]},
                    properties: {
                        role: index === 0 ? 'start' : (index === stops.length - 1 ? 'end' : 'via'),
                        index
                    }
                }))
            });
        }
    }

    function searchPlace(query) {
        const url = 'https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&q='
            + encodeURIComponent(query);
        return fetch(url, {headers: {'Accept': 'application/json'}}).then(response => response.json());
    }

    function resolvePlace(query, gps) {
        if (gps && (!query || /^gps$/i.test(query)))
            return Promise.resolve([Number(gps.lon), Number(gps.lat)]);
        return searchPlace(query).then(results => {
            const hit = results && results[0];
            if (!hit)
                throw new Error('not found');
            return [Number(hit.lon), Number(hit.lat)];
        });
    }

    window.setOsintRoute = payload => {
        if (!payload || !payload.ok || !payload.geometry) {
            setRouteData(null);
            window.osintRouteMeta = (payload && payload.error) || 'Routing unavailable.';
            return;
        }
        const points = (payload.points || []).map(point => [Number(point.lon), Number(point.lat)]);
        if (map.getSource('focus'))
            map.getSource('focus').setData(empty);
        setRouteData(payload.geometry, points);
        const km = (Number(payload.distance_m || 0) / 1000).toFixed(1);
        const min = Math.round(Number(payload.duration_s || 0) / 60);
        window.osintRouteMeta = km + ' km · ' + min + ' min · ' + points.length + ' places';
        const bounds = payload.geometry.coordinates || [];
        if (loaded && bounds.length)
            map.fitBounds(bounds.reduce((box, pair) => box.extend(pair),
                new maplibregl.LngLatBounds(bounds[0], bounds[0])), {padding: 48, maxZoom: 12});
    };

    window.planOsintRoute = spec => {
        const from = String((spec && spec.from) || '').trim();
        const to = String((spec && spec.to) || '').trim();
        const vias = Array.isArray(spec && spec.stops) ? spec.stops : [];
        const gps = spec && spec.gps;
        if (!to || (!from && !gps)) {
            window.osintRouteMeta = 'Write FROM, then TO, then ROUTE.';
            return;
        }
        window.osintRouteMeta = 'ROUTING…';
        const jobs = [resolvePlace(from, gps)];
        vias.forEach(stop => jobs.push(resolvePlace(String(stop || ''), null)));
        jobs.push(resolvePlace(to, null));
        Promise.all(jobs).then(points => {
            const path = points.map(pair => pair[0] + ',' + pair[1]).join(';');
            return fetch('https://router.project-osrm.org/route/v1/driving/' + path
                + '?overview=full&geometries=geojson').then(response => response.json())
                .then(payload => ({payload, points}));
        }).then(({payload, points}) => {
            const route = payload && payload.routes && payload.routes[0];
            if (!route || !route.geometry) {
                window.osintRouteMeta = 'No driving route for those places.';
                return;
            }
            setRouteData(route.geometry, points);
            const km = (route.distance / 1000).toFixed(1);
            const min = Math.round(route.duration / 60);
            window.osintRouteMeta = km + ' km · ' + min + ' min · ' + points.length + ' places';
            const bounds = route.geometry.coordinates;
            if (bounds.length)
                map.fitBounds(bounds.reduce((box, pair) => box.extend(pair),
                    new maplibregl.LngLatBounds(bounds[0], bounds[0])), {padding: 48, maxZoom: 12});
        }).catch(() => { window.osintRouteMeta = 'Place not found or routing unavailable.'; });
    };

    window.clearOsintRoute = () => {
        setRouteData(null);
        window.osintRouteMeta = '';
    };

    window.locateOsintGps = () => {
        if (!navigator.geolocation) {
            window.osintRouteMeta = 'Geolocation not available.';
            return;
        }
        window.osintRouteMeta = 'LOCATING…';
        navigator.geolocation.getCurrentPosition(position => {
            window.osintGps = {
                lat: position.coords.latitude,
                lon: position.coords.longitude
            };
            window.osintRouteMeta = 'GPS ready · use as FROM';
            window.focusOsintPoint({lat: window.osintGps.lat, lon: window.osintGps.lon, zoom: 11});
        }, () => { window.osintRouteMeta = 'GPS denied.'; },
        {enableHighAccuracy: true, timeout: 8000});
    };

    document.getElementById('nav').onclick = () => {
        window.osintNavOpen = !window.osintNavOpen;
        document.getElementById('nav').setAttribute('aria-pressed', String(window.osintNavOpen));
        if (window.osintNavOpen)
            setProjection('mercator');
    };

    document.getElementById('globe').onclick = () => setProjection('globe');
    document.getElementById('flat').onclick = () => setProjection('mercator');
    document.getElementById('reset').onclick = () => {
        setProjection('globe');
        if (map)
            map.flyTo(home);
    };
    retry.onclick = () => {
        remoteTried = false;
        start(styleSpec(), true);
    };
    window.addEventListener('keydown', event => {
        if (event.key.toLowerCase() === 'r' && !event.ctrlKey && !event.metaKey && !event.altKey)
            document.getElementById('reset').click();
    });
    new ResizeObserver(() => { if (map) map.resize(); }).observe(document.getElementById('map'));
    start(styleSpec(), true);
})();
