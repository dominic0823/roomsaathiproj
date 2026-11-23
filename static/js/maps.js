document.addEventListener("DOMContentLoaded", function () {
  if (typeof L === "undefined") return;

  const TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
  const ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
  const INDIA = [22.9, 79.0];

  function baseMap(el, center, zoom) {
    const map = L.map(el).setView(center, zoom);
    L.tileLayer(TILES, { maxZoom: 19, attribution: ATTR }).addTo(map);
    return map;
  }

  const detail = document.getElementById("detail-map");
  if (detail) {
    const pos = [parseFloat(detail.dataset.lat), parseFloat(detail.dataset.lng)];
    const map = baseMap(detail, pos, 15);
    L.marker(pos).addTo(map).bindPopup(document.createTextNode(detail.dataset.title).textContent);
  }

  const listMap = document.getElementById("list-map");
  const toggle = document.getElementById("toggle-map");
  const pointsEl = document.getElementById("map-points");
  if (listMap && toggle && pointsEl) {
    let map = null;
    toggle.addEventListener("click", function () {
      listMap.hidden = !listMap.hidden;
      toggle.textContent = listMap.hidden ? "\u{1F5FA} Show map" : "\u{1F5FA} Hide map";
      if (listMap.hidden || map) return;
      const points = JSON.parse(pointsEl.textContent);
      map = baseMap(listMap, [points[0].lat, points[0].lng], 12);
      const bounds = [];
      points.forEach(function (p) {
        const box = document.createElement("div");
        const link = document.createElement("a");
        link.href = p.url; link.textContent = p.title;
        const line = document.createElement("div");
        line.textContent = "₹" + Math.round(parseFloat(p.price)) + "/month" + (p.location ? " · " + p.location : "");
        box.appendChild(link); box.appendChild(line);
        L.marker([p.lat, p.lng]).addTo(map).bindPopup(box);
        bounds.push([p.lat, p.lng]);
      });
      if (bounds.length > 1) map.fitBounds(bounds, { padding: [30, 30] });
    });
  }

  const picker = document.getElementById("picker-map");
  if (picker) {
    const latInput = document.getElementById(picker.dataset.latInput);
    const lngInput = document.getElementById(picker.dataset.lngInput);
    const hasPin = latInput.value && lngInput.value;
    const start = hasPin ? [parseFloat(latInput.value), parseFloat(lngInput.value)] : INDIA;
    const map = baseMap(picker, start, hasPin ? 15 : 5);
    let marker = null;

    function setPin(lat, lng, zoom) {
      latInput.value = lat.toFixed(6);
      lngInput.value = lng.toFixed(6);
      if (marker) marker.setLatLng([lat, lng]); else {
        marker = L.marker([lat, lng], { draggable: true }).addTo(map);
        marker.on("dragend", function () { const p = marker.getLatLng(); setPin(p.lat, p.lng); });
      }
      if (zoom) map.setView([lat, lng], zoom);
    }
    if (hasPin) setPin(start[0], start[1]);
    map.on("click", function (e) { setPin(e.latlng.lat, e.latlng.lng); });

    document.getElementById("map-clear-btn").addEventListener("click", function () {
      latInput.value = ""; lngInput.value = "";
      if (marker) { map.removeLayer(marker); marker = null; }
    });

    document.getElementById("map-locate-btn").addEventListener("click", function () {
      if (!navigator.geolocation) return alert("Location isn't available in this browser.");
      navigator.geolocation.getCurrentPosition(
        function (pos) { setPin(pos.coords.latitude, pos.coords.longitude, 16); },
        function () { alert("Couldn't get your location. Search for the area instead."); }
      );
    });

    const searchInput = document.getElementById("map-search");
    function search() {
      const q = searchInput.value.trim();
      if (!q) return;
      fetch("https://nominatim.openstreetmap.org/search?format=json&limit=1&countrycodes=in&q=" + encodeURIComponent(q))
        .then(function (r) { return r.json(); })
        .then(function (res) {
          if (!res.length) return alert("Couldn't find that place. Try a nearby landmark.");
          map.setView([parseFloat(res[0].lat), parseFloat(res[0].lon)], 15);
        })
        .catch(function () { alert("Search failed. You can still click on the map to drop a pin."); });
    }
    document.getElementById("map-search-btn").addEventListener("click", search);
    searchInput.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); search(); } });
  }
});
