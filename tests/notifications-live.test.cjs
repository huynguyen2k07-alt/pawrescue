const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "../static/js/notifications-live.js"), "utf8");
const createdAt = "2026-11-01T10:00:00+07:00";
const settle = async () => { for (let i = 0; i < 20; i += 1) await Promise.resolve(); };

function notification(id, extra = {}) {
    return { id, kind: "case_assigned", title: `Ca cứu hộ #${id}`, is_read: false, created_at: createdAt, url: `/cases/${id}/`, open_url: `/notifications/${id}/open/`, ...extra };
}

function snapshot(items = [notification(10)], extra = {}) {
    return {
        user_id: 7, version: "v1", unread_count: items.filter((item) => !item.is_read).length,
        total_count: items.length, latest_id: items.length ? Math.max(...items.map((item) => item.id)) : 0,
        support_unread_count: 2, items, unread_items: items.filter((item) => !item.is_read), ...extra,
    };
}

function fixture({ enabled = true, baseline = 10, hidden = false, online = true, listPage = null, filter = "all", rows = [] } = {}) {
    let mutations = 0;
    class Element {
        constructor(tag = "div") {
            this.tagName = tag.toUpperCase();
            this.attributes = {};
            this.dataset = {};
            this.children = [];
            this.parentElement = null;
            this.handlers = {};
            this.hidden = false;
            this._text = "";
            this.classList = {
                contains: (name) => this.className.split(/\s+/).includes(name),
                toggle: (name, force) => {
                    const names = new Set(this.className.split(/\s+/).filter(Boolean));
                    const next = force === undefined ? !names.has(name) : force;
                    if (next) names.add(name); else names.delete(name);
                    const value = [...names].join(" ");
                    if (this.className !== value) this.className = value;
                    return next;
                },
            };
        }
        set textContent(value) {
            mutations += 1;
            this._text = String(value);
            for (const child of this.children) child.parentElement = null;
            this.children = [];
        }
        get textContent() { return this._text + this.children.map((child) => child.textContent).join(""); }
        set innerHTML(_) { throw new Error("Notification text must never be inserted as HTML"); }
        get className() { return this.attributes.class || ""; }
        set className(value) { this.setAttribute("class", value); }
        get href() { return this.getAttribute("href") || ""; }
        set href(value) { this.setAttribute("href", value); }
        get action() { return this.getAttribute("action") || ""; }
        set action(value) { this.setAttribute("action", value); }
        get firstElementChild() { return this.children[0] || null; }
        get nextElementSibling() {
            if (!this.parentElement) return null;
            return this.parentElement.children[this.parentElement.children.indexOf(this) + 1] || null;
        }
        setAttribute(name, value) {
            mutations += 1;
            this.attributes[name] = String(value);
            if (name.startsWith("data-")) this.dataset[name.slice(5).replace(/-([a-z])/g, (_, char) => char.toUpperCase())] = String(value);
        }
        getAttribute(name) { return this.attributes[name] ?? null; }
        hasAttribute(name) { return name in this.attributes; }
        matches(selector) {
            if (selector.startsWith("[")) return this.hasAttribute(selector.slice(1, -1));
            if (selector.startsWith(".")) return this.classList.contains(selector.slice(1));
            return this.tagName === selector.toUpperCase();
        }
        querySelectorAll(selector) {
            const found = [];
            for (const child of this.children) {
                if (child.matches(selector)) found.push(child);
                found.push(...child.querySelectorAll(selector));
            }
            return found;
        }
        querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
        appendChild(child) { return this.insertBefore(child, null); }
        append(...children) { for (const child of children) this.appendChild(child); }
        insertBefore(child, reference) {
            mutations += 1;
            child.remove();
            const index = reference ? this.children.indexOf(reference) : this.children.length;
            assert.ok(index >= 0, "insertBefore reference must belong to this parent");
            this.children.splice(index, 0, child);
            child.parentElement = this;
            return child;
        }
        remove() {
            if (!this.parentElement) return;
            mutations += 1;
            this.parentElement.children.splice(this.parentElement.children.indexOf(this), 1);
            this.parentElement = null;
        }
        replaceChildren(...children) {
            mutations += 1;
            for (const child of this.children) child.parentElement = null;
            this.children = [];
            this._text = "";
            this.append(...children);
        }
        addEventListener(type, callback) { (this.handlers[type] ||= []).push(callback); }
        closest(selector) {
            for (let node = this; node; node = node.parentElement) if (node.matches(selector)) return node;
            return null;
        }
        fire(type, extra = {}) {
            const event = { type, target: this, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; }, ...extra };
            for (const callback of this.handlers[type] || []) callback(event);
            return event;
        }
    }

    const document = new Element("document");
    document.hidden = hidden;
    document.visibilityState = hidden ? "hidden" : "visible";
    document.createElement = (tag) => new Element(tag);
    const navigator = { onLine: online };
    const window = new Element("window");
    window.location = { origin: "http://127.0.0.1:8000" };
    let now = 0;
    let timerId = 0;
    const timers = new Map();
    window.setTimeout = (callback, delay = 0) => { const id = ++timerId; timers.set(id, { callback, due: now + delay }); return id; };
    window.clearTimeout = (id) => timers.delete(id);
    const clock = {
        async tick(milliseconds) {
            const end = now + milliseconds;
            while (true) {
                const next = [...timers].filter(([, timer]) => timer.due <= end).sort((a, b) => a[1].due - b[1].due)[0];
                if (!next) break;
                const [id, timer] = next;
                timers.delete(id);
                now = timer.due;
                timer.callback();
                await settle();
            }
            now = end;
            await settle();
        },
        pending() { return timers.size; },
    };
    function node(tag, attributes = {}, text = "") {
        const element = new Element(tag);
        for (const [name, value] of Object.entries(attributes)) element.setAttribute(name, value);
        if (text) element.textContent = text;
        return element;
    }
    const root = node("div", { "data-live-notifications": "", "data-state-url": "/notifications/live/", "data-user-id": "7", "data-latest-id": String(baseline), "data-list-url": "/notifications/" });
    const toasts = node("div", { "data-notification-toasts": "" });
    root.appendChild(toasts);
    if (enabled) document.appendChild(root);
    const badges = [];
    const links = [];
    const supportBadges = [];
    for (let i = 0; i < 2; i += 1) {
        const link = node("a", { "data-notification-link": "", href: "/notifications/" });
        const badge = node("span", { "data-notification-count": "" }, "9");
        const support = node("span", { "data-support-unread-count": "" }, "4");
        link.appendChild(badge);
        document.append(link, support);
        badges.push(badge); links.push(link); supportBadges.push(support);
    }
    const total = node("span", { "data-notification-total-count": "" }, "9");
    const unread = node("span", { "data-notification-unread-count": "" }, "9");
    const readAll = node("form", { "data-notification-read-all": "", action: "/notifications/read-all/" });
    readAll.appendChild(node("button"));
    const readStatus = node("p", { "data-notification-read-status": "" });
    const cue = node("p", { "data-notification-new-items": "" });
    cue.hidden = true;
    const older = node("a", { "data-notification-older": "", href: "?page=2" });
    const list = listPage === null ? null : node("div", { "data-live-notification-list": "", "data-filter": filter, "data-page": String(listPage), "data-csrf-token": "csrf-token-7" });
    if (list) {
        for (const item of rows) {
            const row = node("article", { "data-notification-id": String(item.id), "data-notification-read": String(item.is_read), class: `notification-item${item.is_read ? "" : " unread"}` });
            const link = node("a", { "data-notification-title": "", href: item.url }, item.title);
            const time = node("time", { datetime: item.created_at }, "vừa xong");
            const readForm = node("form", { "data-notification-read-form": "", action: item.open_url });
            readForm.appendChild(node("button"));
            const details = node("span", { "data-server-detail": "" }, "Nội dung đang đọc phải được giữ nguyên");
            row.append(link, time, readForm, details);
            list.appendChild(row);
        }
        document.append(total, unread, readAll, readStatus, cue, list, older);
    }
    const unrelatedForm = node("form");
    const draft = node("textarea");
    draft.value = "Bản nháp đang nhập";
    unrelatedForm.appendChild(draft);
    document.appendChild(unrelatedForm);
    const requests = [];
    const context = {
        document, navigator, window, URL, AbortController,
        fetch(url, options) {
            let resolve;
            let reject;
            const promise = new Promise((done, fail) => { resolve = done; reject = fail; });
            requests.push({ url, options, resolve, reject });
            return promise;
        },
        EventSource() { throw new Error("Live notifications must not open a second streaming channel"); },
    };
    vm.runInNewContext(source, context);
    return {
        document, navigator, window, root, toasts, badges, links, supportBadges, list, total, unread, readAll, readStatus, cue, older, draft, requests, clock,
        mutations: () => mutations,
        async respond(index, data, status = 200, extra = {}) {
            requests[index].resolve({ status, ok: status >= 200 && status < 300, redirected: false, headers: { get(name) { return name.toLowerCase() === "etag" && data?.version ? `"${data.version}"` : null; } }, json: async () => data, ...extra });
            await settle();
        },
        async fail(index) { requests[index].reject(new Error("Offline")); await settle(); },
        async visibility(isHidden) {
            document.hidden = isHidden;
            document.visibilityState = isHidden ? "hidden" : "visible";
            document.fire("visibilitychange");
            await settle();
        },
        async connectivity(isOnline) {
            navigator.onLine = isOnline;
            window.fire(isOnline ? "online" : "offline");
            await settle();
        },
    };
}

test("the global notifier starts immediately, scopes cookies and polls two seconds after completion", async () => {
    const ui = fixture();
    assert.equal(ui.requests.length, 1);
    assert.equal(ui.requests[0].url, "/notifications/live/");
    assert.equal(ui.requests[0].options.credentials, "same-origin");
    assert.equal(ui.requests[0].options.cache, "no-store");
    await ui.clock.tick(3000);
    assert.equal(ui.requests.length, 1, "an unfinished request must not overlap another poll");
    await ui.respond(0, snapshot());
    for (const badge of ui.badges) { assert.equal(badge.textContent, "1"); assert.equal(badge.hidden, false); }
    for (const badge of ui.supportBadges) assert.equal(badge.textContent, "2");
    for (const link of ui.links) { assert.equal(link.classList.contains("has-unread"), true); assert.equal(link.getAttribute("href"), "/notifications/"); }
    assert.equal(ui.toasts.children.length, 0, "SSR notifications must not toast again");
    await ui.clock.tick(1999);
    assert.equal(ui.requests.length, 1);
    await ui.clock.tick(1);
    assert.equal(ui.requests.length, 2);
    assert.equal(ui.requests[1].options.headers["If-None-Match"], '"v1"');
    assert.equal(ui.draft.value, "Bản nháp đang nhập");
});

test("an arrival after the SSR baseline appears on the first response as a safe native link", async () => {
    const ui = fixture();
    await ui.respond(0, snapshot([notification(11, { title: "<img src=x onerror=alert(1)>" }), notification(10)]));
    assert.equal(ui.toasts.children.length, 1);
    const toast = ui.toasts.firstElementChild;
    assert.equal(toast.className, "live-notification-toast");
    assert.equal(toast.querySelector("p").textContent, "<img src=x onerror=alert(1)>");
    assert.equal(toast.querySelectorAll("img").length, 0);
    const link = toast.querySelector("a");
    assert.equal(link.href, "/cases/11/");
    assert.equal(link.handlers.click, undefined, "native middle-click and modified clicks must remain untouched");
    assert.equal(ui.links[0].handlers.click, undefined);
    toast.querySelector("button").fire("click");
    assert.equal(ui.toasts.children.length, 0);
});

test("bursts display at most three toasts and repeated snapshots do not notify twice", async () => {
    const ui = fixture();
    const items = [15, 14, 13, 12, 11, 10].map((id) => notification(id));
    await ui.respond(0, snapshot(items));
    assert.equal(ui.toasts.children.length, 3);
    assert.match(ui.toasts.textContent, /Có 5 thông báo mới/);
    assert.equal(ui.toasts.querySelector("[data-notification-toast-summary]").querySelector("a").href, "/notifications/");
    await ui.clock.tick(2000);
    await ui.respond(1, snapshot(items, { version: "v2" }));
    assert.equal(ui.toasts.children.length, 2, "the previous generic burst summary expires on the next changed state");
    assert.equal(ui.toasts.querySelectorAll("[data-notification-toast-id]").length, 2);
    assert.equal(ui.toasts.querySelector("[data-notification-toast-summary]"), null);
});

test("read, deleted or inaccessible notifications disappear from active toasts", async () => {
    for (const reason of ["read", "deleted", "permission revoked"]) {
        const ui = fixture();
        await ui.respond(0, snapshot([notification(11)]));
        assert.equal(ui.toasts.children.length, 1, reason);
        await ui.clock.tick(2000);
        await ui.respond(1, reason === "read" ? snapshot([notification(11, { is_read: true })], { version: "v2" }) : snapshot([], { version: "v2" }));
        assert.equal(ui.toasts.children.length, 0, reason);
        assert.equal(ui.badges[0].hidden, true, reason);
    }
});

test("a 304 preserves DOM identity and does not rebuild any badge, toast or row", async () => {
    const item = notification(10);
    const ui = fixture({ listPage: 1, rows: [item] });
    const originalRow = ui.list.firstElementChild;
    await ui.respond(0, snapshot([item]));
    const mutations = ui.mutations();
    await ui.clock.tick(2000);
    await ui.respond(1, null, 304);
    assert.equal(ui.mutations(), mutations);
    assert.equal(ui.list.firstElementChild, originalRow);
    assert.equal(ui.requests.length, 2);
});

test("zero unread counts hide both public/admin badges and support badges independently", async () => {
    const ui = fixture({ listPage: 1 });
    await ui.respond(0, snapshot([notification(10, { is_read: true })], { support_unread_count: 0 }));
    for (const badge of ui.badges.concat(ui.supportBadges)) { assert.equal(badge.textContent, "0"); assert.equal(badge.hidden, true); }
    for (const link of ui.links) { assert.equal(link.classList.contains("has-unread"), false); assert.equal(link.getAttribute("aria-label"), "Thông báo"); }
    assert.equal(ui.readAll.hidden, true);
    assert.equal(ui.total.textContent, "1");
    assert.equal(ui.unread.textContent, "0");
});

test("malformed snapshots and unsafe links never partially update existing private UI", async () => {
    const badStates = [
        snapshot([notification(11, { url: "javascript:alert(1)" })]),
        snapshot([notification(11, { url: "https://evil.example/private" })]),
        snapshot([notification(11, { open_url: "//evil.example/read" })]),
        snapshot([notification(11, { created_at: "not a date" })]),
        snapshot([notification(11)], { unread_count: -1 }),
        snapshot([notification(11)], { total_count: 0 }),
        snapshot([notification(11)], { support_unread_count: "2" }),
        snapshot([notification(11)], { version: "bad\r\nheader" }),
        snapshot([notification(11), notification(11)]),
        snapshot([notification(11)], { unread_items: [notification(11, { is_read: true })] }),
    ];
    for (const data of badStates) {
        const ui = fixture({ listPage: 1, rows: [notification(10)] });
        const originalRow = ui.list.firstElementChild;
        const mutations = ui.mutations();
        await ui.respond(0, data);
        assert.equal(ui.badges[0].textContent, "9");
        assert.equal(ui.supportBadges[0].textContent, "4");
        assert.equal(ui.toasts.children.length, 0);
        assert.equal(ui.list.firstElementChild, originalRow);
        assert.equal(ui.mutations(), mutations);
    }
});

test("unauthorized responses and cross-account state clear private content and stop polling", async () => {
    for (const problem of ["401", "403", "different user", "login redirect"]) {
        const ui = fixture({ listPage: 1, rows: [notification(10)] });
        await ui.respond(0, snapshot([notification(11)], { total_count: 21 }));
        assert.equal(ui.toasts.children.length, 1);
        assert.equal(ui.older.hidden, false);
        await ui.clock.tick(2000);
        if (problem === "different user") await ui.respond(1, snapshot([notification(12)], { user_id: 8, version: "v2" }));
        else if (problem === "login redirect") await ui.respond(1, null, 200, { redirected: true });
        else await ui.respond(1, null, Number(problem));
        assert.equal(ui.toasts.children.length, 0, problem);
        assert.equal(ui.list.children.length, 0, problem);
        assert.equal(ui.badges[0].hidden, true, problem);
        assert.equal(ui.supportBadges[0].hidden, true, problem);
        assert.equal(ui.older.hidden, true, problem);
        await ui.clock.tick(60000);
        ui.window.fire("focus");
        assert.equal(ui.requests.length, 2, problem);
        assert.equal(ui.clock.pending(), 0, problem);
    }
});

test("hidden tabs abort requests, ignore late private responses and refresh once on return", async () => {
    const ui = fixture();
    await ui.visibility(true);
    assert.equal(ui.requests[0].options.signal.aborted, true);
    await ui.respond(0, snapshot([notification(99)]));
    assert.equal(ui.badges[0].textContent, "9");
    assert.equal(ui.toasts.children.length, 0);
    await ui.clock.tick(20000);
    assert.equal(ui.requests.length, 1);
    await ui.visibility(false);
    ui.window.fire("focus");
    assert.equal(ui.requests.length, 2);
    await ui.respond(1, snapshot([notification(11)]));
    assert.equal(ui.badges[0].textContent, "1");
    assert.equal(ui.toasts.children.length, 1);
});

test("offline pauses requests and repeated online/focus events do not overlap recovery", async () => {
    const ui = fixture();
    await ui.respond(0, snapshot());
    await ui.connectivity(false);
    await ui.clock.tick(30000);
    assert.equal(ui.requests.length, 1);
    await ui.connectivity(true);
    ui.window.fire("online");
    ui.window.fire("focus");
    assert.equal(ui.requests.length, 2);
    await ui.respond(1, snapshot([notification(11)], { version: "v2" }));
    await ui.clock.tick(2000);
    assert.equal(ui.requests.length, 3);
});

test("the eight-second deadline bounds stalled response bodies and permits a clean retry", async () => {
    const ui = fixture();
    let releaseBody;
    const body = new Promise((resolve) => { releaseBody = resolve; });
    await ui.respond(0, null, 200, { json: () => body });
    await ui.clock.tick(7999);
    assert.equal(ui.requests.length, 1);
    assert.equal(ui.requests[0].options.signal.aborted, false);
    await ui.clock.tick(1);
    assert.equal(ui.requests[0].options.signal.aborted, true);
    await ui.clock.tick(3999);
    assert.equal(ui.requests.length, 1);
    await ui.clock.tick(1);
    assert.equal(ui.requests.length, 2);
    releaseBody(snapshot([notification(99)]));
    await settle();
    assert.equal(ui.badges[0].textContent, "9");
    await ui.respond(1, snapshot([notification(11)]));
    assert.equal(ui.toasts.firstElementChild.querySelector("a").href, "/cases/11/");
});

test("errors back off to thirty seconds and success restores the two-second cadence", async () => {
    const ui = fixture();
    const delays = [4000, 8000, 16000, 30000, 30000];
    for (let i = 0; i < delays.length; i += 1) {
        await ui.fail(i);
        await ui.clock.tick(delays[i] - 1);
        assert.equal(ui.requests.length, i + 1);
        await ui.clock.tick(1);
        assert.equal(ui.requests.length, i + 2);
    }
    await ui.respond(delays.length, snapshot());
    await ui.clock.tick(2000);
    assert.equal(ui.requests.length, delays.length + 2);
});

test("first-page keyed updates preserve existing cards and create complete native-link/POST rows", async () => {
    const oldItem = notification(10);
    const ui = fixture({ listPage: 1, rows: [oldItem] });
    const originalRow = ui.list.firstElementChild;
    const originalTitle = originalRow.querySelector("[data-notification-title]");
    const originalDetails = originalRow.querySelector("[data-server-detail]");
    ui.document.activeElement = originalTitle;
    await ui.respond(0, snapshot([notification(11), oldItem]));
    assert.equal(ui.list.children[1], originalRow);
    assert.equal(originalRow.querySelector("[data-server-detail]"), originalDetails);
    assert.equal(ui.document.activeElement, originalTitle);
    const newRow = ui.list.firstElementChild;
    assert.ok(newRow.querySelector(".notification-open"));
    assert.ok(newRow.querySelector(".notification-kind"));
    assert.ok(newRow.querySelector(".notification-content"));
    assert.ok(newRow.querySelector(".notification-live-actions"));
    assert.equal(newRow.querySelector("[data-notification-title]").href, "/cases/11/");
    assert.equal(newRow.querySelector("[data-notification-title]").handlers.click, undefined);
    const form = newRow.querySelector("[data-notification-read-form]");
    assert.equal(form.method, "post");
    assert.equal(form.action, "/notifications/11/open/");
    assert.equal(form.querySelector("input").name, "csrfmiddlewaretoken");
    assert.equal(form.querySelector("input").value, "csrf-token-7");
    assert.equal(ui.draft.value, "Bản nháp đang nhập");
    await ui.clock.tick(2000);
    await ui.respond(1, snapshot([notification(10, { is_read: true })], { version: "v2" }));
    assert.equal(ui.list.firstElementChild, originalRow);
    assert.equal(ui.list.children.length, 1);
    assert.equal(originalRow.classList.contains("unread"), false);
    assert.equal(originalRow.querySelector("[data-notification-read-form]").hidden, true);
});

test("the unread filter uses the unread snapshot and becomes empty when those items are read", async () => {
    const ui = fixture({ listPage: 1, filter: "unread", rows: [notification(10)] });
    await ui.respond(0, snapshot([notification(12, { is_read: true }), notification(11)]));
    assert.equal(ui.list.querySelectorAll("[data-notification-id]").length, 1);
    assert.equal(ui.list.firstElementChild.dataset.notificationId, "11");
    await ui.clock.tick(2000);
    await ui.respond(1, snapshot([notification(12, { is_read: true }), notification(11, { is_read: true })], { version: "v2" }));
    assert.equal(ui.list.querySelectorAll("[data-notification-id]").length, 0);
    assert.match(ui.list.querySelector("[data-notification-empty]").textContent, /đọc hết/);
    assert.equal(ui.readAll.hidden, true);
});

test("older pages preserve their rows and reading position while updating counts and a new-items cue", async () => {
    const ui = fixture({ listPage: 2, rows: [notification(3)] });
    const originalRow = ui.list.firstElementChild;
    const originalTitle = originalRow.querySelector("[data-notification-title]");
    ui.document.activeElement = originalTitle;
    await ui.respond(0, snapshot([notification(11)], { total_count: 30 }));
    assert.equal(ui.list.children.length, 1);
    assert.equal(ui.list.firstElementChild, originalRow);
    assert.equal(ui.document.activeElement, originalTitle);
    assert.equal(ui.cue.hidden, false);
    assert.equal(ui.total.textContent, "30");
    assert.equal(ui.badges[0].textContent, "1");
});

test("the older-items link follows the selected filtered count", async () => {
    for (const filter of ["all", "unread"]) {
        const ui = fixture({ listPage: 1, filter });
        await ui.respond(0, snapshot([notification(10)], { total_count: 30, unread_count: 1 }));
        assert.equal(ui.older.hidden, filter === "unread", filter);
        await ui.clock.tick(2000);
        await ui.respond(1, snapshot([notification(10)], { version: "v2", total_count: 30, unread_count: 25 }));
        assert.equal(ui.older.hidden, false, filter);
    }
});

test("pagehide pauses a page restored from the back-forward cache and pageshow refreshes it once", async () => {
    const ui = fixture();
    ui.window.fire("pagehide");
    await settle();
    assert.equal(ui.requests[0].options.signal.aborted, true);
    await ui.clock.tick(30000);
    assert.equal(ui.requests.length, 1);
    ui.window.fire("pageshow");
    ui.window.fire("focus");
    assert.equal(ui.requests.length, 2);
    await ui.respond(1, snapshot([notification(11)]));
    assert.equal(ui.toasts.children.length, 1);
});

test("anonymous, hidden and offline pages do not start a background request", async () => {
    for (const options of [{ enabled: false }, { hidden: true }, { online: false }]) {
        const ui = fixture(options);
        assert.equal(ui.requests.length, 0);
        await ui.clock.tick(30000);
        assert.equal(ui.requests.length, 0);
    }
});

test("mark-read posts with CSRF and updates the row and counters without navigating or scrolling", async () => {
    const ui = fixture({ listPage: 1, rows: [notification(10), notification(9)] });
    await ui.respond(0, snapshot([notification(10), notification(9)]));
    const row = ui.list.firstElementChild;
    const form = row.querySelector("[data-notification-read-form]");
    const location = ui.window.location;
    ui.window.scrollY = 480;
    const event = ui.document.fire("submit", { target: form });
    assert.equal(event.defaultPrevented, true);
    assert.equal(ui.requests[1].options.method, "POST");
    assert.equal(ui.requests[1].options.headers["X-CSRFToken"], "csrf-token-7");
    assert.equal(ui.requests[1].options.redirect, "error");
    assert.equal(form.querySelector("button").disabled, true);
    ui.document.fire("submit", { target: form });
    ui.window.fire("focus");
    assert.equal(ui.requests.length, 2, "repeated clicks and polling must not race the write");
    await ui.respond(1, snapshot([notification(10, { is_read: true }), notification(9)], { version: "read-v2" }));
    assert.equal(ui.list.firstElementChild, row);
    assert.equal(row.dataset.notificationRead, "true");
    assert.equal(form.hidden, true);
    assert.equal(ui.badges[0].textContent, "1");
    assert.equal(ui.unread.textContent, "1");
    assert.equal(ui.window.location, location);
    assert.equal(ui.window.scrollY, 480);
    assert.match(ui.readStatus.textContent, /Đã đánh dấu/);
    assert.equal(ui.draft.value, "Bản nháp đang nhập");
});

test("mark-all stays in the list and updates the unread filter immediately", async () => {
    const ui = fixture({ listPage: 1, filter: "unread", rows: [notification(10)] });
    await ui.respond(0, snapshot([notification(10)]));
    const event = ui.document.fire("submit", { target: ui.readAll });
    assert.equal(event.defaultPrevented, true);
    assert.equal(ui.requests[1].url, "/notifications/read-all/");
    await ui.respond(1, snapshot([notification(10, { is_read: true })], { version: "all-read" }));
    assert.equal(ui.readAll.hidden, true);
    assert.equal(ui.badges[0].hidden, true);
    assert.equal(ui.list.querySelectorAll("[data-notification-id]").length, 0);
    assert.match(ui.list.textContent, /đọc hết/);
});

test("marking an older row read preserves page two and updates that row outside the latest snapshot", async () => {
    const ui = fixture({ listPage: 2, rows: [notification(3)] });
    await ui.respond(0, snapshot([notification(30)], { total_count: 30, unread_count: 2 }));
    const row = ui.list.firstElementChild;
    ui.document.fire("submit", { target: row.querySelector("[data-notification-read-form]") });
    await ui.respond(1, snapshot([notification(30)], { version: "older-read", total_count: 30 }));
    assert.equal(ui.list.firstElementChild, row);
    assert.equal(ui.list.dataset.page, "2");
    assert.equal(row.dataset.notificationRead, "true");
    assert.equal(ui.badges[0].textContent, "1");
});

test("reading cancels an older poll so its late response cannot undo the read state", async () => {
    const ui = fixture({ listPage: 1, rows: [notification(10)] });
    const row = ui.list.firstElementChild;
    ui.document.fire("submit", { target: row.querySelector("[data-notification-read-form]") });
    assert.equal(ui.requests[0].options.signal.aborted, true);
    await ui.respond(1, snapshot([notification(10, { is_read: true })], { version: "read-now" }));
    await ui.respond(0, snapshot([notification(10)]));
    assert.equal(row.dataset.notificationRead, "true");
    assert.equal(ui.badges[0].hidden, true);
});

test("failed or stalled read actions retain the unread row and allow retry without navigation", async () => {
    for (const failure of ["network", "csrf", "login", "timeout"]) {
        const ui = fixture({ listPage: 1, rows: [notification(10)] });
        await ui.respond(0, snapshot([notification(10)]));
        const row = ui.list.firstElementChild;
        const form = row.querySelector("[data-notification-read-form]");
        ui.document.fire("submit", { target: form });
        if (failure === "timeout") await ui.clock.tick(8000);
        else if (failure === "network") await ui.fail(1);
        else await ui.respond(1, null, failure === "csrf" ? 403 : 200, { redirected: failure === "login" });
        assert.equal(row.dataset.notificationRead, "false", failure);
        assert.equal(form.hidden, false, failure);
        assert.equal(form.querySelector("button").disabled, false, failure);
        assert.match(ui.readStatus.textContent, /Chưa đánh dấu được/, failure);
        assert.equal(ui.list.firstElementChild, row, failure);
        if (failure === "timeout") {
            await ui.respond(1, snapshot([notification(10, { is_read: true })], { version: "too-late" }));
            assert.equal(row.dataset.notificationRead, "false");
        }
    }
});
