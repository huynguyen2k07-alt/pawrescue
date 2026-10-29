const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "../static/js/maps.js"), "utf8");

function picker({ leaflet = true, latitude = "", longitude = "", detailTitle = null, maptilerKey = "" } = {}) {
    function element(value = "") {
        const classes = new Set();
        return {
            value, textContent: "", dataset: {}, handlers: {}, children: [],
            classList: {
                add(name) { classes.add(name); },
                remove(name) { classes.delete(name); },
                contains(name) { return classes.has(name); },
            },
            appendChild(child) { this.children.push(child); },
            setAttribute(name, value) { this[name] = value; },
            hasAttribute(name) { return name === "data-map-picker"; },
            addEventListener(name, handler) { this.handlers[name] = handler; },
            fire(name) { this.handlers[name](); },
        };
    }

    const mapElement = element();
    mapElement.dataset.maptilerKey = maptilerKey;
    const detailElement = detailTitle === null ? null : element();
    if (detailElement) {
        detailElement.dataset = { latitude: "16.05", longitude: "108.20", title: detailTitle };
    }
    const inputs = {
        id_latitude: element(latitude),
        id_longitude: element(longitude),
        id_address: element("430 Hùng Vương, Hải Châu, Đà Nẵng"),
        "use-current-location": element(),
        "location-status": element(),
        "location-summary": element(),
    };
    const map = {
        handlers: {}, markers: new Set(), views: [], tileLayers: [],
        on(name, handler) { this.handlers[name] = handler; return this; },
        setView(location, zoom) { this.views.push({ location, zoom }); return this; },
        removeLayer(layer) { this.markers.delete(layer); },
        invalidateSize() {},
    };
    const context = {
        document: {
            querySelector(selector) {
                if (selector === "[data-map-picker]") return mapElement;
                if (selector === "[data-case-map]") return detailElement;
                return null;
            },
            querySelectorAll() { return []; },
            getElementById(id) { return inputs[id] || null; },
            createElement: element,
        },
        window: { setTimeout(callback) { callback(); } },
        navigator: { geolocation: {
            getCurrentPosition(success, failure) {
                context.locationSuccess = success;
                context.locationFailure = failure;
            },
        } },
    };
    if (leaflet) {
        context.L = {
            latLngBounds() { return { contains() { return true; } }; },
            map() { return map; },
            tileLayer(url) { return { on() { return this; }, addTo(target) { target.tileLayers.push(url); return this; } }; },
            control: { layers() { return { addTo() {} }; } },
            divIcon() { return {}; },
            marker(location) {
                return {
                    location, handlers: {},
                    addTo(target) { target.markers.add(this); return this; },
                    on(name, handler) { this.handlers[name] = handler; return this; },
                    setLatLng(next) { this.location = next; return this; },
                    getLatLng() { return { lat: this.location[0], lng: this.location[1] }; },
                    bindPopup(content) { this.popup = content; return this; },
                };
            },
        };
    }
    vm.runInNewContext(source, context);
    return { map, mapElement, inputs, context, marker: () => [...map.markers][0] };
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

test("geolocation updates the pin and re-enables the button on success or failure", () => {
    const ui = picker();
    const button = ui.inputs["use-current-location"];
    button.fire("click");
    assert.equal(button.disabled, true);
    ui.context.locationSuccess({ coords: { latitude: 16.08, longitude: 108.23 } });
    assert.equal(ui.inputs.id_latitude.value, "16.080000");
    assert.equal(ui.marker().getLatLng().lng, 108.23);
    assert.equal(button.disabled, false);
    button.fire("click");
    ui.context.locationFailure();
    assert.equal(button.disabled, false);
    assert.match(ui.inputs["location-status"].textContent, /nhập vĩ độ và kinh độ/);
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
    ui.context.locationSuccess({ coords: { latitude: 16.09, longitude: 108.24 } });
    assert.equal(ui.inputs.id_latitude.value, "16.090000");
    assert.equal(ui.inputs.id_longitude.value, "108.240000");
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
