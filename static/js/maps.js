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

    // Chỉ nhận tọa độ trong phạm vi Đà Nẵng mà hệ thống hỗ trợ cứu hộ.
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
                name: "MapTiler (tùy chọn)",
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
        // Nền OpenStreetMap không cần khóa giúp bản đồ vẫn dùng được khi khóa MapTiler hết hạn.
        providers.unshift({
            name: "OpenStreetMap",
            url: "https://tile.openstreetmap.de/{z}/{x}/{y}.png",
            options: {
                attribution: osmAttribution,
                maxZoom: 19,
                referrerPolicy: "strict-origin-when-cross-origin",
            },
        });
        return providers;
    }

    function createPinIcon(approximate = false) {
        return L.divIcon({
            className: approximate ? "rescue-map-marker is-approximate" : "rescue-map-marker",
            html: approximate ? '<span aria-hidden="true">?</span>' : '<span aria-hidden="true"><i></i></span>',
            iconSize: approximate ? [32, 32] : [36, 44],
            iconAnchor: approximate ? [16, 16] : [18, 42],
            popupAnchor: [0, -38],
        });
    }

    function createMap(element, center, zoom) {
        const daNangBounds = L.latLngBounds(daNangBoundsCoordinates);
        const initialCenter = daNangBounds.contains(center) ? center : daNangCenter;
        let map = null;
        try {
            map = L.map(element, {
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
            const layers = tileProviders.map(function (provider) {
                return L.tileLayer(provider.url, provider.options);
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
                        showLoadState(`Đang chuyển sang ${tileProviders[activeLayerIndex].name}...`, "is-loading");
                        return;
                    }
                    showLoadState(
                        element.hasAttribute("data-map-picker")
                            ? "Không tải được nền bản đồ. Bạn vẫn có thể nhập tọa độ bên dưới."
                            : "Không thể tải nền bản đồ. Hãy kiểm tra kết nối mạng rồi tải lại trang.",
                        "is-error"
                    );
                });
            });

            activeLayer.addTo(map);

            window.setTimeout(function () {
                map.invalidateSize();
            }, 0);
            return map;
        } catch (_) {
            if (map) map.remove();
            element.textContent = "Không tải được bản đồ. Hãy dùng địa chỉ và tọa độ của ca cứu hộ.";
            element.setAttribute("role", "status");
            return null;
        }
    }

    function validCoordinate(value) {
        return Number.isFinite(value);
    }

    function readCoordinate(value) {
        return value.trim() === "" ? NaN : Number(value);
    }

    // ===== CHỨC NĂNG CHÍNH: LẤY VỊ TRÍ NHANH VÀ CÓ THỂ HỦY =====
    // Một lần bấm lấy vị trí nhanh và tinh chỉnh ghim theo sai số; dừng theo dõi khi hủy hoặc chọn thủ công.
    function bindLocationButton(button, feedback, onLocation, fallbackHint, acceptsLocation, onApproximate) {
        const permissionTimeout = 30000;
        const acquisitionTimeout = 15000;
        const targetAccuracy = 50;
        const maximumAccuracy = 1000;
        const initialLabel = button.textContent;
        let currentRequest = null;

        function stop() {
            const request = currentRequest;
            currentRequest = null;
            if (request) {
                window.clearTimeout(request.timer);
                if (request.watchId !== null) navigator.geolocation.clearWatch(request.watchId);
                if (request.permission && request.permissionHandler) {
                    request.permission.removeEventListener("change", request.permissionHandler);
                }
            }
            button.textContent = initialLabel;
            button.disabled = false;
            button.setAttribute("aria-busy", "false");
        }

        function accuracyOf(position) {
            const accuracy = position.coords.accuracy;
            return Number.isFinite(accuracy) && accuracy >= 0 ? accuracy : Infinity;
        }

        function pageLeaves() {
            if (!currentRequest) return;
            stop();
            feedback.textContent = "Đã dừng lấy vị trí khi rời trang. Bạn có thể bấm lại khi cần.";
        }
        if (window.addEventListener) window.addEventListener("pagehide", pageLeaves);
        if (document.addEventListener) document.addEventListener("visibilitychange", function () {
            if (document.hidden) pageLeaves();
        });

        button.addEventListener("click", function () {
            if (currentRequest) {
                stop();
                feedback.textContent = "Đã hủy lấy vị trí. Bạn có thể bấm lại khi cần.";
                return;
            }
            if (typeof navigator === "undefined" || !navigator.geolocation) {
                feedback.textContent = `Trình duyệt không hỗ trợ lấy vị trí. ${fallbackHint}`;
                return;
            }
            if (window.isSecureContext === false) {
                feedback.textContent = `Cần mở trang bằng HTTPS hoặc localhost để lấy vị trí. ${fallbackHint}`;
                return;
            }

            const request = {
                timer: null, watchId: null, preciseStarted: false, acquiring: false,
                permission: null, permissionHandler: null, candidate: null,
                selectionText: "", outsideArea: false, approximate: null,
                fastError: null, preciseError: null, lastError: null,
            };
            currentRequest = request;
            button.textContent = "Hủy lấy vị trí";
            button.setAttribute("aria-busy", "true");
            feedback.textContent = "Đang chờ vị trí… Hãy cho phép truy cập nếu trình duyệt hỏi (chờ quyền tối đa 30 giây).";

            function isCurrent() {
                return currentRequest === request;
            }

            function fail(message) {
                stop();
                feedback.textContent = `${message} ${fallbackHint}`;
            }

            function showAccuracy(finished) {
                const accuracy = Math.ceil(accuracyOf(request.candidate));
                feedback.textContent = `${request.selectionText} Sai số ước tính khoảng ${accuracy} m.`;
                if (!finished) feedback.textContent += " Đang tinh chỉnh vị trí; bạn có thể kéo ghim để chọn chính xác hơn.";
                else if (accuracy > 150) feedback.textContent += " Vị trí gần đúng; hãy kiểm tra lại ghim trước khi gửi.";
            }

            function showApproximate(finished) {
                const accuracy = Math.ceil(accuracyOf(request.approximate));
                const guidance = onApproximate
                    ? "Chưa tự chọn tọa độ này; hãy kéo ghim hoặc bấm bản đồ để xác nhận đúng hiện trường."
                    : "Chưa áp dụng bộ lọc gần tôi vì vị trí chưa đủ chính xác.";
                const resultText = finished ? "Chưa lấy được vị trí đủ chính xác" : "Máy chỉ cung cấp vị trí gần đúng";
                feedback.textContent = `${resultText}, sai số khoảng ${accuracy} m. ${guidance}`;
                if (!finished) feedback.textContent += " Đang tìm kết quả chính xác hơn.";
                feedback.textContent += ` ${fallbackHint}`;
            }

            function finish() {
                if (!isCurrent()) return;
                if (request.candidate) {
                    stop();
                    showAccuracy(true);
                } else if (request.approximate) {
                    stop();
                    showApproximate(true);
                } else if (request.outsideArea) {
                    fail("Vị trí thiết bị nằm ngoài phạm vi hỗ trợ tại Đà Nẵng.");
                } else if (request.lastError === 2) {
                    fail("Trình duyệt hoặc dịch vụ vị trí của máy không cung cấp được vị trí. Kiểm tra kết nối mạng và dịch vụ vị trí của hệ điều hành rồi thử lại.");
                } else if (request.lastError === 3) {
                    fail("Đã hết thời gian lấy vị trí từ máy. Bạn có thể bấm lại để thử.");
                } else {
                    fail("Chưa nhận được vị trí đủ chính xác từ máy. Hãy kiểm tra quyền vị trí trong trình duyệt và hệ điều hành rồi thử lại.");
                }
            }

            function beginAcquisition() {
                if (!isCurrent() || request.acquiring) return;
                request.acquiring = true;
                window.clearTimeout(request.timer);
                request.timer = window.setTimeout(finish, acquisitionTimeout);
                if (!request.candidate) feedback.textContent = "Đang xác định vị trí, tối đa 15 giây. Ghim sẽ hiện ngay khi máy trả kết quả.";
            }

            function handleError(error, source) {
                if (!isCurrent()) return;
                if (error && error.code === 1) {
                    fail("Quyền vị trí đang bị chặn. Hãy cho phép vị trí trong trình duyệt và hệ điều hành rồi bấm lại.");
                    return;
                }
                request.lastError = error && error.code || 2;
                if (source === "fast") request.fastError = request.lastError;
                if (source === "precise") request.preciseError = request.lastError;
                if (request.fastError && request.preciseError) {
                    finish();
                    return;
                }
                beginAcquisition();
                startPrecise();
                if (isCurrent() && !request.candidate && !request.approximate && request.lastError === 2) {
                    feedback.textContent = "Máy chưa cung cấp được vị trí. Đang thử nguồn định vị còn lại; bạn vẫn có thể bấm bản đồ để chọn điểm.";
                }
            }

            function receive(position) {
                if (!isCurrent()) return;
                beginAcquisition();
                const coords = position && position.coords;
                if (!coords || !validCoordinate(coords.latitude) || !validCoordinate(coords.longitude)) {
                    startPrecise();
                    return;
                }
                if (acceptsLocation && !acceptsLocation(coords.latitude, coords.longitude)) {
                    request.outsideArea = true;
                    feedback.textContent = `Máy đang báo vị trí ngoài khu vực Đà Nẵng. Đang kiểm tra lại; chưa thay đổi ghim. ${fallbackHint}`;
                    startPrecise();
                    return;
                }
                request.outsideArea = false;
                const accuracy = accuracyOf(position);
                if (Number.isFinite(accuracy) && accuracy > maximumAccuracy && !request.candidate) {
                    if (!request.approximate || accuracy < accuracyOf(request.approximate)) {
                        request.approximate = position;
                        if (onApproximate) onApproximate(position);
                        showApproximate(false);
                    }
                    startPrecise();
                    return;
                }
                if (accuracy > maximumAccuracy || request.candidate && accuracy >= accuracyOf(request.candidate)) {
                    startPrecise();
                    return;
                }
                request.candidate = position;
                onLocation(position);
                request.selectionText = feedback.textContent;
                showAccuracy(false);
                if (accuracy <= targetAccuracy) finish();
                else startPrecise();
            }

            function startPrecise() {
                if (!isCurrent() || request.preciseStarted) return;
                request.preciseStarted = true;
                const options = { enableHighAccuracy: true, timeout: acquisitionTimeout, maximumAge: 0 };
                try {
                    if (typeof navigator.geolocation.watchPosition === "function" && typeof navigator.geolocation.clearWatch === "function") {
                        const watchId = navigator.geolocation.watchPosition(receive, function (error) { handleError(error, "precise"); }, options);
                        if (isCurrent()) request.watchId = watchId;
                        else navigator.geolocation.clearWatch(watchId);
                    } else {
                        navigator.geolocation.getCurrentPosition(receive, function (error) { handleError(error, "precise"); }, options);
                    }
                } catch (error) {
                    handleError({ code: error && error.name === "SecurityError" ? 1 : 2 }, "precise");
                }
            }

            function trackPermission(permission) {
                if (!isCurrent()) return;
                if (permission.state === "denied") {
                    handleError({ code: 1 });
                    return;
                }
                if (permission.state === "granted") {
                    beginAcquisition();
                    startPrecise();
                } else if (!request.acquiring) {
                    feedback.textContent = "Hãy chọn Cho phép trong hộp thoại vị trí (chờ tối đa 30 giây). Không cần bấm lại nút lấy vị trí.";
                }
                if (isCurrent() && typeof permission.addEventListener === "function" && typeof permission.removeEventListener === "function" && !request.permission) {
                    request.permission = permission;
                    request.permissionHandler = function () { trackPermission(permission); };
                    permission.addEventListener("change", request.permissionHandler);
                }
            }

            request.timer = window.setTimeout(finish, permissionTimeout);
            try {
                navigator.geolocation.getCurrentPosition(receive, function (error) { handleError(error, "fast"); }, {
                    enableHighAccuracy: false, timeout: 3000, maximumAge: 10000,
                });
            } catch (error) {
                handleError({ code: error && error.name === "SecurityError" ? 1 : 2 }, "fast");
            }
            if (!isCurrent()) return;
            if (navigator.permissions && typeof navigator.permissions.query === "function") {
                try {
                    Promise.resolve(navigator.permissions.query({ name: "geolocation" }))
                        .then(trackPermission).catch(startPrecise);
                } catch (_) {
                    startPrecise();
                }
            } else {
                startPrecise();
            }
        });
        return stop;
    }

    function initPicker() {
        const element = document.querySelector("[data-map-picker]");
        if (!element) return;

        const latitudeInput = document.getElementById("id_latitude");
        const longitudeInput = document.getElementById("id_longitude");
        if (!latitudeInput || !longitudeInput) return;
        const addressInput = document.getElementById("id_address");
        const locationButton = document.getElementById("use-current-location");
        const status = document.getElementById("location-status");
        const summary = document.getElementById("location-summary");
        const confirmationInput = document.getElementById("id_location_confirmed");
        const addressSearch = document.querySelector("[data-address-search]");
        const initialLatitude = readCoordinate(latitudeInput.value || element.dataset.latitude || "");
        const initialLongitude = readCoordinate(longitudeInput.value || element.dataset.longitude || "");
        const hasInitialLocation =
            validCoordinate(initialLatitude) &&
            validCoordinate(initialLongitude) &&
            isWithinDaNang(initialLatitude, initialLongitude);
        const initialCenter = hasInitialLocation
            ? [initialLatitude, initialLongitude]
            : daNangCenter;
        const mapAvailable = typeof L !== "undefined";
        let map = mapAvailable ? createMap(element, initialCenter, hasInitialLocation ? 15 : 11) : null;
        let instruction = null;
        if (map) {
            instruction = document.createElement("div");
            instruction.className = "map-picker-instruction";
            instruction.textContent = "Bấm lên bản đồ để đặt ghim · Kéo ghim để chỉnh";
            element.appendChild(instruction);
        } else {
            element.textContent = "Không tải được bản đồ. Hãy nhập địa chỉ cụ thể, vĩ độ và kinh độ bên dưới; bạn vẫn gửi được báo cáo đến admin.";
            element.setAttribute("role", "status");
        }
        let marker = null;
        let approximateMarker = null;
        let accuracyCircle = null;
        let selectedLocation = null;
        let cancelLocationLookup = function () {};

        function invalidateConfirmation() {
            if (confirmationInput) confirmationInput.checked = false;
        }

        function cancelAddressSearch() {
            if (addressSearch) addressSearch.dispatchEvent(new Event("rescue:cancel-address-search"));
        }

        function clearPreview() {
            if (map && approximateMarker) map.removeLayer(approximateMarker);
            if (map && accuracyCircle) map.removeLayer(accuracyCircle);
            approximateMarker = null;
            accuracyCircle = null;
        }

        function disableMap() {
            if (map) map.remove();
            map = null;
            marker = null;
            approximateMarker = null;
            accuracyCircle = null;
            instruction = null;
            element.textContent = "Không tải được bản đồ. Vị trí đủ chính xác vẫn điền vào ô tọa độ; bạn vẫn gửi được báo cáo đến admin.";
            element.setAttribute("role", "status");
        }

        // Vị trí sai số lớn chỉ để xem trước; kéo ghim hoặc bấm bản đồ mới xác nhận tọa độ gửi admin.
        function showApproximateLocation(position) {
            if (!map || selectedLocation) return;
            clearPreview();
            const location = [position.coords.latitude, position.coords.longitude];
            try {
                approximateMarker = L.marker(location, {
                    draggable: true, icon: createPinIcon(true),
                    title: "Vị trí ước tính — chưa chọn hiện trường",
                }).addTo(map);
                approximateMarker.on("dragend", function () {
                    const point = approximateMarker.getLatLng();
                    cancelAddressSearch();
                    cancelLocationLookup();
                    setLocation(point.lat, point.lng, false);
                });
                accuracyCircle = L.circle(location, {
                    radius: position.coords.accuracy,
                    color: "#d66543", fillOpacity: 0.12, weight: 1,
                }).addTo(map);
                map.fitBounds(accuracyCircle.getBounds(), { padding: [25, 25], maxZoom: 13 });
                if (instruction) instruction.textContent = "Vị trí ước tính · Chưa chọn hiện trường · Kéo dấu ? hoặc bấm bản đồ";
            } catch (_) {
                disableMap();
            }
        }

        function updateSummary() {
            if (!summary) return;
            const address = addressInput ? addressInput.value.trim() : "";
            const coordinateText = selectedLocation
                ? `${selectedLocation[0].toFixed(6)}, ${selectedLocation[1].toFixed(6)}`
                : "chưa chọn";
            summary.textContent = `Địa chỉ gửi admin: ${address || "chưa nhập"}. Tọa độ: ${coordinateText}. Hãy kiểm tra hai thông tin cùng chỉ đúng một địa điểm.`;
        }

        function clearLocation() {
            invalidateConfirmation();
            selectedLocation = null;
            clearPreview();
            if (map && marker) {
                map.removeLayer(marker);
            }
            marker = null;
            element.classList.remove("has-selection");
            if (instruction) instruction.textContent = "Bấm lên bản đồ để đặt ghim · Kéo ghim để chỉnh";
            updateSummary();
        }

        // ===== CHỨC NĂNG CHÍNH: CHỌN VỊ TRÍ TRÊN BẢN ĐỒ =====
        // Giữ ghim và ô tọa độ đồng bộ khi bấm bản đồ, kéo ghim hoặc lấy vị trí thiết bị.
        function setLocation(latitude, longitude, centerMap, writeInputs = true) {
            if (!validCoordinate(latitude) || !validCoordinate(longitude) || !isWithinDaNang(latitude, longitude)) {
                status.textContent = "Vị trí này nằm ngoài phạm vi Đà Nẵng. Hãy chọn lại trong khu vực được hỗ trợ.";
                if (marker && selectedLocation) marker.setLatLng(selectedLocation);
                return false;
            }
            const changed = !selectedLocation || latitude.toFixed(6) !== selectedLocation[0].toFixed(6) || longitude.toFixed(6) !== selectedLocation[1].toFixed(6);
            if (writeInputs && changed) invalidateConfirmation();
            clearPreview();
            selectedLocation = [latitude, longitude];
            if (writeInputs) {
                latitudeInput.value = latitude.toFixed(6);
                longitudeInput.value = longitude.toFixed(6);
            }
            try {
                if (map && !marker) {
                    marker = L.marker([latitude, longitude], {
                        draggable: true,
                        icon: createPinIcon(),
                        title: "Vị trí ca cứu hộ",
                    }).addTo(map);
                    marker.on("dragend", function () {
                        cancelAddressSearch();
                        cancelLocationLookup();
                        const position = marker.getLatLng();
                        setLocation(position.lat, position.lng, false);
                    });
                } else if (marker) {
                    marker.setLatLng([latitude, longitude]);
                }
                if (map && centerMap) map.setView([latitude, longitude], 16);
            } catch (_) {
                disableMap();
            }
            element.classList.add("has-selection");
            if (instruction) instruction.textContent = "Đã đặt ghim · Có thể kéo để chỉnh chính xác";
            status.textContent = `Đã chọn tọa độ: ${latitude.toFixed(6)}, ${longitude.toFixed(6)}. ${map ? "Kiểm tra ghim và địa chỉ trước khi gửi." : "Có thể gửi báo cáo dù bản đồ chưa tải được."}`;
            updateSummary();
            return true;
        }

        function syncFromInputs(centerMap) {
            const latitude = readCoordinate(latitudeInput.value);
            const longitude = readCoordinate(longitudeInput.value);
            if (!validCoordinate(latitude) || !validCoordinate(longitude)) {
                clearLocation();
                status.textContent = "Hãy chọn ghim hoặc nhập đầy đủ vĩ độ và kinh độ ở hai ô bên dưới.";
                return;
            }
            if (!setLocation(latitude, longitude, centerMap, false)) clearLocation();
        }

        if (hasInitialLocation) setLocation(initialLatitude, initialLongitude, false, false);
        else syncFromInputs(false);

        [latitudeInput, longitudeInput].forEach(function (input) {
            input.addEventListener("input", function () { invalidateConfirmation(); cancelAddressSearch(); cancelLocationLookup(); syncFromInputs(true); });
            input.addEventListener("change", function () { invalidateConfirmation(); cancelAddressSearch(); cancelLocationLookup(); syncFromInputs(true); });
        });
        if (addressInput) addressInput.addEventListener("input", function () {
            invalidateConfirmation();
            updateSummary();
        });
        if (confirmationInput) confirmationInput.addEventListener("change", function () {
            if (confirmationInput.checked && (!selectedLocation || !addressInput || !addressInput.value.trim())) {
                confirmationInput.checked = false;
                status.textContent = "Hãy nhập địa chỉ cụ thể và đặt ghim đúng hiện trường trước khi xác nhận.";
            }
        });

        if (map) {
            map.on("click", function (event) {
                cancelAddressSearch();
                cancelLocationLookup();
                setLocation(event.latlng.lat, event.latlng.lng, false);
            });
        }

        if (addressSearch) {
            addressSearch.addEventListener("rescue:address-search-start", function () {
                invalidateConfirmation();
                cancelLocationLookup();
            });
            addressSearch.addEventListener("rescue:address-selected", function (event) {
                const point = event.detail;
                if (!point || !validCoordinate(point.latitude) || !validCoordinate(point.longitude) || !isWithinDaNang(point.latitude, point.longitude)) return;
                invalidateConfirmation();
                cancelLocationLookup();
                if (setLocation(point.latitude, point.longitude, true)) {
                    if (map) map.setView([point.latitude, point.longitude], 18);
                    status.textContent = "Đã đặt ghim theo địa chỉ gợi ý. Kiểm tra đúng số nhà/hiện trường, kéo ghim nếu cần rồi tự đánh dấu xác nhận trước khi gửi.";
                }
            });
        }

        if (!locationButton) return;
        locationButton.addEventListener("click", function () { cancelAddressSearch(); invalidateConfirmation(); });
        cancelLocationLookup = bindLocationButton(
            locationButton, status,
            function (position) {
                setLocation(position.coords.latitude, position.coords.longitude, true);
            },
            "Hãy chọn ghim hoặc nhập vĩ độ và kinh độ bên dưới.",
            isWithinDaNang,
            showApproximateLocation
        );
    }

    function initDetailMap() {
        const element = document.querySelector("[data-case-map]");
        if (!element) return;

        const latitude = Number.parseFloat(element.dataset.latitude);
        const longitude = Number.parseFloat(element.dataset.longitude);
        if (!validCoordinate(latitude) || !validCoordinate(longitude)) return;

        // Máy chủ quyết định quyền xem vị trí; tọa độ đã làm mờ được thể hiện bằng vùng gần đúng.
        const isApproximate = element.dataset.approximate === "true";
        const map = createMap(element, [latitude, longitude], isApproximate ? 13 : 16);
        if (!map) return;
        const popupTitle = document.createElement("strong");
        popupTitle.textContent = element.dataset.title;
        L.marker([latitude, longitude], { icon: createPinIcon() })
            .addTo(map)
            .bindPopup(popupTitle);
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

    // Ghim mở ảnh, địa chỉ, đơn vị và thời điểm chốt; dùng văn bản để nội dung nhập không thành mã HTML.
    function buildPopup(rescueCase) {
        const wrapper = document.createElement("div");
        wrapper.className = "map-popup";

        if (rescueCase.image_url) {
            const image = document.createElement("img");
            image.src = rescueCase.image_url;
            image.alt = `Ảnh ca cứu hộ #${rescueCase.id}`;
            image.loading = "lazy";
            wrapper.appendChild(image);
        }

        const title = document.createElement("strong");
        title.textContent = `#${rescueCase.id} · ${rescueCase.title}`;
        wrapper.appendChild(title);

        const meta = document.createElement("span");
        meta.textContent = `${rescueCase.animal_type} · ${rescueCase.status}`;
        wrapper.appendChild(meta);

        const address = document.createElement("p");
        address.textContent = rescueCase.address;
        wrapper.appendChild(address);

        const organization = document.createElement("p");
        organization.textContent = `Đơn vị cứu hộ: ${rescueCase.organization}`;
        wrapper.appendChild(organization);

        if (rescueCase.completed_at_display) {
            const completed = document.createElement("p");
            completed.textContent = `Duyệt thành công: ${rescueCase.completed_at_display}`;
            wrapper.appendChild(completed);
        }

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
        if (!map) return;
        const markerLayer = L.layerGroup().addTo(map);
        const cards = new Map(
            Array.from(document.querySelectorAll("[data-map-card]")).map((card) => [
                Number(card.dataset.caseId),
                card,
            ])
        );
        const markers = new Map();
        const animalFilter = document.getElementById("map-animal-filter");
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
                const visible = matchesAnimal && matchesDistance;
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
                ? `Tìm thấy ${visibleCount} ca cứu hộ thành công trong bán kính ${radius} km.`
                : `Đang hiển thị ${visibleCount} ca cứu hộ thành công có vị trí.`;
        }

        animalFilter.addEventListener("change", render);
        radiusSelect.addEventListener("change", render);

        const cancelNearbyLookup = bindLocationButton(
            nearbyButton, feedback,
            function (position) {
                const latitude = position.coords.latitude;
                const longitude = position.coords.longitude;
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
                render();
            },
            "Kiểm tra quyền vị trí của trình duyệt rồi thử lại."
        );

        clearNearbyButton.addEventListener("click", function () {
            cancelNearbyLookup();
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
    if (typeof L !== "undefined") {
        initDetailMap();
        initCasesMap();
    } else {
        document.querySelectorAll("[data-case-map], [data-cases-map]").forEach(function (element) {
            element.textContent = "Không tải được bản đồ. Hãy xem thông tin địa chỉ của ca cứu hộ.";
            element.setAttribute("role", "status");
        });
    }
})();
