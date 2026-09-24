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
        conflicts: '#ff7a3d',
        cameras: '#6ec4d8'
    };
    const MAX_TRACKS = 2500;
    const TRACKS_MIN_ZOOM = 4.0;
    const home = {center: [18, 22], zoom: 1.65, bearing: 0, pitch: 0};
    const remoteStyle = 'https://tiles.openfreemap.org/styles/dark';
    let map, pending = [], catalogCounts = {}, restored = null, loaded = false, projection = 'globe';
    let lastRenderCount = 0;
    let moving = false;
    let conflictMarkers = [];
    let usingFallback = false;
    let lastMapError = '';
    window.osintMapReady = false;
    window.osintMapError = '';

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
        const showTracks = map && map.getZoom() >= TRACKS_MIN_ZOOM;
        for (const point of pending) {
            if (!validPoint(point))
                continue;
            const kind = String(point.kind || 'event');
            const feature = {
                type: 'Feature',
                geometry: {type: 'Point', coordinates: [point.lon, point.lat]},
                properties: {
                    id: String(point.id || point.callsign || point.label || ''),
                    kind,
                    label: String(point.label || point.callsign || kind),
                    callsign: String(point.callsign || ''),
                    country: String(point.country || ''),
                    color: colors[kind] || String(point.color || '#7fa9c4'),
                    heading: finite(Number(point.heading)) ? Number(point.heading) : null,
                    magnitude: finite(Number(point.magnitude)) ? Number(point.magnitude) : null,
                    alt_m: finite(Number(point.alt_m)) ? Number(point.alt_m) : null,
                    speed_mps: finite(Number(point.speed_mps)) ? Number(point.speed_mps) : null,
                    squawk: String(point.squawk || ''),
                    on_ground: Boolean(point.on_ground),
                    url: String(point.url || ''),
                    photo: String(point.photo || point.media_url || ''),
                    summary: String(point.summary || ''),
                    place: String(point.place || ''),
                    source: String(point.source || kind).toUpperCase(),
                    city: String(point.city || ''),
                    country: String(point.country || ''),
                    live_video: Boolean(point.live_video),
                    camera_count: finite(Number(point.camera_count)) ? Number(point.camera_count) : 0,
                    aircraft_count: finite(Number(point.aircraft_count)) ? Number(point.aircraft_count) : 0,
                    event_count: finite(Number(point.event_count)) ? Number(point.event_count) : 0,
                    cluster_count: finite(Number(point.cluster_count)) ? Number(point.cluster_count) : 0,
                    cluster: Boolean(point.cluster),
                    media_kind: String(point.media_kind || ''),
                    availability: String(point.availability || '')
                }
            };
            points.push(feature);
            if (kind === 'fires')
                fires.push(feature);
            if (kind === 'earthquakes')
                quakes.push(feature);
            if (kind === 'conflicts')
                conflicts.push(feature);
            if (showTracks && kind === 'aircraft' && !point.cluster
                && tracks.length < MAX_TRACKS && !point.on_ground
                && finite(Number(point.heading))) {
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
                    minzoom: 3,
                    paint: {
                        'circle-radius': ['interpolate', ['linear'], ['zoom'], 0, 6, 5, 11, 10, 16],
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
                        'circle-radius': ['interpolate', ['linear'], ['zoom'], 0, 5, 5, 9, 10, 14],
                        'circle-color': '#e0b15a',
                        'circle-opacity': 0.18
                    }
                },
                {
                    id: 'camera-pulse',
                    type: 'circle',
                    source: 'events',
                    minzoom: 5,
                    filter: ['all',
                        ['==', ['get', 'kind'], 'cameras'],
                        ['!=', ['get', 'cluster'], true]
                    ],
                    paint: {
                        'circle-radius': ['interpolate', ['linear'], ['zoom'], 0, 7, 6, 11, 12, 15],
                        'circle-color': '#6ec4d8',
                        'circle-opacity': 0.10
                    }
                },
                {
                    id: 'event-clusters',
                    type: 'circle',
                    source: 'events',
                    paint: {
                        'circle-radius': ['interpolate', ['linear'], ['get', 'cluster_count'], 2, 4.2, 25, 6, 200, 9, 1000, 13],
                        'circle-color': ['get', 'color'],
                        'circle-stroke-width': 1.4,
                        'circle-stroke-color': '#05070c',
                        'circle-opacity': 0.96
                    },
                    filter: ['==', ['get', 'cluster'], true]
                },
                {
                    id: 'events',
                    type: 'circle',
                    source: 'events',
                    paint: {
                        'circle-radius': ['interpolate', ['linear'], ['zoom'],
                            0, ['match', ['get', 'kind'], 'conflicts', 4.2, 'cameras', 3.4, 'fires', 3.2, 'earthquakes', 3.1, 2.3],
                            6, ['match', ['get', 'kind'], 'conflicts', 6.5, 'cameras', 5.4, 'fires', 5.2, 'earthquakes', 5, 3.6],
                            12, ['match', ['get', 'kind'], 'conflicts', 8, 'cameras', 7, 'fires', 7, 'earthquakes', 6.5, 5]
                        ],
                        'circle-color': ['get', 'color'],
                        'circle-stroke-width': 1.1,
                        'circle-stroke-color': '#05070c',
                        'circle-opacity': 0.92
                    },
                    filter: ['!=', ['get', 'cluster'], true]
                }
            ]
        };
    }

    function report() {
        if (!loaded)
            return;
        const count = lastRenderCount;
        let indexed = 0;
        for (const key of Object.keys(catalogCounts || {}))
            indexed += Number(catalogCounts[key] || 0);
        const mode = projection === 'globe' ? '3D GLOBE' : '2D MAP';
        const indexText = indexed > 0 ? ` · ${indexed.toLocaleString()} INDEXED` : '';
        status.textContent = `${mode} · ${count.toLocaleString()} BLIPS${indexText} · ZOOM ${map.getZoom().toFixed(1)}`;
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
        lastRenderCount = data.points.features.length;
        map.getSource('events').setData(data.points);
        map.getSource('tracks').setData(data.tracks);
        map.getSource('fires').setData(data.fires);
        map.getSource('quakes').setData(data.quakes);
        syncConflicts(data.conflicts.features);
        if (currentPopup && lastPick && finite(Number(lastPick.lat)) && finite(Number(lastPick.lon))) {
            const hit = pending.find(point => validPoint(point)
                && String(point.id || point.callsign || '') === String(lastPick.id || lastPick.callsign || ''));
            if (hit) {
                lastPick.lat = Number(hit.lat);
                lastPick.lon = Number(hit.lon);
                currentPopup.setLngLat([hit.lon, hit.lat]);
            }
        }
        report();
    }

    window.setOsintPoints = (points, counts) => {
        pending = Array.isArray(points) ? points : [];
        catalogCounts = counts && typeof counts === 'object' ? counts : {};
        // A 10k-feature source update must never compete with a pan/zoom
        // frame.  Keep the newest snapshot and commit it on moveend.
        if (!moving)
            applyPoints();
    };
    window.getOsintView = () => loaded ? {
        lng: map.getCenter().lng,
        lat: map.getCenter().lat,
        zoom: map.getZoom(),
        bearing: map.getBearing(),
        pitch: map.getPitch(),
        bounds: map.getBounds().toArray(),
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
        const globeBtn = document.getElementById('globe');
        const flatBtn = document.getElementById('flat');
        if (globeBtn)
            globeBtn.setAttribute('aria-pressed', String(value === 'globe'));
        if (flatBtn)
            flatBtn.setAttribute('aria-pressed', String(value === 'mercator'));
        report();
    }
    window.setOsintProjection = setProjection;
    window.resetOsintView = () => {
        setProjection('globe');
        if (map)
            map.flyTo(home);
    };

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
                minzoom: 7,
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
                id: 'camera-pulse',
                type: 'circle',
                source: 'events',
                minzoom: 5,
                filter: ['all',
                    ['==', ['get', 'kind'], 'cameras'],
                    ['!=', ['get', 'cluster'], true]
                ],
                paint: {
                    'circle-radius': ['interpolate', ['linear'], ['zoom'], 0, 7, 6, 11, 12, 15],
                    'circle-color': '#6ec4d8',
                    'circle-opacity': 0.10
                }
            },
            {
                id: 'event-clusters',
                type: 'circle',
                source: 'events',
                paint: {
                    'circle-radius': ['interpolate', ['linear'], ['get', 'cluster_count'], 2, 4.2, 25, 6, 200, 9, 1000, 13],
                    'circle-color': ['get', 'color'],
                    'circle-stroke-width': 1.4,
                    'circle-stroke-color': '#05070c',
                    'circle-opacity': 0.96
                },
                filter: ['==', ['get', 'cluster'], true]
            },
            {
                id: 'events',
                type: 'circle',
                source: 'events',
                paint: {
                    'circle-radius': ['interpolate', ['linear'], ['zoom'],
                        0, ['match', ['get', 'kind'], 'conflicts', 4.2, 'cameras', 3.4, 'fires', 3.2, 'earthquakes', 3.1, 2.3],
                        6, ['match', ['get', 'kind'], 'conflicts', 6.5, 'cameras', 5.4, 'fires', 5.2, 'earthquakes', 5, 3.6],
                        12, ['match', ['get', 'kind'], 'conflicts', 8, 'cameras', 7, 'fires', 7, 'earthquakes', 6.5, 5]
                    ],
                    'circle-color': ['get', 'color'],
                    'circle-stroke-width': 1.1,
                    'circle-stroke-color': '#05070c',
                    'circle-opacity': 0.92
                },
                filter: ['!=', ['get', 'cluster'], true]
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
        map.on('movestart', () => { moving = true; });
        map.on('moveend', () => {
            moving = false;
            applyPoints();
            report();
        });
        const pickEventLayer = event => {
            const feature = event.features && event.features[0];
            if (!feature)
                return;
            const coords = feature.geometry.coordinates;
            pickFromFeature(feature, coords, feature.properties.kind || 'event');
        };
        for (const layer of ['events', 'event-clusters']) {
            map.on('click', layer, pickEventLayer);
            map.on('mouseenter', layer, () => { map.getCanvas().style.cursor = 'pointer'; });
            map.on('mouseleave', layer, () => { map.getCanvas().style.cursor = ''; });
        }
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
        lastMapError = '';
        window.osintMapError = '';
        window.osintMapReady = true;
        if (restored)
            window.restoreOsintView(restored);
        applyPoints();
        if (window.osintRoutePayload && window.osintRoutePayload.ok) {
            const points = (window.osintRoutePayload.points || []).map(lonLat);
            setRouteData(window.osintRoutePayload.geometry, points);
        }
        if (lastPick)
            showPopup(lastPick);
        if (usingFallback)
            status.textContent = '3D GLOBE · LOCAL LAND · ' + lastRenderCount.toLocaleString() + ' BLIPS';
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

    function mapErrorMessage(error) {
        const raw = error && error.error
            ? (error.error.message || error.error.toString())
            : (error && error.message) || error;
        return String(raw || 'unknown map error').replace(/\s+/g, ' ').trim().slice(0, 180);
    }

    function showMapError(error) {
        lastMapError = mapErrorMessage(error);
        window.osintMapReady = false;
        window.osintMapError = lastMapError;
        if (!loaded) {
            status.textContent = 'MAP ERROR · ' + lastMapError;
            retry.hidden = false;
        }
    }

    function start(style, fallback) {
        if (map)
            map.remove();
        loaded = false;
        eventsBound = false;
        moving = false;
        usingFallback = Boolean(fallback);
        lastMapError = '';
        window.osintMapReady = false;
        window.osintMapError = '';
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
                pixelRatio: 1,
                canvasContextAttributes: {powerPreference: 'low-power', failIfMajorPerformanceCaveat: false},
                attributionControl: false
            });
            map.addControl(new maplibregl.NavigationControl({visualizePitch: true, showCompass: false}), 'top-right');
            map.on('styleimagemissing', event => {
                if (!map.hasImage(event.id))
                    map.addImage(event.id, {width: 1, height: 1, data: new Uint8Array(4)});
            });
            map.once('load', () => {
                try {
                    finishLoad();
                } catch (error) {
                    showMapError(error);
                }
            });
            map.on('error', event => {
                const message = mapErrorMessage(event);
                if (!message)
                    return;
                lastMapError = message;
                if (/webgl/i.test(message)) {
                    status.textContent = 'MAP COULD NOT START · WEBGL REQUIRED';
                    retry.hidden = false;
                } else if (!loaded) {
                    status.textContent = 'MAP ERROR · ' + message;
                    retry.hidden = false;
                }
            });
        } catch (error) {
            if (!fallback) {
                start(styleSpec(), true);
                return;
            }
            showMapError(error);
        }
    }

    let lastPick = null;
    let lastPickSeq = 0;
    let currentPopup = null;
    window.osintNavOpen = false;
    window.osintRouteMeta = '';
    window.osintRoutePayload = null;
    window.osintGps = null;

    function esc(value) {
        return String(value == null ? '' : value).replace(/[&<>"']/g, ch => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
        }[ch]));
    }

    function knots(mps) {
        const n = Number(mps);
        return finite(n) ? Math.round(n * 1.94384) : null;
    }

    function flightLevel(meters) {
        const n = Number(meters);
        return finite(n) && n > 0 ? Math.round(n / 30.48) : null;
    }

    function popupHtml(pick) {
        const kind = String(pick.kind || 'event').toUpperCase();
        const title = esc(pick.title || pick.callsign || pick.label || kind);
        const lines = [];
        if (pick.kind === 'aircraft') {
            const count = Number(pick.aircraft_count || pick.cluster_count || 0);
            if (count > 1) {
                lines.push(count.toLocaleString() + ' INDEXED AIRCRAFT');
            } else {
                const fl = flightLevel(pick.alt_m);
                const kt = knots(pick.speed_mps);
                const bits = [];
                if (fl) bits.push('FL ' + fl);
                if (kt) bits.push(kt + ' kt');
                if (finite(Number(pick.heading))) bits.push('HDG ' + Math.round(Number(pick.heading)));
                if (bits.length) lines.push(bits.join(' · '));
                if (pick.country) lines.push(esc(pick.country));
                if (pick.route) lines.push(esc(pick.route));
            }
        } else if (pick.kind === 'earthquakes') {
            if (finite(Number(pick.magnitude)))
                lines.push('M' + Number(pick.magnitude).toFixed(1));
            if (pick.place || pick.summary) lines.push(esc(pick.place || pick.summary));
        } else if (pick.kind === 'fires') {
            if (pick.summary) lines.push(esc(pick.summary));
        } else if (pick.kind === 'cameras') {
            if (pick.source) lines.push(esc(String(pick.source).toUpperCase()));
            if (finite(Number(pick.camera_count)) && Number(pick.camera_count) > 1)
                lines.push(Number(pick.camera_count).toLocaleString() + ' INDEXED CAMERAS');
            if (pick.media_kind) lines.push(esc(String(pick.media_kind).replaceAll('_', ' ')));
            if (pick.city || pick.country)
                lines.push(esc([pick.city, pick.country].filter(Boolean).join(' · ')));
            else if (pick.summary) lines.push(esc(pick.summary));
            if (!(pick.photo || pick.media_url))
                lines.push('NO LIVE SNAPSHOT');
        } else if (Number(pick.event_count || pick.cluster_count || 0) > 1) {
            lines.push(Number(pick.event_count || pick.cluster_count).toLocaleString() + ' INDEXED EVENTS');
            if (pick.summary) lines.push(esc(pick.summary));
        } else if (pick.summary) {
            lines.push(esc(pick.summary));
        }
        const media = pick.photo || pick.media_url;
        const img = media
            ? '<img class="gg-pop-media" alt="" src="' + esc(media) + '">'
            : '';
        return '<div class="gg-pop">'
            + '<div class="gg-pop-legend">' + title + '</div>'
            + '<div class="gg-pop-k">' + esc(kind) + '</div>'
            + lines.map(line => '<div class="gg-pop-f">' + line + '</div>').join('')
            + img
            + '</div>';
    }

    function showPopup(pick) {
        if (!loaded || !pick || !finite(Number(pick.lat)) || !finite(Number(pick.lon)))
            return;
        if (currentPopup)
            currentPopup.remove();
        currentPopup = new maplibregl.Popup({
            closeButton: true,
            closeOnClick: false,
            maxWidth: '260px',
            offset: 14,
            className: 'gg-osint-popup'
        })
            .setLngLat([Number(pick.lon), Number(pick.lat)])
            .setHTML(popupHtml(pick))
            .addTo(map);
        currentPopup.on('close', () => {
            if (currentPopup)
                currentPopup = null;
        });
    }

    function pickFromFeature(feature, coords, kind) {
        const props = (feature && feature.properties) || {};
        lastPick = {
            id: String(props.id || props.osm || props.callsign || props.label || coords.join(',')),
            kind: String(kind || props.kind || 'event'),
            title: String(props.label || props.callsign || props.brand || props.title || kind || 'Point'),
            callsign: String(props.callsign || props.label || ''),
            country: String(props.country || ''),
            summary: String(props.summary || props.zone || props.place || ''),
            source: String(props.source || kind || 'MAP').toUpperCase(),
            time: '',
            url: String(props.url || ''),
            photo: String(props.photo || ''),
            city: String(props.city || ''),
            live_video: props.live_video === true || props.live_video === 'true',
            camera_count: finite(Number(props.camera_count)) ? Number(props.camera_count) : 0,
            media_kind: String(props.media_kind || ''),
            availability: String(props.availability || ''),
            aircraft_count: finite(Number(props.aircraft_count)) ? Number(props.aircraft_count) : 0,
            event_count: finite(Number(props.event_count)) ? Number(props.event_count) : 0,
            cluster_count: finite(Number(props.cluster_count)) ? Number(props.cluster_count) : 0,
            cluster: props.cluster === true || props.cluster === 'true',
            lat: Number(coords[1]),
            lon: Number(coords[0]),
            alt_m: finite(Number(props.alt_m)) ? Number(props.alt_m) : null,
            speed_mps: finite(Number(props.speed_mps)) ? Number(props.speed_mps) : null,
            heading: finite(Number(props.heading)) ? Number(props.heading) : null,
            squawk: String(props.squawk || ''),
            on_ground: props.on_ground === true || props.on_ground === 'true',
            magnitude: finite(Number(props.magnitude)) ? Number(props.magnitude) : null,
            place: String(props.place || '')
        };
        lastPickSeq += 1;
        showPopup(lastPick);
    }

    window.getOsintPick = () => lastPick;
    window.takeOsintPick = () => lastPick
        ? Object.assign({seq: lastPickSeq}, lastPick)
        : null;
    window.clearOsintPick = () => { lastPick = null; };
    window.showOsintPopup = pick => {
        if (!pick)
            return;
        lastPick = {
            id: String(pick.id || pick.callsign || pick.title || ''),
            kind: String(pick.kind || 'event'),
            title: String(pick.title || pick.callsign || pick.label || pick.kind || 'Point'),
            callsign: String(pick.callsign || pick.title || ''),
            country: String(pick.country || ''),
            summary: String(pick.summary || ''),
            source: String(pick.source || pick.kind || 'MAP').toUpperCase(),
            time: String(pick.time || ''),
            url: String(pick.url || ''),
            photo: String(pick.photo || pick.media_url || ''),
            city: String(pick.city || ''),
            live_video: Boolean(pick.live_video),
            camera_count: finite(Number(pick.camera_count)) ? Number(pick.camera_count) : 0,
            media_kind: String(pick.media_kind || ''),
            availability: String(pick.availability || ''),
            aircraft_count: finite(Number(pick.aircraft_count)) ? Number(pick.aircraft_count) : 0,
            event_count: finite(Number(pick.event_count)) ? Number(pick.event_count) : 0,
            cluster_count: finite(Number(pick.cluster_count)) ? Number(pick.cluster_count) : 0,
            cluster: Boolean(pick.cluster),
            lat: Number(pick.lat),
            lon: Number(pick.lon),
            alt_m: finite(Number(pick.alt_m)) ? Number(pick.alt_m) : null,
            speed_mps: finite(Number(pick.speed_mps)) ? Number(pick.speed_mps) : null,
            heading: finite(Number(pick.heading)) ? Number(pick.heading) : null,
            squawk: String(pick.squawk || ''),
            on_ground: Boolean(pick.on_ground),
            magnitude: finite(Number(pick.magnitude)) ? Number(pick.magnitude) : null,
            place: String(pick.place || ''),
            route: String(pick.route || '')
        };
        showPopup(lastPick);
    };

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

    function lonLat(point) {
        if (Array.isArray(point))
            return [Number(point[0]), Number(point[1])];
        if (!point)
            return [NaN, NaN];
        return [Number(point.lon), Number(point.lat)];
    }

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
        window.osintRoutePayload = payload && payload.ok ? payload : null;
        if (!payload || !payload.ok || !payload.geometry) {
            setRouteData(null);
            window.osintRouteMeta = (payload && payload.error) || 'Routing unavailable.';
            return;
        }
        const points = (payload.points || []).map(lonLat);
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
            const built = {
                ok: true,
                geometry: route.geometry,
                points: points.map(pair => ({lon: pair[0], lat: pair[1]})),
                distance_m: route.distance,
                duration_s: route.duration
            };
            window.osintRoutePayload = built;
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
        window.osintRoutePayload = null;
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
