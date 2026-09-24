(function () {
    "use strict";

    const daNangCenter = [16.0544, 108.2022];
    const daNangBoundsCoordinates = [
        [15.85, 107.75],
        [16.25, 108.35],
    ];
    const osmAttribution =
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>';
    const mapTilerAttribution =
        '<a href="https://www.maptiler.com/copyright/">&copy; MapTiler</a> ' +
        osmAttribution;

    function isWithinDaNang(latitude, longitude) {
        return (
            latitude >= daNangBoundsCoordinates[0][0] &&
            latitude <= daNangBoundsCoordinates[1][0] &&
            longitude >= daNangBoundsCoordinates[0][1] &&
            longitude <= daNangBoundsCoordinates[1][1]
        );
    }

    function getTileProviders(element) {
        const apiKey = (element.dataset.maptilerKey || "").trim();
        const providers = [];
        if (apiKey) {
            providers.push({
                name: "Bản đồ PawRescue",
                url: `https://api.maptiler.com/maps/streets-v4/{z}/{x}/{y}.png?key=${encodeURIComponent(apiKey)}`,
                options: {
                    attribution: mapTilerAttribution,
                    crossOrigin: true,
                    maxZoom: 20,
                    tileSize: 512,
                    zoomOffset: -1,
                },
            });
        }
        providers.push({
            name: apiKey ? "OpenStreetMap dự phòng" : "OpenStreetMap",
            url: "https://tile.openstreetmap.de/{z}/{x}/{y}.png",
            options: {
                attribution: osmAttribution,
                maxZoom: 19,
                referrerPolicy: "strict-origin-when-cross-origin",
            },
        });
        return providers;
    }

    function createPinIcon() {
        return L.divIcon({
            className: "rescue-map-marker",
            html: '<span aria-hidden="true"><i></i></span>',
            iconSize: [36, 44],
            iconAnchor: [18, 42],
            popupAnchor: [0, -38],
        });
    }

    function createMap(element, center, zoom) {
        const daNangBounds = L.latLngBounds(daNangBoundsCoordinates);
        const initialCenter = daNangBounds.contains(center) ? center : daNangCenter;
        const map = L.map(element, {
            scrollWheelZoom: true,
            maxBounds: daNangBounds,
            maxBoundsViscosity: 1,
            minZoom: 10,
        }).setView(initialCenter, Math.max(zoom, 10));
        const loadState = document.createElement("div");
        loadState.className = "map-load-state is-loading";
        loadState.setAttribute("role", "status");
        loadState.setAttribute("aria-live", "polite");
        loadState.textContent = "Đang tải bản đồ...";
        element.appendChild(loadState);

        const tileProviders = getTileProviders(element);
        const layersByName = {};
        const layers = tileProviders.map(function (provider) {
            const layer = L.tileLayer(provider.url, provider.options);
            layersByName[provider.name] = layer;
            return layer;
        });
        let activeLayer = layers[0];
        let activeLayerIndex = 0;
        let tileErrors = 0;

        function showLoadState(message, mode) {
            loadState.textContent = message;
            loadState.className = `map-load-state ${mode || ""}`.trim();
        }

        layers.forEach(function (layer) {
            layer.on("loading", function () {
                if (layer === activeLayer) showLoadState("Đang tải bản đồ...", "is-loading");
            });
            layer.on("load", function () {
                if (layer !== activeLayer) return;
                tileErrors = 0;
                loadState.classList.add("is-hidden");
            });
            layer.on("tileerror", function () {
                if (layer !== activeLayer) return;
                tileErrors += 1;
                if (tileErrors < 3) return;

                if (activeLayerIndex + 1 < layers.length) {
                    tileErrors = 0;
                    map.removeLayer(activeLayer);
                    activeLayerIndex += 1;
                    activeLayer = layers[activeLayerIndex];
                    activeLayer.addTo(map);
                    showLoadState("Đang chuyển sang OpenStreetMap dự phòng...", "is-loading");
                    return;
                }
                showLoadState("Không thể tải nền bản đồ. Hãy kiểm tra kết nối mạng rồi tải lại trang.", "is-error");
            });
        });

        activeLayer.addTo(map);
        if (layers.length > 1) {
            L.control.layers(layersByName, null, {
                position: "topright",
                collapsed: false,
            }).addTo(map);
            map.on("baselayerchange", function (event) {
                activeLayer = event.layer;
                activeLayerIndex = layers.indexOf(event.layer);
                tileErrors = 0;
                showLoadState("Đang tải bản đồ...", "is-loading");
            });
        }

        window.setTimeout(function () {
            map.invalidateSize();
        }, 0);
        return map;
    }

    function validCoordinate(value) {
        return Number.isFinite(value);
    }

    function initPicker() {
        const element = document.querySelector("[data-map-picker]");
        if (!element) return;

        const latitudeInput = document.getElementById("id_latitude");
        const longitudeInput = document.getElementById("id_longitude");
        const locationButton = document.getElementById("use-current-location");
        const status = document.getElementById("location-status");
        const initialLatitude = Number.parseFloat(element.dataset.latitude);
        const initialLongitude = Number.parseFloat(element.dataset.longitude);
        const hasInitialLocation =
            validCoordinate(initialLatitude) &&
            validCoordinate(initialLongitude) &&
            isWithinDaNang(initialLatitude, initialLongitude);
        const initialCenter = hasInitialLocation
            ? [initialLatitude, initialLongitude]
            : daNangCenter;
        const map = createMap(element, initialCenter, hasInitialLocation ? 15 : 11);
        const instruction = document.createElement("div");
        instruction.className = "map-picker-instruction";
        instruction.textContent = "Bấm lên bản đồ để đặt ghim · Kéo ghim để chỉnh";
        element.appendChild(instruction);
        let marker = null;
        let selectedLocation = null;

        function setLocation(latitude, longitude, centerMap) {
            if (!isWithinDaNang(latitude, longitude)) {
                status.textContent = "Vị trí này nằm ngoài phạm vi Đà Nẵng. Hãy chọn lại trong khu vực được hỗ trợ.";
                if (marker && selectedLocation) marker.setLatLng(selectedLocation);
                return false;
            }
            selectedLocation = [latitude, longitude];
            latitudeInput.value = latitude.toFixed(6);
            longitudeInput.value = longitude.toFixed(6);
            if (!marker) {
                marker = L.marker([latitude, longitude], {
                    draggable: true,
                    icon: createPinIcon(),
                    title: "Vị trí ca cứu hộ",
                }).addTo(map);
                marker.on("dragend", function () {
                    const position = marker.getLatLng();
                    setLocation(position.lat, position.lng, false);
                });
            } else {
                marker.setLatLng([latitude, longitude]);
            }
            if (centerMap) map.setView([latitude, longitude], 16);
            element.classList.add("has-selection");
            instruction.textContent = "Đã đặt ghim · Có thể kéo để chỉnh chính xác";
            status.textContent = `Đã chọn vị trí: ${latitude.toFixed(6)}, ${longitude.toFixed(6)}.`;
            return true;
        }

        if (hasInitialLocation) setLocation(initialLatitude, initialLongitude, false);

        map.on("click", function (event) {
            setLocation(event.latlng.lat, event.latlng.lng, false);
        });

        locationButton.addEventListener("click", function () {
            if (!navigator.geolocation) {
                status.textContent = "Trình duyệt này không hỗ trợ lấy vị trí hiện tại.";
                return;
            }
            locationButton.disabled = true;
            status.textContent = "Đang xác định vị trí của bạn...";
            navigator.geolocation.getCurrentPosition(
                function (position) {
                    setLocation(position.coords.latitude, position.coords.longitude, true);
                    locationButton.disabled = false;
                },
                function () {
                    status.textContent = "Không thể lấy vị trí. Bạn có thể bấm trực tiếp lên bản đồ.";
                    locationButton.disabled = false;
                },
                { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
            );
        });
    }

    function initDetailMap() {
        const element = document.querySelector("[data-case-map]");
        if (!element) return;

        const latitude = Number.parseFloat(element.dataset.latitude);
        const longitude = Number.parseFloat(element.dataset.longitude);
        if (!validCoordinate(latitude) || !validCoordinate(longitude)) return;

        const isApproximate = element.dataset.approximate === "true";
        const map = createMap(element, [latitude, longitude], isApproximate ? 13 : 16);
        L.marker([latitude, longitude], { icon: createPinIcon() })
            .addTo(map)
            .bindPopup(element.dataset.title);
        if (isApproximate) {
            L.circle([latitude, longitude], {
                radius: 1400,
                color: "#d66543",
                fillColor: "#e47754",
                fillOpacity: 0.14,
                weight: 2,
            }).addTo(map);
        }
    }

    function haversineDistance(latitude1, longitude1, latitude2, longitude2) {
        const earthRadius = 6371;
        const toRadians = (degrees) => (degrees * Math.PI) / 180;
        const latitudeDelta = toRadians(latitude2 - latitude1);
        const longitudeDelta = toRadians(longitude2 - longitude1);
        const a =
            Math.sin(latitudeDelta / 2) ** 2 +
            Math.cos(toRadians(latitude1)) *
                Math.cos(toRadians(latitude2)) *
                Math.sin(longitudeDelta / 2) ** 2;
        return earthRadius * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    }

    function buildPopup(rescueCase) {
        const wrapper = document.createElement("div");
        wrapper.className = "map-popup";

        const title = document.createElement("strong");
        title.textContent = rescueCase.title;
        wrapper.appendChild(title);

        const meta = document.createElement("span");
        meta.textContent = `${rescueCase.animal_type} · ${rescueCase.status}`;
        wrapper.appendChild(meta);

        const address = document.createElement("p");
        address.textContent = rescueCase.address;
        wrapper.appendChild(address);

        const link = document.createElement("a");
        link.href = rescueCase.detail_url;
        link.textContent = "Xem chi tiết →";
        wrapper.appendChild(link);
        return wrapper;
    }

    function initCasesMap() {
        const element = document.querySelector("[data-cases-map]");
        const dataElement = document.getElementById("map-case-data");
        if (!element || !dataElement) return;

        const cases = JSON.parse(dataElement.textContent);
        const map = createMap(element, daNangCenter, 11);
        const markerLayer = L.layerGroup().addTo(map);
        const cards = new Map(
            Array.from(document.querySelectorAll("[data-map-card]")).map((card) => [
                Number(card.dataset.caseId),
                card,
            ])
        );
        const markers = new Map();
        const animalFilter = document.getElementById("map-animal-filter");
        const statusFilter = document.getElementById("map-status-filter");
        const radiusSelect = document.getElementById("nearby-radius");
        const nearbyButton = document.getElementById("find-nearby");
        const clearNearbyButton = document.getElementById("clear-nearby");
        const feedback = document.getElementById("map-feedback");
        let currentLocation = null;
        let currentLocationLayer = null;

        function render() {
            markerLayer.clearLayers();
            markers.clear();
            const visibleBounds = [];
            const radius = Number.parseFloat(radiusSelect.value);
            let visibleCount = 0;

            cases.forEach(function (rescueCase) {
                const matchesAnimal = !animalFilter.value || rescueCase.animal_type_value === animalFilter.value;
                const matchesStatus = !statusFilter.value || rescueCase.status_value === statusFilter.value;
                let distance = null;
                let matchesDistance = true;
                if (currentLocation) {
                    distance = haversineDistance(
                        currentLocation.latitude,
                        currentLocation.longitude,
                        rescueCase.latitude,
                        rescueCase.longitude
                    );
                    matchesDistance = distance <= radius;
                }
                const visible = matchesAnimal && matchesStatus && matchesDistance;
                const card = cards.get(rescueCase.id);
                if (card) {
                    card.hidden = !visible;
                    const distanceElement = card.querySelector("[data-distance]");
                    distanceElement.textContent = distance === null ? "" : `${distance.toFixed(1)} km từ bạn`;
                }
                if (!visible) return;

                const marker = L.marker([rescueCase.latitude, rescueCase.longitude], {
                    icon: createPinIcon(),
                    title: rescueCase.title,
                })
                    .bindPopup(buildPopup(rescueCase))
                    .addTo(markerLayer);
                markers.set(rescueCase.id, marker);
                visibleBounds.push([rescueCase.latitude, rescueCase.longitude]);
                visibleCount += 1;
            });

            if (currentLocation) visibleBounds.push([currentLocation.latitude, currentLocation.longitude]);
            if (visibleBounds.length > 1) map.fitBounds(visibleBounds, { padding: [35, 35], maxZoom: 14 });
            else if (visibleBounds.length === 1) map.setView(visibleBounds[0], 13);
            else map.setView(daNangCenter, 11);

            feedback.textContent = currentLocation
                ? `Tìm thấy ${visibleCount} ca trong bán kính ${radius} km.`
                : `Đang hiển thị ${visibleCount} ca có vị trí.`;
        }

        animalFilter.addEventListener("change", render);
        statusFilter.addEventListener("change", render);
        radiusSelect.addEventListener("change", render);

        nearbyButton.addEventListener("click", function () {
            if (!navigator.geolocation) {
                feedback.textContent = "Trình duyệt này không hỗ trợ lấy vị trí hiện tại.";
                return;
            }
            nearbyButton.disabled = true;
            feedback.textContent = "Đang xác định vị trí của bạn...";
            navigator.geolocation.getCurrentPosition(
                function (position) {
                    const latitude = position.coords.latitude;
                    const longitude = position.coords.longitude;
                    if (!isWithinDaNang(latitude, longitude)) {
                        feedback.textContent = "Vị trí của bạn nằm ngoài phạm vi hỗ trợ tại Đà Nẵng.";
                        nearbyButton.disabled = false;
                        return;
                    }
                    currentLocation = { latitude, longitude };
                    if (currentLocationLayer) currentLocationLayer.remove();
                    currentLocationLayer = L.circleMarker(
                        [currentLocation.latitude, currentLocation.longitude],
                        {
                            radius: 8,
                            color: "#ffffff",
                            fillColor: "#26705f",
                            fillOpacity: 1,
                            weight: 3,
                        }
                    ).addTo(map).bindPopup("Vị trí của bạn");
                    clearNearbyButton.hidden = false;
                    nearbyButton.disabled = false;
                    render();
                },
                function () {
                    feedback.textContent = "Không thể lấy vị trí. Hãy kiểm tra quyền vị trí của trình duyệt.";
                    nearbyButton.disabled = false;
                },
                { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
            );
        });

        clearNearbyButton.addEventListener("click", function () {
            currentLocation = null;
            if (currentLocationLayer) {
                currentLocationLayer.remove();
                currentLocationLayer = null;
            }
            clearNearbyButton.hidden = true;
            render();
        });

        document.querySelectorAll("[data-focus-case]").forEach(function (button) {
            button.addEventListener("click", function () {
                const caseId = Number(button.dataset.focusCase);
                const marker = markers.get(caseId);
                if (!marker) return;
                map.setView(marker.getLatLng(), 16);
                marker.openPopup();
            });
        });

        render();
    }

    initPicker();
    initDetailMap();
    initCasesMap();
})();
