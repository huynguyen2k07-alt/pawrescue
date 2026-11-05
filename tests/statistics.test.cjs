const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const SOURCE = path.join(__dirname, "../static/js/public-statistics.js");
const INITIAL_VERSION = "a".repeat(64);
const NEW_VERSION = "b".repeat(64);
const PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aB1cAAAAASUVORK5CYII=";
const CHECKED_AT = "2026-10-31T06:35:00+07:00";

function element(tagName = "div") {
    const attributes = new Map();
    const classes = new Set();
    let text = "";
    let source = "";
    return {
        tagName, dataset: {}, children: [], handlers: {}, open: false,
        disabled: false, replaceCount: 0, sourceWrites: 0,
        get textContent() { return text; },
        set textContent(value) { text = String(value); },
        get src() { return source; },
        set src(value) { source = String(value); this.sourceWrites += 1; },
        set innerHTML(_value) { throw new Error("Unsafe innerHTML assignment"); },
        classList: {
            add(name) { classes.add(name); },
            remove(name) { classes.delete(name); },
            toggle(name, present) {
                if (present ?? !classes.has(name)) classes.add(name); else classes.delete(name);
            },
        },
        append(...children) { this.children.push(...children); },
        appendChild(child) { this.children.push(child); return child; },
        replaceChildren(...children) { this.replaceCount += 1; this.children = children; },
        setAttribute(name, value) { attributes.set(name, String(value)); this[name] = String(value); },
        getAttribute(name) { return attributes.get(name) ?? this[name] ?? null; },
        removeAttribute(name) { attributes.delete(name); },
        addEventListener(name, callback) { this.handlers[name] = callback; },
    };
}

function payload(values = {}) {
    return {
        version: NEW_VERSION, checked_at: CHECKED_AT, time_zone: "Asia/Ho_Chi_Minh",
        total: 12, rescued_count: 4, daily_average: 1,
        window_label: "25/10/2026 – 31/10/2026",
        status_chart: PNG, daily_chart: PNG,
        status_rows: [
            { label: "Đã xác nhận", count: 6 },
            { label: "Đã cứu thành công", count: 4 },
            { label: "Đã hủy", count: 2 },
        ],
        daily_rows: Array.from({ length: 7 }, (_, index) => ({ date: `2026-10-${25 + index}`, count: 1 })),
        ...values,
    };
}

async function settle() {
    await new Promise(setImmediate);
    await new Promise(setImmediate);
}

async function statisticsUI({ hidden = false, online = true, present = true } = {}) {
    const root = element("section");
    root.dataset = {
        url: "/statistics/live/", version: INITIAL_VERSION, timeZone: "Asia/Ho_Chi_Minh",
        pollInterval: "5000", checkedAt: "2026-10-31T06:30:00+07:00",
    };
    const names = ["total", "rescued", "average", "status-chart", "daily-chart", "window",
        "status-rows", "daily-rows", "status", "checked-at", "refresh"];
    const nodes = Object.fromEntries(names.map((name) => [name, element()]));
    nodes.total.textContent = "10";
    nodes.rescued.textContent = "3";
    nodes.average.textContent = "0,50";
    nodes.window.textContent = "Khoảng thời gian ban đầu";
    nodes["status-chart"].src = "/initial-status.png";
    nodes["daily-chart"].src = "/initial-daily.png";
    for (const name of ["status-rows", "daily-rows"]) nodes[name].appendChild(element("tr"));
    const details = [element("details"), element("details")];
    details.forEach((item) => { item.open = true; });
    root.children = details;
    root.querySelector = (selector) => {
        const match = selector.match(/^\[data-statistics-(.+)\]$/);
        return match ? nodes[match[1]] || null : null;
    };

    let now = 0;
    let timerId = 0;
    let jsonCalls = 0;
    const timers = new Map();
    const requests = [];
    const responses = [];
    const errors = [];
    const document = {
        hidden, handlers: {},
        querySelector(selector) { return present && selector === "[data-public-statistics]" ? root : null; },
        createElement: element,
        createDocumentFragment() { return element("fragment"); },
        addEventListener(name, callback) { this.handlers[name] = callback; },
    };
    const navigator = { onLine: online };
    const window = {
        location: { origin: "http://localhost:8000", href: "http://localhost:8000/" },
        handlers: {},
        setTimeout(callback, delay = 0) {
            const id = ++timerId;
            timers.set(id, { callback, due: now + Number(delay) });
            return id;
        },
        clearTimeout(id) { timers.delete(id); },
        addEventListener(name, callback) { this.handlers[name] = callback; },
    };
    const fetch = async (url, options = {}) => {
        requests.push({ url: String(url), options });
        const next = responses.shift() || { status: 304 };
        if (next instanceof Error) throw next;
        if (next.pending) {
            return new Promise((_resolve, reject) => {
                options.signal.addEventListener("abort", () => {
                    const error = new Error("Request aborted");
                    error.name = "AbortError";
                    reject(error);
                }, { once: true });
            });
        }
        const status = next.status ?? 200;
        return {
            status, ok: status >= 200 && status < 300,
            headers: { get(name) {
                if (name.toLowerCase() === "x-statistics-checked-at") return next.checkedAt || CHECKED_AT;
                if (name.toLowerCase() === "etag") return `"${next.payload?.version || INITIAL_VERSION}"`;
                return null;
            } },
            async json() {
                jsonCalls += 1;
                if (next.jsonError) throw next.jsonError;
                return next.payload ?? payload();
            },
        };
    };
    class ClockDate extends Date {
        static now() { return Date.parse("2026-10-31T06:30:00+07:00") + now; }
    }
    vm.runInNewContext(fs.readFileSync(SOURCE, "utf8"), {
        document, window, navigator, fetch, URL, AbortController, Intl, Date: ClockDate,
        setTimeout: window.setTimeout, clearTimeout: window.clearTimeout,
        console: { warn(...values) { errors.push(values); }, error(...values) { errors.push(values); } },
    });
    await settle();
    async function advance(milliseconds) {
        const target = now + milliseconds;
        let executions = 0;
        while (timers.size) {
            const entry = [...timers.entries()].sort((a, b) => a[1].due - b[1].due)[0];
            if (entry[1].due > target) break;
            assert.ok(++executions < 100, "Polling scheduled an unbounded immediate loop");
            now = entry[1].due;
            timers.delete(entry[0]);
            entry[1].callback();
            await settle();
        }
        now = target;
        await settle();
    }
    return {
        root, nodes, details, document, window, navigator, requests, errors,
        get jsonCalls() { return jsonCalls; },
        get nextDelay() { return timers.size ? Math.min(...[...timers.values()].map((item) => item.due - now)) : null; },
        enqueue(...items) { responses.push(...items); },
        advance,
        async next() { assert.notEqual(this.nextDelay, null); await advance(this.nextDelay); },
        async refresh() { nodes.refresh.handlers.click?.({ preventDefault() {} }); await settle(); },
        async visibility(value) { document.hidden = value; document.handlers.visibilitychange?.(); await settle(); },
        async connectivity(value) { navigator.onLine = value; window.handlers[value ? "online" : "offline"]?.(); await settle(); },
    };
}

function assertOriginalData(ui) {
    assert.equal(ui.nodes.total.textContent, "10");
    assert.equal(ui.nodes.rescued.textContent, "3");
    assert.equal(ui.nodes.average.textContent, "0,50");
    assert.equal(ui.nodes["status-chart"].src, "/initial-status.png");
    assert.equal(ui.nodes["daily-chart"].src, "/initial-daily.png");
    assert.equal(ui.nodes["status-rows"].replaceCount, 0);
    assert.equal(ui.nodes["daily-rows"].replaceCount, 0);
}

test("public statistics waits five seconds and sends conditional same-origin requests", async () => {
    const ui = await statisticsUI();
    assert.equal(ui.requests.length, 0);
    await ui.advance(4999);
    assert.equal(ui.requests.length, 0);
    await ui.advance(1);
    assert.equal(ui.requests.length, 1);
    const request = ui.requests[0];
    assert.ok(request.url.endsWith("/statistics/live/"));
    assert.equal(request.options.credentials, "same-origin");
    assert.equal(request.options.cache, "no-store");
    assert.equal(request.options.headers["If-None-Match"], `"${INITIAL_VERSION}"`);
    assert.ok(request.options.signal instanceof AbortSignal);
    assert.equal(ui.nextDelay, 5000);
});

test("changed statistics update charts, metrics and seven safe table rows while preserving details", async () => {
    const ui = await statisticsUI();
    const next = payload();
    next.status_rows[0].label = '<script>alert("label")</script>';
    ui.enqueue({ payload: next });
    const metric = ui.nodes.total;
    const originalDetails = [...ui.details];
    await ui.next();
    assert.equal(ui.nodes.total, metric);
    assert.equal(metric.textContent, "12");
    assert.equal(ui.nodes.rescued.textContent, "4");
    assert.match(ui.nodes.average.textContent, /^1(?:[,.]00)?$/);
    assert.equal(ui.nodes["status-chart"].src, PNG);
    assert.equal(ui.nodes["daily-chart"].src, PNG);
    assert.equal(ui.nodes.window.textContent, next.window_label);
    assert.equal(ui.nodes["status-rows"].children.length, 3);
    assert.equal(ui.nodes["daily-rows"].children.length, 7);
    assert.equal(ui.nodes["status-rows"].children[0].children[0].textContent, next.status_rows[0].label);
    assert.equal(ui.nodes["daily-rows"].children[0].children[1].textContent, "1");
    assert.equal(ui.nodes["checked-at"].dateTime, CHECKED_AT);
    assert.deepEqual(ui.root.children, originalDetails);
    assert.ok(ui.details.every((item) => item.open));
    assert.equal(ui.root.replaceCount, 0);
    await ui.next();
    assert.equal(ui.requests[1].options.headers["If-None-Match"], `"${NEW_VERSION}"`);
});

test("304 avoids JSON and DOM rebuilding and still records the server check time", async () => {
    const ui = await statisticsUI();
    const statusRow = ui.nodes["status-rows"].children[0];
    const dailyRow = ui.nodes["daily-rows"].children[0];
    await ui.next();
    assert.equal(ui.jsonCalls, 0);
    assertOriginalData(ui);
    assert.equal(ui.nodes["status-rows"].children[0], statusRow);
    assert.equal(ui.nodes["daily-rows"].children[0], dailyRow);
    assert.equal(ui.nodes["checked-at"].dateTime, CHECKED_AT);
    assert.ok(ui.details.every((item) => item.open));
});

test("an unchanged version preserves chart and table nodes on a 200 response", async () => {
    const ui = await statisticsUI();
    ui.enqueue({ payload: payload({ version: INITIAL_VERSION }) });
    await ui.next();
    assertOriginalData(ui);
    assert.equal(ui.nodes["status-chart"].sourceWrites, 1);
    assert.equal(ui.nodes["daily-chart"].sourceWrites, 1);
});

test("a new day shifts the seven-day window and adds its counts without replacing the open section", async () => {
    const ui = await statisticsUI();
    ui.enqueue({ payload: payload() });
    await ui.next();
    const originalNodes = { ...ui.nodes };
    const originalDetails = [...ui.details];
    const nextChart = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=";
    const checkedAt = "2026-11-01T00:00:05+07:00";
    const next = payload({
        version: "c".repeat(64), checked_at: checkedAt,
        total: 15, daily_average: 1.29,
        window_label: "26/10/2026 – 01/11/2026",
        status_chart: nextChart, daily_chart: nextChart,
        daily_rows: [26, 27, 28, 29, 30, 31].map((day) => ({ date: `2026-10-${day}`, count: 1 }))
            .concat({ date: "2026-11-01", count: 3 }),
    });
    next.status_rows[0].count = 6;
    ui.enqueue({ payload: next, checkedAt });
    await ui.next();

    for (const [name, node] of Object.entries(originalNodes)) assert.equal(ui.nodes[name], node);
    assert.deepEqual(ui.root.children, originalDetails);
    assert.ok(ui.details.every((item) => item.open));
    assert.equal(ui.root.replaceCount, 0);
    assert.equal(ui.nodes.total.textContent, "15");
    assert.equal(ui.nodes.average.textContent, "1,29");
    assert.equal(ui.nodes.window.textContent, next.window_label);
    assert.equal(ui.nodes["status-chart"].src, nextChart);
    assert.equal(ui.nodes["daily-chart"].src, nextChart);
    assert.equal(ui.nodes["checked-at"].dateTime, checkedAt);
    const rows = ui.nodes["daily-rows"].children;
    assert.equal(rows.length, 7);
    assert.equal(rows[0].children[0].textContent, "26/10/2026");
    assert.equal(rows[6].children[0].textContent, "01/11/2026");
    assert.equal(rows[6].children[1].textContent, "3");
    assert.ok(rows.every((row) => row.children[0].textContent !== "25/10/2026"));
});

test("hidden pages pause polling and refresh immediately when visible", async () => {
    const ui = await statisticsUI({ hidden: true });
    await ui.advance(30000);
    assert.equal(ui.requests.length, 0);
    await ui.visibility(false);
    assert.equal(ui.requests.length, 1);
    await ui.visibility(true);
    await ui.advance(30000);
    assert.equal(ui.requests.length, 1);
    await ui.visibility(false);
    assert.equal(ui.requests.length, 2);
});

test("offline pages keep existing data and resume when the connection returns", async () => {
    const ui = await statisticsUI({ online: false });
    await ui.advance(30000);
    assert.equal(ui.requests.length, 0);
    assertOriginalData(ui);
    ui.enqueue({ payload: payload() });
    await ui.connectivity(true);
    assert.equal(ui.requests.length, 1);
    assert.equal(ui.nodes.total.textContent, "12");
    await ui.connectivity(false);
    await ui.advance(30000);
    assert.equal(ui.requests.length, 1);
});

test("manual refresh runs immediately and replaces the scheduled poll", async () => {
    const ui = await statisticsUI();
    ui.enqueue({ payload: payload() });
    await ui.refresh();
    assert.equal(ui.requests.length, 1);
    assert.equal(ui.nodes.total.textContent, "12");
    await ui.advance(4999);
    assert.equal(ui.requests.length, 1);
    await ui.advance(1);
    assert.equal(ui.requests.length, 2);
});

test("a slow request never overlaps polling or manual refresh and is aborted after ten seconds", async () => {
    const ui = await statisticsUI();
    ui.enqueue({ pending: true });
    await ui.next();
    await ui.refresh();
    await ui.advance(5000);
    assert.equal(ui.requests.length, 1);
    assert.equal(ui.requests[0].options.signal.aborted, false);
    await ui.advance(5000);
    assert.equal(ui.requests.length, 1);
    assert.equal(ui.requests[0].options.signal.aborted, true);
    assertOriginalData(ui);
    assert.ok(ui.nextDelay > 0 && ui.nextDelay <= 30000);
    ui.enqueue({ payload: payload() });
    await ui.next();
    assert.equal(ui.nodes.total.textContent, "12");
});

test("network and HTTP failures preserve displayed data, back off at most thirty seconds and recover", async () => {
    const ui = await statisticsUI();
    ui.enqueue(new Error("Network disconnected"), { status: 503 }, { status: 500 }, { status: 502 }, { status: 502 });
    const delays = [];
    for (let index = 0; index < 5; index += 1) {
        await ui.next();
        assertOriginalData(ui);
        assert.ok(ui.nextDelay >= 5000 && ui.nextDelay <= 30000);
        delays.push(ui.nextDelay);
    }
    assert.ok(delays.every((delay, index) => index === 0 || delay >= delays[index - 1]));
    assert.equal(delays.at(-1), 30000);
    ui.enqueue({ payload: payload() });
    await ui.next();
    assert.equal(ui.nodes.total.textContent, "12");
    assert.equal(ui.nextDelay, 5000);
});

test("invalid JSON, incomplete dates and unsafe chart payloads never partially replace existing statistics", async () => {
    const repeatedDay = payload().daily_rows;
    repeatedDay[3].date = repeatedDay[2].date;
    const missingDay = payload().daily_rows;
    missingDay[6].date = "2026-11-01";
    const invalid = [
        { jsonError: new SyntaxError("Invalid JSON") },
        { payload: payload({ daily_rows: payload().daily_rows.slice(0, 6) }) },
        { payload: payload({ daily_rows: repeatedDay }) },
        { payload: payload({ daily_rows: missingDay }) },
        { payload: payload({ status_chart: 'data:text/html,<script>alert(1)</script>' }) },
        { payload: payload({ total: -1 }) },
        { payload: payload({ daily_chart: undefined }) },
    ];
    for (const response of invalid) {
        const ui = await statisticsUI();
        ui.enqueue(response);
        await ui.next();
        assertOriginalData(ui);
        assert.equal(ui.root.dataset.version, INITIAL_VERSION);
        assert.equal(ui.nodes.status.getAttribute("data-state"), "error");
        ui.enqueue({ payload: payload() });
        await ui.next();
        assert.equal(ui.nodes.total.textContent, "12");
    }
});

test("pages without the statistics section install no polling", async () => {
    const ui = await statisticsUI({ present: false });
    assert.equal(ui.nextDelay, null);
    await ui.advance(30000);
    assert.equal(ui.requests.length, 0);
});
