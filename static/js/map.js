document.addEventListener('DOMContentLoaded', () => {
  const ROUTE_PLAN_URL = '/api/v1/route-plan/';
  const US_CENTER = [-98.5795, 39.8283];

  const STYLES = {
    liberty: 'https://tiles.openfreemap.org/styles/liberty',
    positron: 'https://tiles.openfreemap.org/styles/positron',
    bright: 'https://tiles.openfreemap.org/styles/bright',
    dark: 'https://tiles.openfreemap.org/styles/dark',
  };

  const ROUTE_COLOR = '#4f46e5';
  const CASING_COLOR = 'rgba(49, 46, 129, 0.35)';
  const FLOW_COLOR = '#ffffff';
  const TRANSPARENT = 'rgba(0, 0, 0, 0)';

  const DASH_SEQUENCE = [
    [0, 4, 3], [0.5, 4, 2.5], [1, 4, 2], [1.5, 4, 1.5],
    [2, 4, 1], [2.5, 4, 0.5], [3, 4, 0], [0, 0.5, 3, 3.5],
    [0, 1, 3, 3], [0, 1.5, 3, 2.5], [0, 2, 3, 2], [0, 2.5, 3, 1.5],
    [0, 3, 3, 1], [0, 3.5, 3, 0.5],
  ];

  const form = document.getElementById('route-form');
  const submitButton = document.getElementById('submit-button');
  const statusEl = document.getElementById('status');
  const summaryEl = document.getElementById('summary');
  const stopsList = document.getElementById('stops-list');
  const styleSwitcher = document.getElementById('map-styles');

  const map = new maplibregl.Map({
    container: 'map',
    style: STYLES.liberty,
    center: US_CENTER,
    zoom: 3.4,
    attributionControl: false,
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
  map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right');

  let markers = [];
  let lastResult = null;
  let drawFrame = null;
  let flowFrame = null;

  let resolveReady;
  const mapReady = new Promise((resolve) => { resolveReady = resolve; });

  map.on('style.load', () => {
    addRouteLayers();
    if (lastResult) {
      setRouteData(toLngLat(lastResult));
      animateRoute();
    }
    resolveReady();
  });

  function addRouteLayers() {
    if (map.getSource('route')) return;
    map.addSource('route', {
      type: 'geojson',
      lineMetrics: true,
      data: { type: 'FeatureCollection', features: [] },
    });
    map.addLayer({
      id: 'route-casing',
      type: 'line',
      source: 'route',
      layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: { 'line-color': CASING_COLOR, 'line-width': lineWidth(7, 11) },
    });
    map.addLayer({
      id: 'route-line',
      type: 'line',
      source: 'route',
      layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: { 'line-color': ROUTE_COLOR, 'line-width': lineWidth(3, 6) },
    });
    map.addLayer({
      id: 'route-flow',
      type: 'line',
      source: 'route',
      layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: {
        'line-color': FLOW_COLOR,
        'line-width': lineWidth(1.5, 3),
        'line-opacity': 0,
        'line-dasharray': [0, 4, 3],
      },
    });
  }

  function lineWidth(base, top) {
    return ['interpolate', ['linear'], ['zoom'], 4, base, 10, (base + top) / 2, 14, top];
  }

  styleSwitcher.addEventListener('click', (event) => {
    const button = event.target.closest('.map-styles__btn');
    if (!button || button.classList.contains('is-active')) return;

    styleSwitcher.querySelectorAll('.map-styles__btn').forEach((btn) => {
      btn.classList.toggle('is-active', btn === button);
    });

    cancelAnimations();
    map.setStyle(STYLES[button.dataset.style]);
  });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();

    const startLocation = document.getElementById('start_location').value.trim();
    const finishLocation = document.getElementById('finish_location').value.trim();

    setLoading(true);
    setStatus('Planning your route…');
    summaryEl.classList.add('hidden');

    try {
      const response = await fetch(ROUTE_PLAN_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          start_location: startLocation,
          finish_location: finishLocation,
        }),
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || 'Unable to plan this route.');
      }

      await mapReady;
      renderResult(data);
      setStatus('');
    } catch (error) {
      setStatus(error.message, true);
    } finally {
      setLoading(false);
    }
  });

  function renderResult(data) {
    lastResult = data;
    const lngLatRoute = toLngLat(data);

    setRouteData(lngLatRoute);

    clearMarkers();
    addPinMarker(lngLatRoute[0], 'start', 'Start', data.start_location);
    addPinMarker(lngLatRoute[lngLatRoute.length - 1], 'finish', 'Finish', data.finish_location);
    data.fuel_stops.forEach((stop, index) => addStopMarker(stop, index + 1));
    addRouteBadge(lngLatRoute, data);

    fitToRoute(lngLatRoute);
    renderSummary(data);
    animateRoute();
  }

  function toLngLat(data) {
    return data.route_geometry.map(([lat, lon]) => [lon, lat]);
  }

  function setRouteData(lngLatRoute) {
    map.getSource('route').setData({
      type: 'Feature',
      geometry: { type: 'LineString', coordinates: lngLatRoute },
    });
  }

  function animateRoute() {
    cancelAnimations();
    const duration = 1100;
    const start = performance.now();
    map.setPaintProperty('route-flow', 'line-opacity', 0);

    const step = (now) => {
      const t = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - t, 3);
      map.setPaintProperty('route-line', 'line-gradient',
        ['step', ['line-progress'], ROUTE_COLOR, eased, TRANSPARENT]);
      map.setPaintProperty('route-casing', 'line-gradient',
        ['step', ['line-progress'], CASING_COLOR, eased, TRANSPARENT]);

      if (t < 1) {
        drawFrame = requestAnimationFrame(step);
      } else {
        drawFrame = null;
        startFlow();
      }
    };
    drawFrame = requestAnimationFrame(step);
  }

  function startFlow() {
    map.setPaintProperty('route-flow', 'line-opacity', 0.9);
    let current = 0;
    const tick = (timestamp) => {
      const next = Math.floor((timestamp / 55) % DASH_SEQUENCE.length);
      if (next !== current) {
        map.setPaintProperty('route-flow', 'line-dasharray', DASH_SEQUENCE[current]);
        current = next;
      }
      flowFrame = requestAnimationFrame(tick);
    };
    flowFrame = requestAnimationFrame(tick);
  }

  function cancelAnimations() {
    if (drawFrame) cancelAnimationFrame(drawFrame);
    if (flowFrame) cancelAnimationFrame(flowFrame);
    drawFrame = null;
    flowFrame = null;
  }

  function renderSummary(data) {
    document.getElementById('summary-distance').textContent =
      `${formatNumber(data.total_distance_miles)} mi`;
    document.getElementById('summary-cost').textContent =
      `$${formatNumber(data.total_fuel_cost)}`;
    document.getElementById('summary-assumptions').textContent =
      `${data.vehicle_range_miles} mi range · ${data.miles_per_gallon} MPG`;

    stopsList.innerHTML = '';
    if (data.fuel_stops.length === 0) {
      const empty = document.createElement('li');
      empty.className = 'stop--empty';
      empty.textContent = 'No fuel stops needed — the destination is within range.';
      stopsList.appendChild(empty);
    } else {
      data.fuel_stops.forEach((stop) => stopsList.appendChild(buildStopItem(stop)));
    }

    summaryEl.classList.remove('hidden');
  }

  function buildStopItem(stop) {
    const item = document.createElement('li');

    const name = document.createElement('div');
    name.className = 'stop__name';
    name.textContent = stop.name;

    const meta = document.createElement('div');
    meta.className = 'stop__meta';
    meta.textContent =
      `${stop.city}, ${stop.state} · mile ${formatNumber(stop.distance_from_start_miles)}`;

    const chip = document.createElement('span');
    chip.className = 'stop__chip';
    chip.textContent =
      `${stop.gallons_purchased} gal @ $${stop.price_per_gallon} = $${stop.cost}`;

    item.append(name, meta, chip);
    return item;
  }

  function addPinMarker(lngLat, kind, label, place) {
    const el = document.createElement('div');
    el.className = `pin pin--${kind}`;

    const html =
      `<div class="popup popup--${kind}">`
      + `<span class="popup__eyebrow popup__eyebrow--${kind}">${label}</span>`
      + `<div class="popup__title">${escapeHtml(place)}</div>`
      + '</div>';

    addMarkerWithPopup(el, lngLat, html, { offset: 18, anchor: 'bottom' });
  }

  function addStopMarker(stop, position) {
    const el = document.createElement('div');
    el.className = 'pin pin--stop';
    el.textContent = position;

    const html =
      `<div class="popup popup--stop">`
      + `<span class="popup__eyebrow popup__eyebrow--stop">Fuel stop ${position}</span>`
      + `<div class="popup__title">${escapeHtml(stop.name)}</div>`
      + `<div class="popup__place">${escapeHtml(stop.city)}, ${escapeHtml(stop.state)}</div>`
      + '<dl class="popup__rows">'
      + popupRow('Mile marker', `${formatNumber(stop.distance_from_start_miles)} mi`)
      + popupRow('Price', `$${stop.price_per_gallon}/gal`)
      + popupRow('Fuel to buy', `${stop.gallons_purchased} gal`)
      + popupRow('Cost', `$${stop.cost}`, 'popup__row--total')
      + '</dl></div>';

    addMarkerWithPopup(el, [stop.longitude, stop.latitude], html, { offset: 16 });
  }

  function addMarkerWithPopup(element, lngLat, html, options) {
    const popup = new maplibregl.Popup({ className: 'route-popup', maxWidth: '260px', ...options })
      .setHTML(html);
    const marker = new maplibregl.Marker({ element, anchor: options.anchor })
      .setLngLat(lngLat)
      .setPopup(popup)
      .addTo(map);

    element.addEventListener('click', () => setTimeout(() => closeOtherPopups(popup), 0));
    markers.push(marker);
  }

  function closeOtherPopups(keep) {
    markers.forEach((marker) => {
      const popup = marker.getPopup();
      if (popup && popup !== keep && popup.isOpen()) popup.remove();
    });
  }

  function addRouteBadge(lngLatRoute, data) {
    const midpoint = lngLatRoute[Math.floor(lngLatRoute.length / 2)];
    const el = document.createElement('div');
    el.className = 'route-badge';
    el.innerHTML =
      `<strong>${formatNumber(data.total_distance_miles)} mi</strong>`
      + `<span>$${formatNumber(data.total_fuel_cost)} fuel · ${data.fuel_stops.length} stop`
      + `${data.fuel_stops.length === 1 ? '' : 's'}</span>`;
    markers.push(new maplibregl.Marker({ element: el }).setLngLat(midpoint).addTo(map));
  }

  function clearMarkers() {
    markers.forEach((marker) => marker.remove());
    markers = [];
  }

  function fitToRoute(lngLatRoute) {
    const bounds = lngLatRoute.reduce(
      (acc, coord) => acc.extend(coord),
      new maplibregl.LngLatBounds(lngLatRoute[0], lngLatRoute[0]),
    );
    const isMobile = window.matchMedia('(max-width: 640px)').matches;
    const padding = isMobile
      ? { top: 60, bottom: window.innerHeight * 0.55, left: 40, right: 40 }
      : { top: 60, bottom: 60, left: 420, right: 60 };
    map.fitBounds(bounds, { padding, duration: 900 });
  }

  function setLoading(isLoading) {
    submitButton.disabled = isLoading;
    submitButton.classList.toggle('is-loading', isLoading);
    submitButton.querySelector('.btn-primary__label').textContent =
      isLoading ? 'Planning…' : 'Plan route';
  }

  function setStatus(message, isError = false) {
    statusEl.textContent = message;
    statusEl.classList.toggle('error', isError);
  }

  function formatNumber(value) {
    return Number(value).toLocaleString('en-US', { maximumFractionDigits: 2 });
  }

  function popupRow(label, value, modifier = '') {
    return `<div class="popup__row ${modifier}"><dt>${label}</dt><dd>${value}</dd></div>`;
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (char) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[char]));
  }
});
