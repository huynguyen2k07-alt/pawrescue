const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "../static/js/maps.js"), "utf8");

function virtualClock() {
    let now = 0;
    let nextId = 0;
    const timers = new Map();
    return {
        setTimeout(callback, delay = 0) {
            const id = ++nextId;
            timers.set(id, { callback, due: now + delay });
            return id;
        },
        clearTimeout(id) { timers.delete(id); },
        tick(milliseconds) {
            const end = now + milliseconds;
            while (true) {
                const next = [...timers].filter(([, timer]) => timer.due <= end)
                    .sort((a, b) => a[1].due - b[1].due)[0];
                if (!next) break;
                const [id, timer] = next;
                timers.delete(id);
                now = timer.due;
                timer.callback();
            }
            now = end;
        },
        pending() { return timers.size; },
    };
}

function position(latitude = 16.08, longitude = 108.23, accuracy = 30) {
    return { coords: { latitude, longitude, accuracy } };
}

function eventTarget(target = {}) {
    const listeners = new Map();
    return Object.assign(target, {
        handlers: {},
        addEventListener(name, handler) {
            if (!listeners.has(name)) listeners.set(name, new Set());
            listeners.get(name).add(handler);
            this.handlers[name] = (event = { type: name }) => {
                for (const callback of [...(listeners.get(name) || [])]) callback(event);
            };
        },
        removeEventListener(name, handler) {
            const callbacks = listeners.get(name);
            if (callbacks) callbacks.delete(handler);
            if (!callbacks || !callbacks.size) delete this.handlers[name];
        },
        dispatchEvent(event) {
            if (this.handlers[event.type]) this.handlers[event.type](event);
            return true;
        },
        fire(name) { this.dispatchEvent({ type: name }); },
        listenerCount(name) { return (listeners.get(name) || new Set()).size; },
    });
}

function locationApi({ permission, permissionQuery, watch = true, watchImmediately } = {}) {
    const requests = [];
    const watches = [];
    const clearedWatches = [];
    const activeWatches = new Set();
    const geolocation = {
        getCurrentPosition(success, failure, options) { requests.push({ success, failure, options }); },
    };
    if (watch) {
        geolocation.watchPosition = function (success, failure, options) {
            const id = watches.length;
            const entry = { id, success, failure, options };
            watches.push(entry);
            activeWatches.add(id);
            if (watchImmediately) watchImmediately(entry);
            return id;
        };
        geolocation.clearWatch = function (id) {
            clearedWatches.push(id);
            activeWatches.delete(id);
        };
    }
    const navigator = { geolocation };
    let permissionStatus = null;
    if (permission || permissionQuery) {
        permissionStatus = eventTarget({ state: permission || "prompt" });
        navigator.permissions = {
            query() {
                if (permissionQuery === "throw") throw new Error("Permission lookup unavailable");
                if (permissionQuery === "reject") return Promise.reject(new Error("Permission lookup unavailable"));
                return Promise.resolve(permissionStatus);
            },
        };
    }
    return {
        navigator, requests, watches, clearedWatches, activeWatches, permissionStatus,
        setPermission(state) {
            permissionStatus.state = state;
            permissionStatus.fire("change");
        },
    };
}

async function flushPermissions() {
    await new Promise((resolve) => setImmediate(resolve));
}

function picker({ leaflet = true, mapError = "", latitude = "", longitude = "", confirmed = false, detailTitle = null, maptilerKey = "", searchPanel = false, ...locationOptions } = {}) {
    function element(value = "") {
        const classes = new Set();
        return eventTarget({
            value, textContent: "", dataset: {}, children: [],
            classList: {
                add(name) { classes.add(name); },
                remove(name) { classes.delete(name); },
                contains(name) { return classes.has(name); },
            },
            appendChild(child) { this.children.push(child); },
            replaceChildren(...children) { this.children = children; },
            setAttribute(name, value) { this[name] = value; },
            hasAttribute(name) { return name === "data-map-picker"; },
        });
    }

    const mapElement = element();
    mapElement.dataset.maptilerKey = maptilerKey;
    const addressSearchPanel = searchPanel ? element() : null;
    const detailElement = detailTitle === null ? null : element();
    if (detailElement) {
        detailElement.dataset = { latitude: "16.05", longitude: "108.20", title: detailTitle };
    }
    const inputs = {
        id_latitude: element(latitude),
        id_longitude: element(longitude),
        id_address: element("430 Hùng Vương, Hải Châu, Đà Nẵng"),
        id_location_confirmed: element(),
        "use-current-location": element(),
        "location-status": element(),
        "location-summary": element(),
    };
    inputs.id_location_confirmed.checked = confirmed;
    inputs["use-current-location"].textContent = "Dùng vị trí hiện tại";
    inputs["use-current-location"].disabled = false;
    const clock = virtualClock();
    const location = locationApi(locationOptions);
    const map = {
        handlers: {}, markers: new Set(), circles: new Set(), views: [], tileLayers: [],
        on(name, handler) { this.handlers[name] = handler; return this; },
        setView(location, zoom) { this.views.push({ location, zoom }); return this; },
        fitBounds(bounds, options) { this.fittedBounds = { bounds, options }; return this; },
        removeLayer(layer) { this.markers.delete(layer); this.circles.delete(layer); },
        remove() { this.removed = true; this.markers.clear(); this.circles.clear(); },
        invalidateSize() {},
    };
    const context = {
        URL,
        Event: class {
            constructor(type, options = {}) { this.type = type; this.bubbles = Boolean(options.bubbles); }
        },
        document: eventTarget({
            hidden: false, visibilityState: "visible",
            querySelector(selector) {
                if (selector === "[data-map-picker]") return mapElement;
                if (selector === "[data-case-map]") return detailElement;
                if (selector === "[data-address-search]") return addressSearchPanel;
                return null;
            },
            querySelectorAll() { return []; },
            getElementById(id) { return inputs[id] || null; },
            createElement: element,
        }),
        window: eventTarget({ setTimeout: clock.setTimeout, clearTimeout: clock.clearTimeout }),
        navigator: location.navigator,
    };
    if (leaflet) {
        context.L = {
            latLngBounds() { return { contains() { return true; } }; },
            map() {
                if (mapError === "map") throw new Error("Map initialization failed");
                return map;
            },
            tileLayer(url) {
                if (mapError === "tiles") throw new Error("Tile initialization failed");
                return { on() { return this; }, addTo(target) { target.tileLayers.push(url); return this; } };
            },
            control: { layers() { throw new Error("The map must not show a second provider selector"); } },
            divIcon(options) { return options; },
            marker(location, options = {}) {
                return {
                    location, options, handlers: {},
                    addTo(target) { this.target = target; target.markers.add(this); return this; },
                    remove() { if (this.target) this.target.removeLayer(this); return this; },
                    on(name, handler) { this.handlers[name] = handler; return this; },
                    setLatLng(next) { this.location = next; return this; },
                    getLatLng() { return { lat: this.location[0], lng: this.location[1] }; },
                    bindPopup(content) { this.popup = content; return this; },
                };
            },
            circle(location, options = {}) {
                return {
                    location, options,
                    addTo(target) { this.target = target; target.circles.add(this); return this; },
                    remove() { if (this.target) this.target.removeLayer(this); return this; },
                    setLatLng(next) { this.location = next; return this; },
                    setRadius(radius) { this.options.radius = radius; return this; },
                    getBounds() { return [this.location, this.location]; },
                };
            },
        };
    }
    vm.runInNewContext(source, context);
    clock.tick(0);
    return { map, mapElement, inputs, context, clock, searchPanel: addressSearchPanel, ...location, marker: () => [...map.markers][0] };
}

test("manual coordinate edits synchronize the marker without rewriting the typed value", () => {
    const ui = picker();
    ui.inputs.id_latitude.value = "16.0544";
    ui.inputs.id_longitude.value = "108.2022";
    ui.inputs.id_longitude.fire("input");
    assert.equal(ui.inputs.id_latitude.value, "16.0544");
    assert.equal(ui.marker().getLatLng().lat, 16.0544);
    assert.equal(ui.marker().getLatLng().lng, 108.2022);
    assert.equal(ui.map.views.at(-1).zoom, 16);
    assert.match(ui.inputs["location-summary"].textContent, /430 Hùng Vương/);
    ui.inputs.id_address.value = "Cổng chợ Hàn";
    ui.inputs.id_address.fire("input");
    assert.match(ui.inputs["location-summary"].textContent, /Cổng chợ Hàn/);
});

test("configured or stale MapTiler keys cannot replace the working default map", () => {
    const ui = picker({ maptilerKey: "a-stale-configured-key" });
    assert.equal(new URL(ui.map.tileLayers[0]).hostname, "tile.openstreetmap.de");
    assert.equal(ui.map.tileLayers.length, 1);
});

test("incomplete and out-of-area manual coordinates remove the stale pin", () => {
    const ui = picker({ latitude: "16.05", longitude: "108.20" });
    assert.ok(ui.marker());
    ui.inputs.id_latitude.value = "";
    ui.inputs.id_latitude.fire("input");
    assert.equal(ui.marker(), undefined);
    assert.match(ui.inputs["location-summary"].textContent, /Tọa độ: chưa chọn/);
    ui.inputs.id_latitude.value = "17";
    ui.inputs.id_latitude.fire("input");
    assert.equal(ui.marker(), undefined);
    assert.match(ui.inputs["location-status"].textContent, /ngoài phạm vi Đà Nẵng/);
});

test("map click and dragging synchronize inputs while rejecting an out-of-area drag", () => {
    const ui = picker();
    ui.map.handlers.click({ latlng: { lat: 16.06, lng: 108.21 } });
    assert.equal(ui.inputs.id_latitude.value, "16.060000");
    assert.equal(ui.inputs.id_longitude.value, "108.210000");
    ui.marker().setLatLng([16.07, 108.22]);
    ui.marker().handlers.dragend();
    assert.equal(ui.inputs.id_latitude.value, "16.070000");
    ui.marker().setLatLng([17, 108.22]);
    ui.marker().handlers.dragend();
    assert.equal(ui.marker().getLatLng().lat, 16.07);
    assert.equal(ui.inputs.id_latitude.value, "16.070000");
});

test("opening the report form never requests location or starts a watch", () => {
    const ui = picker({ permission: "granted" });
    assert.equal(ui.requests.length, 0);
    assert.equal(ui.watches.length, 0);
    assert.equal(ui.clock.pending(), 0);
    assert.equal(ui.inputs.id_location_confirmed.checked, false);
});

test("starting an address search stops GPS, clears confirmation and preserves the selected rescue pin", () => {
    const ui = picker({ searchPanel: true, latitude: "16.05", longitude: "108.20", confirmed: true });
    ui.inputs["use-current-location"].fire("click");
    ui.inputs.id_location_confirmed.checked = true;
    ui.inputs.id_location_confirmed.fire("change");
    assert.equal(ui.inputs.id_location_confirmed.checked, true);
    assert.equal(ui.activeWatches.size, 1);

    ui.searchPanel.fire("rescue:address-search-start");
    assert.equal(ui.inputs.id_location_confirmed.checked, false);
    assert.equal(ui.activeWatches.size, 0);
    assert.equal(ui.clock.pending(), 0);
    assert.equal(ui.inputs["use-current-location"]["aria-busy"], "false");
    ui.requests[0].success(position(16.08, 108.23));
    ui.watches[0].success(position(16.09, 108.24));
    assert.equal(ui.inputs.id_latitude.value, "16.05");
    assert.equal(ui.inputs.id_longitude.value, "108.20");
    assert.deepEqual(ui.marker().getLatLng(), { lat: 16.05, lng: 108.20 });
});

test("an address search also prevents a pending permission result from starting GPS later", async () => {
    const ui = picker({ searchPanel: true, permission: "granted" });
    ui.inputs["use-current-location"].fire("click");
    ui.searchPanel.fire("rescue:address-search-start");
    await flushPermissions();
    ui.requests[0].success(position());
    assert.equal(ui.watches.length, 0);
    assert.equal(ui.permissionStatus.listenerCount("change"), 0);
    assert.equal(ui.clock.pending(), 0);
    assert.equal(ui.inputs.id_latitude.value, "");
    assert.equal(ui.inputs.id_longitude.value, "");
    assert.equal(ui.marker(), undefined);
});

test("selecting an address suggestion places its pair at zoom 18 without replacing the reporter's landmark", () => {
    const ui = picker({ searchPanel: true, latitude: "16.05", longitude: "108.20", confirmed: true });
    const landmark = "Cổng sau màu xanh, đối diện quán nước\nGọi trước khi đến";
    ui.inputs.id_address.value = landmark;
    ui.inputs["use-current-location"].fire("click");
    ui.inputs.id_location_confirmed.checked = true;
    ui.searchPanel.dispatchEvent({
        type: "rescue:address-selected",
        detail: { latitude: 16.0673, longitude: 108.2242, label: "119 Trần Phú, Đà Nẵng" },
    });
    assert.equal(ui.inputs.id_latitude.value, "16.067300");
    assert.equal(ui.inputs.id_longitude.value, "108.224200");
    assert.deepEqual(ui.marker().getLatLng(), { lat: 16.0673, lng: 108.2242 });
    assert.deepEqual([...ui.map.views.at(-1).location], [16.0673, 108.2242]);
    assert.equal(ui.map.views.at(-1).zoom, 18);
    assert.equal(ui.inputs.id_address.value, landmark);
    assert.equal(ui.inputs.id_location_confirmed.checked, false);
    assert.ok(ui.inputs["location-summary"].textContent.includes(landmark));
    assert.match(ui.inputs["location-status"].textContent, /địa chỉ gợi ý.*Kiểm tra.*xác nhận/i);
    assert.equal(ui.activeWatches.size, 0);
    assert.equal(ui.clock.pending(), 0);

    const status = ui.inputs["location-status"].textContent;
    ui.requests[0].success(position(16.08, 108.23));
    ui.watches[0].success(position(16.09, 108.24));
    ui.watches[0].failure({ code: 1 });
    assert.equal(ui.inputs.id_latitude.value, "16.067300");
    assert.equal(ui.inputs.id_longitude.value, "108.224200");
    assert.equal(ui.inputs["location-status"].textContent, status);
    assert.equal(ui.map.views.at(-1).zoom, 18);
});

test("malformed and out-of-area address-selection events cannot change a checked rescue pin", () => {
    const invalidPoints = [
        undefined, null, "16.06,108.21", [], {},
        { latitude: 16.06 }, { longitude: 108.21 },
        { latitude: "16.06", longitude: 108.21 }, { latitude: 16.06, longitude: "108.21" },
        { latitude: NaN, longitude: 108.21 }, { latitude: 16.06, longitude: Infinity },
        { latitude: null, longitude: 108.21 },
        { latitude: 15.8499, longitude: 108.21 }, { latitude: 16.2501, longitude: 108.21 },
        { latitude: 16.06, longitude: 107.7499 }, { latitude: 16.06, longitude: 108.3501 },
    ];
    for (const detail of invalidPoints) {
        const ui = picker({ searchPanel: true, latitude: "16.05", longitude: "108.20", confirmed: true });
        const viewCount = ui.map.views.length;
        const status = ui.inputs["location-status"].textContent;
        ui.searchPanel.dispatchEvent({ type: "rescue:address-selected", detail });
        assert.equal(ui.inputs.id_latitude.value, "16.05");
        assert.equal(ui.inputs.id_longitude.value, "108.20");
        assert.deepEqual(ui.marker().getLatLng(), { lat: 16.05, lng: 108.20 });
        assert.equal(ui.inputs.id_location_confirmed.checked, true);
        assert.equal(ui.map.views.length, viewCount);
        assert.equal(ui.inputs["location-status"].textContent, status);
    }
});

test("GPS, map clicks, pin drags and manual coordinates cancel a pending address search before choosing their pin", () => {
    const actions = {
        gps(ui) {
            ui.inputs["use-current-location"].fire("click");
            ui.watches[0].success(position(16.06, 108.21));
        },
        mapClick(ui) { ui.map.handlers.click({ latlng: { lat: 16.06, lng: 108.21 } }); },
        pinDrag(ui) { ui.marker().setLatLng([16.06, 108.21]); ui.marker().handlers.dragend(); },
        latitudeInput(ui) {
            ui.inputs.id_latitude.value = "16.06";
            ui.inputs.id_latitude.fire("input");
        },
        longitudeChange(ui) {
            ui.inputs.id_longitude.value = "108.21";
            ui.inputs.id_longitude.fire("change");
        },
        incompleteCoordinate(ui) {
            ui.inputs.id_longitude.value = "";
            ui.inputs.id_longitude.fire("input");
        },
    };
    for (const [name, action] of Object.entries(actions)) {
        const ui = picker({ searchPanel: true, latitude: "16.05", longitude: "108.20" });
        let pendingSearch = true;
        let cancellations = 0;
        ui.searchPanel.addEventListener("rescue:cancel-address-search", () => {
            pendingSearch = false;
            cancellations += 1;
            assert.equal(ui.requests.length, 0, `${name}: cancel before any native GPS request`);
        });
        action(ui);
        assert.equal(pendingSearch, false, name);
        assert.equal(cancellations, 1, name);
        const latitude = ui.inputs.id_latitude.value;
        const longitude = ui.inputs.id_longitude.value;
        const viewCount = ui.map.views.length;
        if (pendingSearch) {
            ui.searchPanel.dispatchEvent({
                type: "rescue:address-selected",
                detail: { latitude: 16.10, longitude: 108.25, label: "Late address result" },
            });
        }
        assert.equal(ui.inputs.id_latitude.value, latitude, `${name}: stale search cannot replace coordinates`);
        assert.equal(ui.inputs.id_longitude.value, longitude, name);
        assert.equal(ui.map.views.length, viewCount, name);
    }
});

test("dragging a coarse GPS preview cancels an address search and rejects late GPS fixes", () => {
    const ui = picker({ searchPanel: true });
    ui.inputs["use-current-location"].fire("click");
    ui.requests[0].success(position(16.08, 108.23, 2500));
    let cancellations = 0;
    ui.searchPanel.addEventListener("rescue:cancel-address-search", () => { cancellations += 1; });
    ui.marker().setLatLng([16.06, 108.21]);
    ui.marker().handlers.dragend();
    assert.equal(cancellations, 1);
    assert.equal(ui.inputs.id_latitude.value, "16.060000");
    assert.equal(ui.inputs.id_longitude.value, "108.210000");
    assert.equal(ui.activeWatches.size, 0);
    ui.watches[0].success(position(16.09, 108.24));
    assert.equal(ui.inputs.id_latitude.value, "16.060000");
    assert.equal(ui.inputs.id_longitude.value, "108.210000");
});

test("a selected address still fills coordinates and requires confirmation when Leaflet is unavailable", () => {
    const ui = picker({ searchPanel: true, leaflet: false });
    const address = ui.inputs.id_address.value;
    ui.searchPanel.dispatchEvent({
        type: "rescue:address-selected",
        detail: { latitude: 16.0673, longitude: 108.2242, label: "Gợi ý địa chỉ" },
    });
    assert.equal(ui.inputs.id_latitude.value, "16.067300");
    assert.equal(ui.inputs.id_longitude.value, "108.224200");
    assert.equal(ui.inputs.id_address.value, address);
    assert.equal(ui.inputs.id_location_confirmed.checked, false);
    assert.equal(ui.marker(), undefined);
    assert.match(ui.inputs["location-summary"].textContent, /16.067300, 108.224200/);
});

test("a coarse laptop preview cannot be confirmed until the reporter selects a rescue pin", () => {
    const ui = picker();
    const confirmation = ui.inputs.id_location_confirmed;
    ui.inputs["use-current-location"].fire("click");
    ui.requests[0].success(position(16.08, 108.23, 1226));
    assert.ok(ui.marker());
    assert.equal(ui.map.circles.size, 1);
    assert.equal(ui.inputs.id_latitude.value, "");
    assert.equal(confirmation.checked, false);
    confirmation.checked = true;
    confirmation.fire("change");
    assert.equal(confirmation.checked, false);
    assert.match(ui.inputs["location-status"].textContent, /nhập địa chỉ cụ thể và đặt ghim đúng hiện trường/i);

    ui.marker().setLatLng([16.06, 108.21]);
    ui.marker().handlers.dragend();
    assert.equal(ui.inputs.id_latitude.value, "16.060000");
    assert.equal(ui.map.circles.size, 0);
    assert.equal(confirmation.checked, false, "Choosing a pin must not claim the reporter checked the address");
    confirmation.checked = true;
    confirmation.fire("change");
    assert.equal(confirmation.checked, true);
});

test("a 1226 metre preview is visibly different from a selected rescue pin and preserves the real accuracy", () => {
    const ui = picker();
    ui.inputs["use-current-location"].fire("click");
    ui.requests[0].success(position(16.08, 108.23, 1226));
    assert.match(ui.marker().options.icon.className, /is-approximate/);
    assert.match(ui.marker().options.icon.html, /\?/);
    assert.match(ui.marker().options.title, /chưa chọn hiện trường/);
    assert.equal([...ui.map.circles][0].options.radius, 1226);
    assert.equal(ui.inputs.id_latitude.value, "");
    ui.clock.tick(15000);
    assert.match(ui.inputs["location-status"].textContent, /Chưa lấy được vị trí đủ chính xác.*1226 m/);
    assert.equal(ui.inputs.id_latitude.value, "");
    assert.equal(ui.inputs.id_location_confirmed.checked, false);
    ui.marker().setLatLng([16.06, 108.21]);
    ui.marker().handlers.dragend();
    assert.doesNotMatch(ui.marker().options.icon.className, /is-approximate/);
    assert.equal(ui.inputs.id_latitude.value, "16.060000");
    assert.equal(ui.inputs.id_longitude.value, "108.210000");
    assert.equal(ui.inputs.id_location_confirmed.checked, false);
});

test("confirmation requires both a selected rescue pin and a nonblank address", () => {
    const ui = picker();
    const confirmation = ui.inputs.id_location_confirmed;
    confirmation.checked = true;
    confirmation.fire("change");
    assert.equal(confirmation.checked, false, "An address alone is not a selected pin");

    ui.map.handlers.click({ latlng: { lat: 16.06, lng: 108.21 } });
    for (const emptyAddress of ["", "   "]) {
        ui.inputs.id_address.value = emptyAddress;
        ui.inputs.id_address.fire("input");
        confirmation.checked = true;
        confirmation.fire("change");
        assert.equal(confirmation.checked, false, "Coordinates alone are not an address");
    }
    ui.inputs.id_address.value = "Cổng chợ Hàn, 119 Trần Phú, Đà Nẵng";
    ui.inputs.id_address.fire("input");
    assert.equal(confirmation.checked, false);
    confirmation.checked = true;
    confirmation.fire("change");
    assert.equal(confirmation.checked, true);
});

test("changing the address, map pin or coordinate fields invalidates the previous confirmation", () => {
    const edits = {
        address(ui) {
            ui.inputs.id_address.value = "Cổng chợ Hàn, đường Trần Phú";
            ui.inputs.id_address.fire("input");
        },
        map(ui) {
            ui.map.handlers.click({ latlng: { lat: 16.06, lng: 108.21 } });
        },
        drag(ui) {
            ui.marker().setLatLng([16.06, 108.21]);
            ui.marker().handlers.dragend();
        },
        latitudeInput(ui) {
            ui.inputs.id_latitude.value = "16.06";
            ui.inputs.id_latitude.fire("input");
        },
        longitudeChange(ui) {
            ui.inputs.id_longitude.value = "108.21";
            ui.inputs.id_longitude.fire("change");
        },
        incompleteCoordinates(ui) {
            ui.inputs.id_longitude.value = "";
            ui.inputs.id_longitude.fire("input");
        },
    };
    for (const [name, edit] of Object.entries(edits)) {
        const ui = picker({ latitude: "16.05", longitude: "108.20", confirmed: true });
        assert.equal(ui.inputs.id_location_confirmed.checked, true, `${name}: valid restored confirmation`);
        edit(ui);
        assert.equal(ui.inputs.id_location_confirmed.checked, false, `${name}: must be checked again`);
    }
});

test("requesting GPS invalidates a checked location and a precise result never checks it automatically", () => {
    const ui = picker({ latitude: "16.05", longitude: "108.20", confirmed: true });
    const confirmation = ui.inputs.id_location_confirmed;
    assert.equal(confirmation.checked, true);
    ui.inputs["use-current-location"].fire("click");
    assert.equal(confirmation.checked, false, "The old location cannot remain approved while GPS changes it");
    ui.watches[0].success(position(16.06, 108.21, 40));
    assert.equal(ui.inputs.id_latitude.value, "16.060000");
    assert.equal(confirmation.checked, false, "Device accuracy does not verify the rescue address");
    confirmation.checked = true;
    confirmation.fire("change");
    assert.equal(confirmation.checked, true);
});

test("an accurate first GPS fix still waits for the reporter's explicit confirmation", () => {
    const ui = picker();
    ui.inputs["use-current-location"].fire("click");
    ui.requests[0].success(position(16.06, 108.21, 30));
    assert.equal(ui.inputs.id_latitude.value, "16.060000");
    assert.equal(ui.inputs.id_location_confirmed.checked, false);
    ui.inputs.id_location_confirmed.checked = true;
    ui.inputs.id_location_confirmed.fire("change");
    assert.equal(ui.inputs.id_location_confirmed.checked, true);
});

test("redisplaying an otherwise invalid form preserves a checked valid pin but rejects stale incomplete confirmation", () => {
    const valid = picker({ latitude: "16.05", longitude: "108.20", confirmed: true });
    assert.equal(valid.inputs.id_location_confirmed.checked, true);
    assert.equal(valid.marker().getLatLng().lat, 16.05);
    const incomplete = picker({ latitude: "16.05", longitude: "", confirmed: true });
    assert.equal(incomplete.inputs.id_location_confirmed.checked, false);
    assert.equal(incomplete.marker(), undefined);
});

test("one click tries a recent fast fix and a fresh precise watch without locking the button", () => {
    const ui = picker();
    const button = ui.inputs["use-current-location"];
    button.fire("click");
    assert.equal(button.disabled, false);
    assert.equal(button.textContent, "Hủy lấy vị trí");
    assert.equal(button["aria-busy"], "true");
    assert.equal(ui.requests.length, 1);
    assert.equal(ui.requests[0].options.enableHighAccuracy, false);
    assert.equal(ui.requests[0].options.timeout, 3000);
    assert.equal(ui.requests[0].options.maximumAge, 10000);
    assert.equal(ui.watches.length, 1);
    assert.equal(ui.watches[0].options.enableHighAccuracy, true);
    assert.equal(ui.watches[0].options.timeout, 15000);
    assert.equal(ui.watches[0].options.maximumAge, 0);
    ui.requests[0].success(position());
    assert.equal(ui.inputs.id_latitude.value, "16.080000");
    assert.equal(ui.marker().getLatLng().lng, 108.23);
    assert.match(ui.inputs["location-status"].textContent, /Sai số ước tính khoảng 30 m/i);
    assert.equal(button.textContent, "Dùng vị trí hiện tại");
    assert.equal(button["aria-busy"], "false");
    assert.deepEqual(ui.clearedWatches, [0]);
    assert.equal(ui.activeWatches.size, 0);
    assert.equal(ui.clock.pending(), 0);
});

test("a credible coarse fix appears immediately and only better fixes move the pin", () => {
    const ui = picker();
    const button = ui.inputs["use-current-location"];
    button.fire("click");
    ui.requests[0].success(position(16.05, 108.20, 500));
    assert.equal(ui.inputs.id_latitude.value, "16.050000");
    assert.match(ui.inputs["location-status"].textContent, /Sai số ước tính khoảng 500 m/i);
    assert.equal(button["aria-busy"], "true");
    ui.watches[0].success(position(16.06, 108.21, 100));
    assert.equal(ui.inputs.id_latitude.value, "16.060000");
    ui.watches[0].success(position(16.07, 108.22, 700));
    ui.watches[0].success(position(16.07, 108.22, 100));
    assert.equal(ui.inputs.id_latitude.value, "16.060000");
    ui.watches[0].success(position());
    assert.equal(ui.inputs.id_latitude.value, "16.080000");
    assert.equal(button["aria-busy"], "false");
    assert.equal(ui.activeWatches.size, 0);
});

test("a precise watch result can win before the fast request and late callbacks cannot overwrite it", () => {
    const ui = picker();
    ui.inputs["use-current-location"].fire("click");
    ui.watches[0].success(position(16.06, 108.21, 40));
    ui.requests[0].success(position(16.09, 108.24, 10));
    ui.requests[0].failure({ code: 1 });
    ui.watches[0].success(position(16.09, 108.24, 10));
    assert.equal(ui.inputs.id_latitude.value, "16.060000");
    assert.match(ui.inputs["location-status"].textContent, /40 m/);
    assert.equal(ui.clock.pending(), 0);
});

test("an unanswered permission prompt gets time to be accepted and is eventually canceled", () => {
    const ui = picker();
    const button = ui.inputs["use-current-location"];
    button.fire("click");
    ui.clock.tick(7000);
    assert.equal(button["aria-busy"], "true");
    ui.clock.tick(22999);
    assert.equal(button["aria-busy"], "true");
    ui.clock.tick(1);
    assert.equal(button["aria-busy"], "false");
    assert.match(ui.inputs["location-status"].textContent, /thời gian|quyền vị trí/i);
    ui.requests[0].success(position());
    ui.watches[0].success(position());
    assert.equal(ui.inputs.id_latitude.value, "");
    assert.equal(ui.activeWatches.size, 0);
    assert.equal(ui.clock.pending(), 0);
});

test("granted permission bounds fresh acquisition to fifteen seconds without waiting for a failed fast phase", async () => {
    const ui = picker({ permission: "granted" });
    const button = ui.inputs["use-current-location"];
    button.fire("click");
    await flushPermissions();
    assert.equal(ui.watches.length, 1);
    ui.clock.tick(14999);
    assert.equal(button["aria-busy"], "true");
    ui.clock.tick(1);
    assert.equal(button["aria-busy"], "false");
    assert.match(ui.inputs["location-status"].textContent, /Hết thời gian|Chưa (lấy|nhận) được/i);
    assert.equal(ui.activeWatches.size, 0);
    assert.equal(ui.clock.pending(), 0);
});

test("first-time permission asks through one request and starts the precise budget after approval", async () => {
    const ui = picker({ permission: "prompt" });
    const button = ui.inputs["use-current-location"];
    button.fire("click");
    await flushPermissions();
    assert.equal(ui.requests.length, 1);
    assert.equal(ui.watches.length, 0);
    assert.equal(ui.permissionStatus.listenerCount("change"), 1);
    ui.clock.tick(10000);
    assert.equal(button["aria-busy"], "true");
    ui.setPermission("granted");
    assert.equal(ui.watches.length, 1);
    ui.requests[0].success(position(16.05, 108.20, 500));
    assert.equal(ui.inputs.id_latitude.value, "16.050000");
    ui.clock.tick(14999);
    assert.equal(button["aria-busy"], "true");
    ui.clock.tick(1);
    assert.equal(button["aria-busy"], "false");
    assert.match(ui.inputs["location-status"].textContent, /Vị trí gần đúng/i);
    assert.match(ui.inputs["location-status"].textContent, /500 m/);
    assert.equal(ui.permissionStatus.listenerCount("change"), 0);
    assert.equal(ui.activeWatches.size, 0);
});

test("a native result can signal permission approval when no permission change event arrives", async () => {
    const ui = picker({ permission: "prompt" });
    ui.inputs["use-current-location"].fire("click");
    await flushPermissions();
    assert.equal(ui.watches.length, 0);
    ui.requests[0].success(position(16.05, 108.20, 250));
    assert.equal(ui.watches.length, 1);
    assert.equal(ui.inputs.id_latitude.value, "16.050000");
    ui.watches[0].success(position());
    assert.equal(ui.activeWatches.size, 0);
    assert.equal(ui.permissionStatus.listenerCount("change"), 0);
});

test("permission denial stops immediately and ignores later permission or position updates", async () => {
    for (const initialState of ["denied", "prompt"]) {
        const ui = picker({ permission: initialState });
        ui.inputs["use-current-location"].fire("click");
        await flushPermissions();
        if (initialState === "prompt") ui.setPermission("denied");
        assert.equal(ui.inputs["use-current-location"]["aria-busy"], "false");
        assert.match(ui.inputs["location-status"].textContent, /quyền vị trí.*chặn|chặn quyền vị trí/i);
        ui.setPermission("granted");
        for (const request of ui.requests) request.success(position());
        assert.equal(ui.inputs.id_latitude.value, "");
        assert.equal(ui.watches.length, 0);
        assert.equal(ui.permissionStatus.listenerCount("change"), 0);
        assert.equal(ui.clock.pending(), 0);
    }
});

test("rejected or throwing permission queries safely fall back to browser geolocation", async () => {
    for (const permissionQuery of ["reject", "throw"]) {
        const ui = picker({ permissionQuery });
        ui.inputs["use-current-location"].fire("click");
        await flushPermissions();
        assert.equal(ui.requests.length, 1, permissionQuery);
        assert.equal(ui.watches.length, 1, permissionQuery);
        ui.watches[0].success(position());
        assert.equal(ui.inputs.id_latitude.value, "16.080000", permissionQuery);
        assert.equal(ui.clock.pending(), 0, permissionQuery);
    }
});

test("a failed or timed-out fast attempt does not discard the running precise lookup", () => {
    for (const code of [2, 3]) {
        const ui = picker();
        ui.inputs["use-current-location"].fire("click");
        ui.requests[0].failure({ code });
        assert.equal(ui.inputs["use-current-location"]["aria-busy"], "true");
        assert.equal(ui.watches.length, 1);
        ui.watches[0].success(position());
        assert.equal(ui.inputs.id_latitude.value, "16.080000");
        assert.equal(ui.clock.pending(), 0);
    }
});

test("cancel and restart keep only the newest request and watch results", () => {
    const ui = picker();
    const button = ui.inputs["use-current-location"];
    button.fire("click");
    button.fire("click");
    assert.match(ui.inputs["location-status"].textContent, /Đã hủy lấy vị trí/);
    assert.equal(ui.clock.pending(), 0);
    assert.equal(ui.activeWatches.size, 0);
    button.fire("click");
    ui.requests[0].success(position(16.04, 108.19));
    ui.watches[0].success(position(16.04, 108.19));
    ui.watches[0].failure({ code: 1 });
    assert.equal(ui.inputs.id_latitude.value, "");
    ui.watches[1].success(position());
    assert.equal(ui.inputs.id_latitude.value, "16.080000");
    assert.deepEqual(ui.clearedWatches, [0, 1]);
});

test("manual map clicks, drags and coordinate edits take precedence over every pending fix", () => {
    for (const manualAction of ["click", "drag", "input", "change"]) {
        const ui = picker({ latitude: "16.05", longitude: "108.20" });
        ui.inputs["use-current-location"].fire("click");
        if (manualAction === "click") {
            ui.map.handlers.click({ latlng: { lat: 16.06, lng: 108.21 } });
        } else if (manualAction === "drag") {
            ui.marker().setLatLng([16.06, 108.21]);
            ui.marker().handlers.dragend();
        } else {
            ui.inputs.id_latitude.value = "16.06";
            ui.inputs.id_longitude.value = "108.21";
            ui.inputs.id_latitude.fire(manualAction);
        }
        ui.requests[0].success(position());
        ui.watches[0].success(position());
        ui.watches[0].failure({ code: 1 });
        assert.equal(Number(ui.inputs.id_latitude.value), 16.06, manualAction);
        assert.equal(ui.marker().getLatLng().lat, 16.06, manualAction);
        assert.equal(ui.inputs["use-current-location"]["aria-busy"], "false");
        assert.equal(ui.activeWatches.size, 0);
        assert.equal(ui.clock.pending(), 0);
    }
});

test("leaving or hiding the page stops tracking without accumulating lifecycle listeners", async () => {
    for (const leave of ["pagehide", "hidden"]) {
        const ui = picker({ permission: "granted" });
        ui.inputs["use-current-location"].fire("click");
        await flushPermissions();
        if (leave === "pagehide") ui.context.window.fire("pagehide");
        else {
            ui.context.document.hidden = true;
            ui.context.document.visibilityState = "hidden";
            ui.context.document.fire("visibilitychange");
        }
        ui.watches[0].success(position());
        ui.requests[0].success(position());
        assert.equal(ui.inputs.id_latitude.value, "", leave);
        assert.equal(ui.activeWatches.size, 0, leave);
        assert.equal(ui.clock.pending(), 0, leave);
        assert.equal(ui.permissionStatus.listenerCount("change"), 0, leave);
        assert.equal(ui.context.window.listenerCount("pagehide"), 1, leave);
        assert.equal(ui.context.document.listenerCount("visibilitychange"), 1, leave);
        ui.context.document.hidden = false;
        ui.context.document.visibilityState = "visible";
        ui.inputs["use-current-location"].fire("click");
        await flushPermissions();
        assert.equal(ui.context.window.listenerCount("pagehide"), 1, leave);
        assert.equal(ui.context.document.listenerCount("visibilitychange"), 1, leave);
        ui.context.window.fire("pagehide");
        assert.equal(ui.activeWatches.size, 0, leave);
        assert.equal(ui.clock.pending(), 0, leave);
    }
});

test("a coarse best fix survives the deadline and worse results cannot extend acquisition", async () => {
    const ui = picker({ permission: "granted" });
    ui.inputs["use-current-location"].fire("click");
    await flushPermissions();
    ui.requests[0].success(position(16.05, 108.20, 500));
    ui.clock.tick(14000);
    ui.watches[0].success(position(16.04, 108.19, 900));
    ui.clock.tick(1000);
    assert.equal(ui.inputs.id_latitude.value, "16.050000");
    assert.match(ui.inputs["location-status"].textContent, /Vị trí gần đúng/i);
    assert.match(ui.inputs["location-status"].textContent, /500 m/);
    assert.equal(ui.inputs["use-current-location"]["aria-busy"], "false");
    assert.equal(ui.clock.pending(), 0);
    ui.watches[0].success(position());
    assert.equal(ui.inputs.id_latitude.value, "16.050000");
});

test("unreliable or missing accuracy never replaces an existing rescue pin", async () => {
    for (const accuracy of [1200, undefined, NaN, -10]) {
        const ui = picker({ latitude: "16.05", longitude: "108.20", permission: "granted" });
        ui.inputs["use-current-location"].fire("click");
        await flushPermissions();
        ui.requests[0].success({ coords: { latitude: 16.08, longitude: 108.23, accuracy } });
        ui.watches[0].success({ coords: { latitude: 16.08, longitude: 108.23, accuracy } });
        assert.equal(ui.inputs.id_latitude.value, "16.05");
        ui.clock.tick(15000);
        assert.equal(ui.inputs.id_latitude.value, "16.05");
        assert.equal(ui.inputs["use-current-location"]["aria-busy"], "false");
        assert.equal(ui.activeWatches.size, 0);
    }
});

test("a laptop fix with large uncertainty previews the area without submitting unconfirmed coordinates", () => {
    const ui = picker();
    ui.inputs["use-current-location"].fire("click");
    ui.requests[0].success(position(16.08, 108.23, 2500));
    assert.equal(ui.inputs.id_latitude.value, "");
    assert.equal(ui.inputs.id_longitude.value, "");
    assert.ok(ui.marker(), "A coarse result should become a visible draggable preview");
    assert.equal(ui.marker().getLatLng().lat, 16.08);
    assert.equal(ui.marker().options.draggable, true);
    assert.equal(ui.map.circles.size, 1);
    assert.equal([...ui.map.circles][0].options.radius, 2500);
    assert.match(ui.inputs["location-status"].textContent, /2[.,]?500\s*m/);
    assert.match(ui.inputs["location-status"].textContent, /kéo|bấm/i);
    assert.match(ui.inputs["location-summary"].textContent, /chưa chọn/);
});

test("dragging a coarse preview confirms the chosen location and cancels late device fixes", () => {
    const ui = picker();
    ui.inputs["use-current-location"].fire("click");
    ui.requests[0].success(position(16.08, 108.23, 2500));
    const preview = ui.marker();
    assert.ok(preview, "The user needs a preview to adjust");
    preview.setLatLng([16.06, 108.21]);
    preview.handlers.dragend();
    assert.equal(ui.inputs.id_latitude.value, "16.060000");
    assert.equal(ui.inputs.id_longitude.value, "108.210000");
    assert.equal(ui.map.markers.size, 1);
    assert.equal(ui.map.circles.size, 0);
    assert.equal(ui.activeWatches.size, 0);
    assert.equal(ui.clock.pending(), 0);
    ui.watches[0].success(position());
    assert.equal(ui.inputs.id_latitude.value, "16.060000");
});

test("clicking the map confirms a coarse preview and removes its uncertainty circle", () => {
    const ui = picker();
    ui.inputs["use-current-location"].fire("click");
    ui.requests[0].success(position(16.08, 108.23, 2500));
    assert.ok(ui.marker());
    assert.equal(ui.map.circles.size, 1);
    ui.map.handlers.click({ latlng: { lat: 16.06, lng: 108.21 } });
    assert.equal(ui.inputs.id_latitude.value, "16.060000");
    assert.equal(ui.inputs.id_longitude.value, "108.210000");
    assert.equal(ui.map.markers.size, 1);
    assert.equal(ui.map.circles.size, 0);
    assert.equal(ui.activeWatches.size, 0);
});

test("manual coordinates replace an unconfirmed laptop preview without accepting a late fix", () => {
    const ui = picker();
    ui.inputs["use-current-location"].fire("click");
    ui.requests[0].success(position(16.08, 108.23, 2500));
    assert.ok(ui.marker());
    ui.inputs.id_latitude.value = "16.06";
    ui.inputs.id_longitude.value = "108.21";
    ui.inputs.id_longitude.fire("input");
    assert.equal(ui.inputs.id_latitude.value, "16.06");
    assert.equal(ui.inputs.id_longitude.value, "108.21");
    assert.equal(ui.marker().getLatLng().lat, 16.06);
    assert.equal(ui.map.circles.size, 0);
    assert.equal(ui.activeWatches.size, 0);
    ui.watches[0].success(position());
    assert.equal(ui.inputs.id_latitude.value, "16.06");
});

test("an accurate later result replaces a preview and clears its uncertainty circle", () => {
    const ui = picker();
    ui.inputs["use-current-location"].fire("click");
    ui.requests[0].success(position(16.08, 108.23, 2500));
    assert.equal(ui.inputs.id_latitude.value, "");
    assert.equal(ui.map.circles.size, 1);
    ui.watches[0].success(position(16.06, 108.21, 40));
    assert.equal(ui.inputs.id_latitude.value, "16.060000");
    assert.equal(ui.inputs.id_longitude.value, "108.210000");
    assert.equal(ui.map.markers.size, 1);
    assert.equal(ui.map.circles.size, 0);
    assert.equal(ui.activeWatches.size, 0);
});

test("a coarse laptop result never moves an existing selected rescue pin", () => {
    const ui = picker({ latitude: "16.05", longitude: "108.20" });
    ui.inputs["use-current-location"].fire("click");
    ui.requests[0].success(position(16.08, 108.23, 2500));
    assert.equal(ui.inputs.id_latitude.value, "16.05");
    assert.equal(ui.inputs.id_longitude.value, "108.20");
    assert.equal(ui.marker().getLatLng().lat, 16.05);
    assert.equal(ui.marker().getLatLng().lng, 108.20);
    assert.equal(ui.map.markers.size, 1);
    assert.match(ui.inputs["location-status"].textContent, /2[.,]?500\s*m/);
});

test("the coarse preview remains adjustable after the acquisition deadline without claiming no result", async () => {
    const ui = picker({ permission: "granted" });
    ui.inputs["use-current-location"].fire("click");
    await flushPermissions();
    ui.requests[0].success(position(16.08, 108.23, 2500));
    ui.clock.tick(15000);
    assert.equal(ui.inputs.id_latitude.value, "");
    assert.ok(ui.marker());
    assert.equal(ui.map.circles.size, 1);
    assert.equal(ui.activeWatches.size, 0);
    assert.equal(ui.inputs["use-current-location"]["aria-busy"], "false");
    assert.match(ui.inputs["location-status"].textContent, /2[.,]?500\s*m/);
    assert.match(ui.inputs["location-status"].textContent, /kéo|bấm/i);
    assert.doesNotMatch(ui.inputs["location-status"].textContent, /Chưa nhận được vị trí/i);
    ui.marker().setLatLng([16.06, 108.21]);
    ui.marker().handlers.dragend();
    assert.equal(ui.inputs.id_latitude.value, "16.060000");
    assert.equal(ui.map.circles.size, 0);
});

test("both native provider failures stop promptly with a specific safe message", () => {
    for (const code of [2, 3]) {
        for (const first of ["fast", "precise"]) {
            const ui = picker();
            ui.inputs["use-current-location"].fire("click");
            const fast = ui.requests[0];
            const precise = ui.watches[0];
            const sensitiveMessage = "Provider failed at https://provider.invalid?key=private-secret";
            const attempts = first === "fast" ? [fast, precise] : [precise, fast];
            attempts[0].failure({ code, message: sensitiveMessage });
            assert.equal(ui.inputs["use-current-location"]["aria-busy"], "true");
            attempts[1].failure({ code, message: sensitiveMessage });
            assert.equal(ui.inputs["use-current-location"]["aria-busy"], "false", `${code}/${first}`);
            assert.equal(ui.activeWatches.size, 0);
            assert.equal(ui.clock.pending(), 0);
            assert.equal(ui.inputs.id_latitude.value, "");
            assert.doesNotMatch(ui.inputs["location-status"].textContent, /private-secret|provider\.invalid/);
            assert.match(ui.inputs["location-status"].textContent, code === 2 ? /không.*cung cấp.*vị trí|không.*xác định.*vị trí|dịch vụ.*vị trí/i : /hết thời gian|quá thời gian/i);
            precise.success(position());
            assert.equal(ui.inputs.id_latitude.value, "", "Late fixes cannot restart a failed request");
        }
    }
});

test("out-of-area and malformed fixes preserve the old pin while a later valid fix can recover", () => {
    const ui = picker({ latitude: "16.05", longitude: "108.20" });
    ui.inputs["use-current-location"].fire("click");
    ui.requests[0].success(position(17, 108.20));
    ui.watches[0].success({ coords: { latitude: NaN, longitude: 108.23, accuracy: 10 } });
    ui.watches[0].success(null);
    assert.equal(ui.inputs.id_latitude.value, "16.05");
    assert.equal(ui.inputs["use-current-location"]["aria-busy"], "true");
    ui.watches[0].success(position());
    assert.equal(ui.inputs.id_latitude.value, "16.080000");
    assert.equal(ui.clock.pending(), 0);
});

test("a denied native location request stops all acquisition immediately", () => {
    const ui = picker();
    ui.inputs["use-current-location"].fire("click");
    ui.requests[0].failure({ code: 1 });
    assert.equal(ui.inputs["use-current-location"]["aria-busy"], "false");
    assert.match(ui.inputs["location-status"].textContent, /quyền vị trí.*chặn|chặn quyền vị trí/i);
    assert.equal(ui.activeWatches.size, 0);
    assert.equal(ui.clock.pending(), 0);
});

test("a permission query resolving after cancellation cannot start tracking or attach permission listeners", async () => {
    const ui = picker({ permission: "granted" });
    ui.inputs["use-current-location"].fire("click");
    ui.inputs["use-current-location"].fire("click");
    await flushPermissions();
    assert.equal(ui.watches.length, 0);
    assert.equal(ui.permissionStatus.listenerCount("change"), 0);
    assert.equal(ui.clock.pending(), 0);
    assert.equal(ui.inputs["use-current-location"]["aria-busy"], "false");
});

test("missing watchPosition falls back to a bounded fresh high-accuracy request", () => {
    const ui = picker({ watch: false });
    ui.inputs["use-current-location"].fire("click");
    assert.equal(ui.requests.length, 2);
    assert.equal(ui.requests[1].options.enableHighAccuracy, true);
    assert.equal(ui.requests[1].options.timeout, 15000);
    assert.equal(ui.requests[1].options.maximumAge, 0);
    ui.requests[1].success(position());
    assert.equal(ui.inputs.id_latitude.value, "16.080000");
    assert.equal(ui.clock.pending(), 0);
});

test("a synchronously successful watch is cleared even before its zero ID is returned", () => {
    const ui = picker({ watchImmediately(entry) { entry.success(position()); } });
    ui.inputs["use-current-location"].fire("click");
    assert.equal(ui.inputs.id_latitude.value, "16.080000");
    assert.deepEqual(ui.clearedWatches, [0]);
    assert.equal(ui.activeWatches.size, 0);
    assert.equal(ui.clock.pending(), 0);
});

test("unsupported, insecure and synchronous security errors leave a usable location button", () => {
    for (const state of ["unsupported", "insecure", "security-error"]) {
        const ui = picker();
        const button = ui.inputs["use-current-location"];
        if (state === "unsupported") delete ui.context.navigator.geolocation;
        if (state === "insecure") ui.context.window.isSecureContext = false;
        if (state === "security-error") {
            ui.context.navigator.geolocation.getCurrentPosition = () => { throw { name: "SecurityError" }; };
        }
        button.fire("click");
        assert.equal(button.textContent, "Dùng vị trí hiện tại", state);
        assert.equal(button.disabled, false, state);
        assert.equal(ui.clock.pending(), 0, state);
        assert.equal(ui.requests.length, 0, state);
        assert.equal(ui.activeWatches.size, 0, state);
        assert.match(ui.inputs["location-status"].textContent, /nhập vĩ độ và kinh độ/);
    }
});

test("manual coordinates and geolocation remain usable when Leaflet is unavailable", () => {
    const ui = picker({ leaflet: false });
    assert.match(ui.mapElement.textContent, /vẫn gửi được báo cáo/);
    ui.inputs.id_latitude.value = "16.05";
    ui.inputs.id_longitude.value = "108.20";
    ui.inputs.id_latitude.fire("change");
    assert.match(ui.inputs["location-summary"].textContent, /16.050000, 108.200000/);
    assert.match(ui.inputs["location-status"].textContent, /Có thể gửi báo cáo/);
    ui.inputs["use-current-location"].fire("click");
    ui.requests[0].success(position(16.09, 108.24));
    assert.equal(ui.inputs.id_latitude.value, "16.090000");
    assert.equal(ui.inputs.id_longitude.value, "108.240000");
});

test("a Leaflet initialization error leaves GPS and manual coordinates usable", () => {
    for (const mapError of ["map", "tiles"]) {
        const ui = picker({ mapError });
        assert.ok(ui.inputs["use-current-location"].listenerCount("click"), mapError);
        ui.inputs.id_latitude.value = "16.05";
        ui.inputs.id_longitude.value = "108.20";
        ui.inputs.id_longitude.fire("input");
        assert.match(ui.inputs["location-summary"].textContent, /16.050000, 108.200000/);
        ui.inputs["use-current-location"].fire("click");
        assert.equal(ui.requests.length, 1, `${mapError}: one fast request per click`);
        assert.equal(ui.watches.length, 1, `${mapError}: one precise lookup per click`);
        ui.requests[0].success(position(16.09, 108.24, 30));
        assert.equal(ui.inputs.id_latitude.value, "16.090000");
        assert.equal(ui.inputs.id_longitude.value, "108.240000");
        assert.equal(ui.inputs["use-current-location"]["aria-busy"], "false");
    }
});

test("detail map popup treats the report title as text rather than HTML", () => {
    const title = '<img src="x" onerror="alert(1)">';
    const ui = picker({ detailTitle: title });
    assert.equal(ui.marker().popup.textContent, title);
    assert.equal(typeof ui.marker().popup, "object");
    assert.equal(ui.marker().popup.innerHTML, undefined);
});

test("missing Leaflet leaves the case map cards and detail links usable", () => {
    const caseMap = { textContent: "", setAttribute(name, value) { this[name] = value; } };
    const cards = [{ hidden: false, detailLink: { href: "/cases/123/" } }];
    vm.runInNewContext(source, {
        document: {
            querySelector() { return null; },
            querySelectorAll(selector) {
                if (selector === "[data-case-map], [data-cases-map]") return [caseMap];
                if (selector === "[data-map-card]") return cards;
                return [];
            },
        },
    });
    assert.match(caseMap.textContent, /Không tải được bản đồ/);
    assert.equal(caseMap.role, "status");
    assert.equal(cards[0].hidden, false);
    assert.equal(cards[0].detailLink.href, "/cases/123/");
});

function casesMap(locationOptions = {}) {
    function element(tagName = "div") {
        return eventTarget({
            tagName, value: "", textContent: "", dataset: {}, children: [], hidden: false,
            classList: { add() {} },
            appendChild(child) { this.children.push(child); },
            setAttribute(name, value) { this[name] = value; },
            hasAttribute() { return false; },
        });
    }

    const mapElement = element();
    const cases = [
        { id: 1, title: "Ca chó đã cứu", animal_type: "Chó", animal_type_value: "dog", latitude: 16.05, longitude: 108.20, detail_url: "/cases/1/" },
        { id: 2, title: "Ca mèo đã cứu", animal_type: "Mèo", animal_type_value: "cat", latitude: 16.15, longitude: 108.30, detail_url: "/cases/2/" },
    ].map((item) => ({ ...item, address: "Đà Nẵng", status: "Đã cứu thành công", status_value: "rescued", organization: "Đội cứu hộ Đà Nẵng", completed_at_display: "14:30, 02/11/2026", image_url: `/cases/images/${item.id}/` }));
    const cards = cases.map((item) => {
        const card = element();
        const distance = element();
        card.dataset.caseId = String(item.id);
        card.querySelector = () => distance;
        return card;
    });
    const nodes = {
        "map-case-data": { textContent: JSON.stringify(cases) },
        "map-animal-filter": element("select"),
        "nearby-radius": { ...element("select"), value: "10" },
        "find-nearby": element("button"),
        "clear-nearby": { ...element("button"), hidden: true },
        "map-feedback": element(),
    };
    nodes["find-nearby"].textContent = "Tìm ca gần tôi";
    nodes["find-nearby"].disabled = false;
    const focusButtons = cases.map((item) => {
        const button = element("button");
        button.dataset.focusCase = String(item.id);
        return button;
    });
    const map = {
        views: [],
        setView(location, zoom) { this.views.push({ location, zoom }); return this; },
        fitBounds() {}, invalidateSize() {}, on() { return this; },
    };
    const clock = virtualClock();
    const location = locationApi(locationOptions);
    const layer = {
        markers: [], addTo() { return this; }, clearLayers() { this.markers = []; },
    };
    const context = {
        document: eventTarget({
            hidden: false, visibilityState: "visible",
            querySelector(selector) { return selector === "[data-cases-map]" ? mapElement : null; },
            querySelectorAll(selector) { return selector === "[data-map-card]" ? cards : selector === "[data-focus-case]" ? focusButtons : []; },
            getElementById(id) { return nodes[id] || null; },
            createElement: element,
        }),
        window: eventTarget({ setTimeout: clock.setTimeout, clearTimeout: clock.clearTimeout }),
        navigator: location.navigator,
        L: {
            latLngBounds() { return { contains() { return true; } }; },
            map() { return map; }, divIcon() { return {}; },
            tileLayer() { return { on() { return this; }, addTo() { return this; } }; },
            layerGroup() { return layer; },
            marker(location) {
                return {
                    location,
                    getLatLng() { return this.location; },
                    openPopup() { this.opened = true; return this; },
                    bindPopup(popup) { this.popup = popup; return this; },
                    addTo(target) { target.markers.push(this); return this; },
                };
            },
            circleMarker() { return { addTo() { return this; }, bindPopup() { return this; }, remove() {} }; },
        },
    };
    vm.runInNewContext(source, context);
    clock.tick(0);
    return { nodes, layer, cards, clock, context, map, focusButtons, ...location };
}

test("successful-case map works without a status dropdown and preserves animal, nearby and detail actions", () => {
    const { nodes, layer, cards, requests } = casesMap();
    assert.equal(layer.markers.length, 2);
    assert.match(nodes["map-feedback"].textContent, /2 ca cứu hộ thành công/);
    const detailLink = layer.markers[0].popup.children.at(-1);
    assert.equal(detailLink.tagName, "a");
    assert.equal(detailLink.href, "/cases/1/");
    assert.equal(detailLink.handlers.click, undefined);

    nodes["map-animal-filter"].value = "cat";
    nodes["map-animal-filter"].handlers.change();
    assert.equal(layer.markers.length, 1);
    assert.equal(cards[0].hidden, true);
    assert.equal(cards[1].hidden, false);

    nodes["find-nearby"].handlers.click();
    requests[0].success(position(16.055, 108.205));
    assert.equal(nodes["find-nearby"].disabled, false);
    assert.equal(nodes["clear-nearby"].hidden, false);
    assert.equal(layer.markers.length, 0);
    assert.match(nodes["map-feedback"].textContent, /0 ca cứu hộ thành công trong bán kính 10 km/);

    nodes["clear-nearby"].handlers.click();
    assert.equal(nodes["clear-nearby"].hidden, true);
    assert.equal(layer.markers.length, 1);
    assert.equal(cards[0].hidden, true);
    assert.equal(cards[1].hidden, false);
});

test("nearby lookup progressively filters successful cases and clearing cancels every late fix", () => {
    const { nodes, clock, requests, watches, activeWatches, layer } = casesMap();
    nodes["find-nearby"].handlers.click();
    requests[0].success(position(16.055, 108.205, 500));
    assert.equal(nodes["clear-nearby"].hidden, false);
    assert.equal(nodes["find-nearby"]["aria-busy"], "true");
    assert.match(nodes["map-feedback"].textContent, /500 m/);
    assert.equal(layer.markers.length, 1);
    nodes["clear-nearby"].handlers.click();
    requests[0].success(position());
    watches[0].success(position());
    assert.equal(nodes["clear-nearby"].hidden, true);
    assert.equal(nodes["find-nearby"]["aria-busy"], "false");
    assert.equal(layer.markers.length, 2);
    assert.equal(activeWatches.size, 0);
    assert.equal(clock.pending(), 0);
});

test("nearby lookup respects its acquisition deadline and cleans up a hidden page", async () => {
    const ui = casesMap({ permission: "granted" });
    ui.nodes["find-nearby"].handlers.click();
    await flushPermissions();
    ui.clock.tick(15000);
    assert.equal(ui.nodes["find-nearby"]["aria-busy"], "false");
    assert.equal(ui.nodes["clear-nearby"].hidden, true);
    assert.equal(ui.activeWatches.size, 0);
    ui.watches[0].success(position());
    assert.equal(ui.nodes["clear-nearby"].hidden, true);
    ui.nodes["find-nearby"].handlers.click();
    await flushPermissions();
    ui.context.document.hidden = true;
    ui.context.document.visibilityState = "hidden";
    ui.context.document.fire("visibilitychange");
    ui.watches[1].success(position());
    assert.equal(ui.nodes["clear-nearby"].hidden, true);
    assert.equal(ui.activeWatches.size, 0);
    assert.equal(ui.clock.pending(), 0);
});

test("nearby lookup can use a visitor position outside the reporting service area", () => {
    const { nodes, requests } = casesMap();
    nodes["find-nearby"].handlers.click();
    requests[0].success(position(16.26, 108.20));
    assert.equal(requests.length, 1);
    assert.equal(nodes["clear-nearby"].hidden, false);
    assert.match(nodes["map-feedback"].textContent, /trong bán kính 10 km/);
});

test("an imprecise nearby lookup does not offer report-only pin confirmation controls", () => {
    const ui = casesMap();
    ui.nodes["find-nearby"].handlers.click();
    ui.requests[0].success(position(16.08, 108.23, 2500));
    assert.equal(ui.nodes["clear-nearby"].hidden, true);
    assert.match(ui.nodes["map-feedback"].textContent, /2[.,]?500\s*m/);
    assert.doesNotMatch(ui.nodes["map-feedback"].textContent, /kéo ghim|bấm bản đồ.*xác nhận/i);
    ui.clock.tick(15000);
    assert.equal(ui.nodes["clear-nearby"].hidden, true);
    assert.equal(ui.nodes["find-nearby"]["aria-busy"], "false");
    assert.doesNotMatch(ui.nodes["map-feedback"].textContent, /kéo ghim|bấm bản đồ.*xác nhận/i);
});

test("successful marker shows the rescue photo and public details with a native detail link", () => {
    const ui = casesMap();
    const marker = ui.layer.markers[0];
    const popup = marker.popup;
    assert.equal(popup.children[0].tagName, "img");
    assert.equal(popup.children[0].src, "/cases/images/1/");
    const text = popup.children.map((node) => node.textContent).join(" ");
    for (const expected of ["#1 · Ca chó đã cứu", "Chó · Đã cứu thành công", "Đà Nẵng", "Đơn vị cứu hộ: Đội cứu hộ Đà Nẵng", "14:30, 02/11/2026"]) {
        assert.ok(text.includes(expected), expected);
    }
    assert.equal(popup.children.at(-1).href, "/cases/1/");
    ui.focusButtons[0].fire("click");
    assert.equal(marker.opened, true);
    assert.equal(ui.map.views.at(-1).zoom, 16);
});
