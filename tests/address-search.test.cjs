const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "../static/js/address-search.js"), "utf8");

function eventTarget(target = {}) {
    const listeners = new Map();
    return Object.assign(target, {
        addEventListener(type, callback) {
            if (!listeners.has(type)) listeners.set(type, new Set());
            listeners.get(type).add(callback);
        },
        dispatchEvent(event) {
            for (const callback of [...(listeners.get(event.type) || [])]) callback(event);
            return true;
        },
        fire(type) { this.dispatchEvent({ type }); },
        listenerCount(type) { return (listeners.get(type) || new Set()).size; },
    });
}

function virtualClock() {
    let now = 0;
    let nextId = 0;
    const timers = new Map();
    return {
        setTimeout(callback, delay) {
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

function element(tagName = "div") {
    const node = eventTarget({
        tagName, value: "", textContent: "", dataset: {}, children: [], disabled: false,
        appendChild(child) { this.children.push(child); },
        replaceChildren(...children) { this.children = children; },
        setAttribute(name, value) { this[name] = value; },
    });
    Object.defineProperty(node, "innerHTML", {
        set() { throw new Error("Address labels must never be parsed as HTML"); },
    });
    return node;
}

function deferred() {
    let resolve;
    let reject;
    const promise = new Promise((accept, fail) => { resolve = accept; reject = fail; });
    return { promise, resolve, reject };
}

function response(payload = { results: [suggestion()] }, options = {}) {
    return {
        ok: true, status: 200, redirected: false,
        headers: { get() { return "application/json; charset=utf-8"; } },
        json() { return Promise.resolve(payload); },
        ...options,
    };
}

function suggestion(overrides = {}) {
    return { label: "Cổng chợ Hàn, 119 Trần Phú, Đà Nẵng", latitude: 16.0673, longitude: 108.2242, ...overrides };
}

function picker(options = {}) {
    const panel = element();
    panel.dataset = { searchUrl: "/locations/search/", csrfToken: "test-csrf-token", ...options.dataset };
    const nodes = {
        id_address: element("textarea"),
        "find-address": element("button"),
        "address-search-results": element(),
        "address-search-status": element("p"),
        id_location_confirmed: element("input"),
    };
    nodes.id_address.value = "  Cổng chợ Hàn\n119 Trần Phú, Đà Nẵng  ";
    nodes.id_location_confirmed.checked = true;
    const clock = virtualClock();
    const requests = [];
    const events = [];
    const sequence = [];
    for (const type of ["rescue:address-search-start", "rescue:address-selected"]) {
        panel.addEventListener(type, (event) => { events.push(event); sequence.push(type); });
    }
    const context = {
        URL, URLSearchParams, AbortController,
        CustomEvent: class {
            constructor(type, settings = {}) {
                this.type = type;
                this.bubbles = Boolean(settings.bubbles);
                this.detail = settings.detail;
            }
        },
        window: eventTarget({
            location: { href: "https://rescue.example/report/", origin: "https://rescue.example" },
            setTimeout: clock.setTimeout, clearTimeout: clock.clearTimeout,
        }),
        document: eventTarget({
            hidden: false, visibilityState: "visible",
            querySelector() { return options.missingPanel ? null : panel; },
            getElementById(id) { return options.missingNode === id ? null : nodes[id] || null; },
            createElement: element,
        }),
        fetch(url, settings) {
            if (options.throwFetch) throw new Error("Private provider failure key=do-not-expose");
            const pending = deferred();
            requests.push({ url, settings, ...pending });
            sequence.push("fetch");
            return pending.promise;
        },
    };
    if (options.noFetch) delete context.fetch;
    if (options.noAbortController) delete context.AbortController;
    vm.runInNewContext(source, context);
    return {
        panel, nodes, requests, events, sequence, clock, context,
        search() { nodes["find-address"].fire("click"); },
        results() { return nodes["address-search-results"].children; },
        status() { return nodes["address-search-status"].textContent; },
        selected() { return events.filter((event) => event.type === "rescue:address-selected"); },
    };
}

async function flush() {
    await new Promise((resolve) => setImmediate(resolve));
}

async function resolveSearch(ui, payload = { results: [suggestion()] }, options) {
    ui.requests.at(-1).resolve(response(payload, options));
    await flush();
}

function assertIdle(ui) {
    assert.equal(ui.nodes["find-address"].disabled, false);
    assert.equal(ui.nodes["find-address"]["aria-busy"], "false");
    assert.equal(ui.panel["aria-busy"], "false");
    assert.equal(ui.clock.pending(), 0);
}

test("loading, typing and Enter in the address never start a search or submit the form", () => {
    const ui = picker();
    assert.equal(ui.nodes["find-address"].type, "button");
    assert.equal(ui.requests.length, 0);
    assert.equal(ui.clock.pending(), 0);
    ui.nodes.id_address.value = "Cổng nhà\nđường Trần Phú";
    ui.nodes.id_address.fire("input");
    ui.nodes.id_address.fire("keydown");
    assert.equal(ui.nodes.id_address.value, "Cổng nhà\nđường Trần Phú");
    assert.equal(ui.nodes.id_address.listenerCount("keydown"), 0);
    assert.equal(ui.requests.length, 0);
});

test("one deliberate click posts a trimmed address and CSRF only to this origin", async () => {
    const ui = picker();
    ui.search();
    ui.search();
    assert.equal(ui.requests.length, 1);
    const { url, settings } = ui.requests[0];
    assert.equal(url, "https://rescue.example/locations/search/");
    assert.equal(settings.method, "POST");
    assert.equal(settings.headers.Accept, "application/json");
    assert.equal(settings.headers["X-CSRFToken"], "test-csrf-token");
    assert.equal(settings.body.get("address"), "Cổng chợ Hàn\n119 Trần Phú, Đà Nẵng");
    assert.deepEqual([...settings.body.keys()], ["address"]);
    assert.equal(settings.credentials, "same-origin");
    assert.equal(settings.cache, "no-store");
    assert.equal(settings.redirect, "error");
    assert.equal(settings.signal.aborted, false);
    assert.equal(ui.nodes["find-address"].disabled, true);
    assert.equal(ui.nodes["find-address"]["aria-busy"], "true");
    assert.equal(ui.panel["aria-busy"], "true");
    assert.deepEqual(ui.sequence, ["rescue:address-search-start", "fetch"]);
    assert.equal(ui.events[0].bubbles, true);
    await resolveSearch(ui);
    assertIdle(ui);
});

test("labels remain literal text and results need an explicit selection without changing the address", async () => {
    const ui = picker();
    const address = ui.nodes.id_address.value;
    const label = '<img src=x onerror="alert(1)"> & Cổng chợ Hàn';
    ui.search();
    await resolveSearch(ui, { results: [suggestion({ label }), suggestion({ label: "Gợi ý thứ hai" })] });
    assert.equal(ui.results().length, 2);
    assert.equal(ui.selected().length, 0);
    assert.equal(ui.nodes.id_address.value, address);
    assert.equal(ui.nodes.id_location_confirmed.checked, true, "maps owns location confirmation");
    const button = ui.results()[0];
    assert.equal(button.type, "button");
    assert.equal(button.className, "address-search-result");
    assert.equal(button.children[0].textContent, label);
    assert.match(button.children[1].textContent, /kiểm tra.*ghim/);
    button.fire("click");
    assert.equal(ui.selected().length, 1);
    assert.equal(ui.selected()[0].bubbles, true);
    assert.deepEqual({ ...ui.selected()[0].detail }, suggestion({ label }));
    assert.equal(ui.nodes.id_address.value, address);
    assert.equal(ui.results().length, 0);
    assert.match(ui.status(), /kiểm tra.*ghim.*xác nhận/i);
    button.fire("click");
    assert.equal(ui.selected().length, 1, "Detached result buttons cannot choose a stale pin");
});

test("up to five results, 500-character labels and both service-area boundaries are valid", async () => {
    const ui = picker();
    ui.search();
    await resolveSearch(ui, { results: [
        suggestion({ label: "x".repeat(500), latitude: 15.85, longitude: 107.75 }),
        suggestion({ latitude: 16.25, longitude: 108.35 }),
        suggestion(), suggestion(), suggestion(),
    ] });
    assert.equal(ui.results().length, 5);
    assert.equal(ui.results()[0].children[0].textContent.length, 500);
});

test("every result is validated before any suggestion is shown", async () => {
    const invalidPayloads = [
        null, [], {}, { results: null }, { results: "bad" },
        { results: Array.from({ length: 6 }, () => suggestion()) },
        ...[null, [], "bad", {},
            suggestion({ label: "" }), suggestion({ label: "  " }), suggestion({ label: 3 }),
            suggestion({ label: "x".repeat(501) }),
            suggestion({ latitude: "16.06" }), suggestion({ longitude: "108.2" }),
            suggestion({ latitude: null }), suggestion({ longitude: NaN }),
            suggestion({ latitude: Infinity }), suggestion({ longitude: -Infinity }),
            suggestion({ latitude: 15.8499 }), suggestion({ latitude: 16.2501 }),
            suggestion({ longitude: 107.7499 }), suggestion({ longitude: 108.3501 }),
        ].map((bad) => ({ results: [suggestion(), bad] })),
    ];
    for (const payload of invalidPayloads) {
        const ui = picker();
        ui.search();
        await resolveSearch(ui, payload);
        assert.equal(ui.results().length, 0, JSON.stringify(payload));
        assert.equal(ui.selected().length, 0);
        assert.match(ui.status(), /Không tìm được địa chỉ/);
        assertIdle(ui);
    }
});

test("an empty result explains how to refine the address or choose a map pin", async () => {
    const ui = picker();
    ui.search();
    await resolveSearch(ui, { results: [] });
    assert.equal(ui.results().length, 0);
    assert.match(ui.status(), /Chưa tìm thấy.*Đà Nẵng/);
    assert.match(ui.status(), /chọn ghim/);
    assertIdle(ui);
});

test("network errors preserve the address and allow a fresh attempt", async () => {
    const ui = picker();
    const address = ui.nodes.id_address.value;
    ui.search();
    ui.requests[0].reject(new Error("Private upstream URL https://provider.invalid?key=do-not-expose"));
    await flush();
    assert.match(ui.status(), /Không tìm được địa chỉ/);
    assert.doesNotMatch(ui.status(), /provider|do-not-expose/);
    assert.equal(ui.nodes.id_address.value, address);
    assertIdle(ui);
    ui.search();
    await resolveSearch(ui);
    assert.equal(ui.requests.length, 2);
    assert.equal(ui.results().length, 1);
    assertIdle(ui);
});

test("a synchronous fetch failure remains bounded and retryable", async () => {
    const ui = picker({ throwFetch: true });
    ui.search();
    await flush();
    assert.match(ui.status(), /Không tìm được địa chỉ/);
    assert.doesNotMatch(ui.status(), /do-not-expose/);
    assertIdle(ui);
    ui.search();
    await flush();
    assertIdle(ui);
});

test("HTTP, permission and provider failures use safe Vietnamese messages and never show their body", async () => {
    const expected = new Map([
        [400, /Địa chỉ chưa hợp lệ/], [401, /tải lại trang/], [403, /tải lại trang/],
        [429, /đợi một lúc/], [503, /chưa sẵn sàng/], [500, /Không tìm được địa chỉ/],
    ]);
    for (const [status, message] of expected) {
        const ui = picker();
        let readBody = false;
        ui.search();
        await resolveSearch(ui, null, {
            status, ok: false,
            json() { readBody = true; return Promise.resolve({ error: "private provider key" }); },
        });
        assert.equal(readBody, false);
        assert.match(ui.status(), message);
        assert.equal(ui.results().length, 0);
        assertIdle(ui);
        ui.search();
        assert.equal(ui.requests.length, 2);
        await resolveSearch(ui);
        assert.equal(ui.results().length, 1);
    }
});

test("redirected, non-JSON and unreadable successful responses cannot become suggestions", async () => {
    for (const bad of [
        { redirected: true },
        { headers: { get() { return "text/html"; } } },
        { headers: { get() { return null; } } },
        { json() { return Promise.reject(new Error("private response failure")); } },
    ]) {
        const ui = picker();
        ui.search();
        await resolveSearch(ui, undefined, bad);
        assert.equal(ui.results().length, 0);
        assert.match(ui.status(), /Không tìm được địa chỉ/);
        assert.doesNotMatch(ui.status(), /private/);
        assertIdle(ui);
    }
});

test("foreign, malformed and credential-bearing endpoints never receive an address or CSRF", () => {
    for (const searchUrl of [
        "", "https://foreign.invalid/search", "//foreign.invalid/search", "javascript:alert(1)",
        "data:application/json,{}", "http://[", "https://person:password@rescue.example/locations/search/",
        "http://rescue.example/locations/search/",
    ]) {
        const ui = picker({ dataset: { searchUrl } });
        ui.search();
        assert.equal(ui.requests.length, 0, searchUrl);
        assert.equal(ui.events.length, 0, searchUrl);
        assert.match(ui.status(), /Chưa thể tìm địa chỉ/);
        assertIdle(ui);
    }
    const local = picker({ dataset: { searchUrl: "https://rescue.example/locations/search/" } });
    local.search();
    assert.equal(local.requests.length, 1);
});

test("blank addresses and unavailable request support fail locally without starting GPS cancellation", () => {
    for (const options of [{ noFetch: true }, { noAbortController: true }, { dataset: { csrfToken: "" } }]) {
        const ui = picker(options);
        ui.search();
        assert.equal(ui.requests.length, 0);
        assert.equal(ui.events.length, 0);
        assert.match(ui.status(), /Chưa thể tìm địa chỉ/);
        assertIdle(ui);
    }
    const blank = picker();
    blank.nodes.id_address.value = " \n ";
    blank.search();
    assert.equal(blank.requests.length, 0);
    assert.equal(blank.events.length, 0);
    assert.match(blank.status(), /Nhập địa chỉ/);
});

test("a seven-second deadline aborts the request and releases the button even if fetch ignores abort", async () => {
    const ui = picker();
    ui.search();
    ui.clock.tick(6999);
    assert.equal(ui.nodes["find-address"].disabled, true);
    ui.clock.tick(1);
    assert.equal(ui.requests[0].settings.signal.aborted, true);
    assert.match(ui.status(), /quá thời gian/);
    assertIdle(ui);
    ui.search();
    assert.equal(ui.requests.length, 2);
    ui.requests[0].resolve(response({ results: [suggestion({ label: "Stale result" })] }));
    await flush();
    assert.equal(ui.results().length, 0);
    assert.equal(ui.nodes["find-address"].disabled, true, "An old finally cannot release a new request");
    await resolveSearch(ui, { results: [suggestion({ label: "Fresh result" })] });
    assert.equal(ui.results()[0].children[0].textContent, "Fresh result");
    assertIdle(ui);
});

test("the deadline also covers an unresolved JSON body and ignores its late completion", async () => {
    const ui = picker();
    const body = deferred();
    ui.search();
    ui.requests[0].resolve(response(null, { json() { return body.promise; } }));
    await flush();
    ui.clock.tick(7000);
    assert.match(ui.status(), /quá thời gian/);
    assertIdle(ui);
    body.resolve({ results: [suggestion()] });
    await flush();
    assert.equal(ui.results().length, 0);
    assert.equal(ui.selected().length, 0);
});

test("editing the address or a manual-position event wins over every late response", async () => {
    for (const cancel of [
        (ui) => { ui.nodes.id_address.value = "Mốc mới"; ui.nodes.id_address.fire("input"); },
        (ui) => ui.panel.fire("rescue:cancel-address-search"),
    ]) {
        const ui = picker();
        ui.search();
        cancel(ui);
        assert.equal(ui.requests[0].settings.signal.aborted, true);
        assertIdle(ui);
        await resolveSearch(ui);
        assert.equal(ui.results().length, 0);
        assert.equal(ui.selected().length, 0);
        ui.search();
        await resolveSearch(ui);
        const staleButton = ui.results()[0];
        cancel(ui);
        staleButton.fire("click");
        assert.equal(ui.results().length, 0);
        assert.equal(ui.selected().length, 0);
    }
});

test("hiding or leaving the page cancels pending searches and still permits retry after return", async () => {
    for (const lifecycle of ["pagehide", "visibilitychange"]) {
        const ui = picker();
        ui.search();
        if (lifecycle === "pagehide") ui.context.window.fire(lifecycle);
        else {
            ui.context.document.hidden = true;
            ui.context.document.visibilityState = "hidden";
            ui.context.document.fire(lifecycle);
        }
        assert.equal(ui.requests[0].settings.signal.aborted, true);
        assertIdle(ui);
        ui.requests[0].reject(new Error("late cancellation rejection"));
        await flush();
        assert.equal(ui.results().length, 0);
        assert.equal(ui.status(), "");
        ui.context.document.hidden = false;
        ui.context.document.visibilityState = "visible";
        ui.context.window.fire("pageshow");
        ui.context.document.fire("visibilitychange");
        ui.search();
        await resolveSearch(ui);
        assert.equal(ui.results().length, 1);
        assertIdle(ui);
    }
});

test("lifecycle cancellation removes completed suggestions and invalidates detached selections", async () => {
    const ui = picker();
    ui.search();
    await resolveSearch(ui);
    const staleButton = ui.results()[0];
    ui.context.window.fire("pagehide");
    staleButton.fire("click");
    assert.equal(ui.results().length, 0);
    assert.equal(ui.selected().length, 0);
    assertIdle(ui);
});

test("a synchronous cancellation from search-start prevents the outgoing request", () => {
    const ui = picker();
    ui.panel.addEventListener("rescue:address-search-start", () => ui.panel.fire("rescue:cancel-address-search"));
    ui.search();
    assert.equal(ui.requests.length, 0);
    assertIdle(ui);
});

test("pages without the panel or required fields keep working", () => {
    for (const options of [{ missingPanel: true }, { missingNode: "id_address" }, { missingNode: "find-address" }]) {
        const ui = picker(options);
        ui.search();
        assert.equal(ui.requests.length, 0);
        assert.equal(ui.clock.pending(), 0);
    }
});
