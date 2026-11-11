const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

function element(tagName = "div") {
    const classes = new Set();
    return {
        tagName, dataset: {}, children: [], value: "", files: [], hidden: false, disabled: false,
        textContent: "", handlers: {}, scrollTop: 0, scrollHeight: 100,
        classList: { add(value) { classes.add(value); }, remove(value) { classes.delete(value); }, toggle(value, enabled) { if (enabled) classes.add(value); else classes.delete(value); } },
        append(...items) { for (const item of items) this.children.push(...(item.isFragment ? item.children : [item])); },
        appendChild(item) { this.append(item); return item; },
        replaceChildren(...items) { this.children = []; this.append(...items); },
        addEventListener(name, handler) { this.handlers[name] = handler; },
        setAttribute(name, value) { this[name] = value; },
        focus() {},
    };
}

function descendants(item) { return [item, ...item.children.flatMap(descendants)]; }
function content(item) { return descendants(item).map((node) => node.textContent).join(" "); }
function settle() { return new Promise(setImmediate); }
function deferred() { let resolve; const promise = new Promise((done) => { resolve = done; }); return { promise, resolve }; }

function caseState(id = 7, overrides = {}) {
    return {
        case_id: id, title: `Ca cứu hộ ${id}`, unread_count: 0,
        recipients: [{ id: 2, name: "Cộng tác viên cứu hộ" }],
        messages: [{ id: id * 10, body: `Chỉ dẫn riêng ca ${id}`, sender_name: "Admin chính", recipient_name: "Cộng tác viên cứu hộ", is_own: false, created_at: "2026-11-10T08:00:00+07:00", read_at: null }],
        ...overrides,
    };
}

async function widget({ operator = false } = {}) {
    const nodes = new Map();
    function node(key) { if (!nodes.has(key)) nodes.set(key, element()); return nodes.get(key); }
    const root = node("root");
    const names = ["close", "messages", "form", "file-input", "attachment-preview", "feedback", "status", "badge", "toggle-title", "toggle-copy", "mode-tools", "default", "full-page", "case-title", "privacy", "attach-button"];
    const selectors = Object.fromEntries(names.map((name) => [`[data-support-${name}]`, node(name)]));
    selectors["[data-case-chat-recipient]"] = node("recipient-control");
    selectors["[data-case-chat-recipient-select]"] = node("recipient");
    root.querySelector = (selector) => selectors[selector] || null;
    root.dataset = { stateUrl: "/support/state/", sendUrl: "/support/send/", supportOperator: String(operator), supportInboxUrl: "/support/inbox/" };
    node("panel").hidden = true;
    node("form").querySelector = (selector) => ({ textarea: node("textarea"), "[data-support-file-input]": node("file-input"), "[data-support-attachment-preview]": node("attachment-preview"), "button[type='submit']": node("submit") })[selector] || null;
    const document = {
        hidden: false, handlers: {},
        getElementById(id) { return { "support-chat": root, "support-chat-toggle": node("toggle"), "support-chat-panel": node("panel"), "support-chat-title": node("title") }[id] || null; },
        createElement: element,
        createDocumentFragment() { return { ...element(), isFragment: true }; },
        addEventListener(name, handler) { this.handlers[name] = handler; },
    };
    const requests = [];
    const states = new Map();
    const supportState = { status_label: "Sẵn sàng", unread_count: 0, messages: [{ id: 1, body: "Hỗ trợ riêng người dùng", sender_name: "Admin chính", is_admin: true, created_at: "08:00", attachments: [] }] };
    let poll;
    let intercept;
    class FormData {
        constructor() { this.values = new Map([["csrfmiddlewaretoken", "csrf-token"], ["attachments", "fake-file"]]); }
        set(key, value) { this.values.set(key, value); }
        get(key) { return this.values.get(key); }
        delete(key) { this.values.delete(key); }
    }
    const context = {
        URL, FormData, document,
        window: { location: { origin: "http://localhost:8000" }, setInterval(callback) { poll = callback; } },
        fetch: async (url, options) => {
            const request = { url: String(url), options };
            requests.push(request);
            if (intercept) {
                const response = intercept(request);
                if (response) return response;
            }
            const match = request.url.match(/\/cases\/(\d+)\/messages\//);
            const data = match ? states.get(Number(match[1])) || caseState(Number(match[1])) : supportState;
            return { ok: true, status: options.method === "POST" ? 201 : 200, json: async () => data };
        },
    };
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../static/js/support-chat.js"), "utf8"), context);
    await settle();
    function clickCase(id, options = {}) {
        const link = element("a");
        link.dataset = { caseChatUrl: `/cases/${id}/messages/`, caseChatTitle: `Ca #${id}` };
        link.closest = () => link;
        let prevented = false;
        const event = { target: link, button: 0, ...options, preventDefault() { prevented = true; } };
        document.handlers.click(event);
        return prevented;
    }
    return {
        node, requests, states, document, clickCase,
        set intercept(value) { intercept = value; },
        async openCase(id) { assert.equal(clickCase(id), true); await settle(); },
        async tick() { await poll(); await settle(); },
        async submit() { await node("form").handlers.submit({ preventDefault() {} }); await settle(); },
        async close() { node("close").handlers.click(); await settle(); },
    };
}

test("admin opens assigned case chat in the shared widget without fetching a personal support conversation", async () => {
    const ui = await widget({ operator: true });
    assert.equal(ui.requests.length, 0);
    await ui.openCase(7);
    assert.match(content(ui.node("messages")), /Chỉ dẫn riêng ca 7/);
    assert.equal(ui.node("recipient").value, "2");
    assert.equal(ui.node("submit").disabled, false);
    assert.equal(ui.node("file-input").disabled, true);
    assert.equal(ui.node("full-page").href, "http://localhost:8000/cases/7/messages/");
    assert.ok(ui.requests.every((request) => request.url.includes("/cases/7/messages/")));
});

test("helper switches between personal support and case chat without retaining the other conversation or draft", async () => {
    const ui = await widget();
    ui.node("toggle").handlers.click();
    await settle();
    assert.match(content(ui.node("messages")), /Hỗ trợ riêng người dùng/);
    ui.node("textarea").value = "Bản nháp của người dùng";
    await ui.openCase(7);
    assert.equal(ui.node("textarea").value, "");
    assert.doesNotMatch(content(ui.node("messages")), /Hỗ trợ riêng người dùng/);
    ui.node("default").handlers.click();
    await settle();
    assert.match(content(ui.node("messages")), /Hỗ trợ riêng người dùng/);
    assert.doesNotMatch(content(ui.node("messages")), /Chỉ dẫn riêng ca 7/);
    assert.equal(ui.node("recipient").disabled, true);
});

test("case send carries the permitted recipient and CSRF token with no support attachments", async () => {
    const ui = await widget({ operator: true });
    await ui.openCase(7);
    ui.node("textarea").value = "  Đã đến hiện trường  ";
    const sent = caseState(7, { messages: [...caseState().messages, { id: 71, body: "Đã đến hiện trường", sender_name: "Cộng tác viên", recipient_name: "Admin chính", is_own: true, created_at: "2026-11-10T09:00:00+07:00", read_at: null }] });
    ui.states.set(7, sent);
    await ui.submit();
    const request = ui.requests.find((item) => item.options.method === "POST");
    assert.equal(request.url, "http://localhost:8000/cases/7/messages/");
    assert.equal(request.options.body.get("recipient"), "2");
    assert.equal(request.options.body.get("body"), "Đã đến hiện trường");
    assert.equal(request.options.body.get("csrfmiddlewaretoken"), "csrf-token");
    assert.equal(request.options.body.get("attachments"), undefined);
    assert.equal(ui.node("textarea").value, "");
    assert.match(content(ui.node("messages")), /Đã đến hiện trường/);
});

test("admin must choose a recipient when multiple helpers are assigned and cannot retain a removed recipient", async () => {
    const ui = await widget({ operator: true });
    const recipients = [{ id: 2, name: "Trung tâm A" }, { id: 3, name: "Cộng tác viên B" }];
    ui.states.set(7, caseState(7, { recipients }));
    await ui.openCase(7);
    assert.equal(ui.node("recipient").value, "");
    assert.equal(ui.node("submit").disabled, true);
    ui.node("recipient").value = "2";
    ui.node("recipient").handlers.change();
    assert.equal(ui.node("submit").disabled, false);
    ui.states.set(7, caseState(7, { recipients: [] }));
    await ui.tick();
    assert.equal(ui.node("recipient").value, "");
    assert.equal(ui.node("submit").disabled, true);
});

test("revoked access clears private messages, case title and recipient labels on the next update", async () => {
    const ui = await widget({ operator: true });
    await ui.openCase(7);
    ui.intercept = () => ({ ok: false, status: 404, json: async () => ({ error: "Không tìm thấy" }) });
    await ui.tick();
    assert.equal(content(ui.node("messages")).trim(), "");
    assert.equal(ui.node("case-title").textContent, "");
    assert.equal(ui.node("recipient").children.length, 0);
    assert.equal(ui.node("submit").disabled, true);
    assert.equal(ui.node("feedback").hidden, false);
});

test("a late response for another case never appears after switching conversations", async () => {
    const ui = await widget({ operator: true });
    const oldResponse = deferred();
    ui.intercept = (request) => request.url.includes("/cases/7/") ? oldResponse.promise : null;
    ui.clickCase(7);
    await ui.openCase(8);
    oldResponse.resolve({ ok: true, json: async () => caseState(7) });
    await settle();
    assert.match(content(ui.node("messages")), /Chỉ dẫn riêng ca 8/);
    assert.doesNotMatch(content(ui.node("messages")), /Chỉ dẫn riêng ca 7/);
    assert.equal(ui.node("case-title").textContent, "Ca cứu hộ 8");
});

test("closing case chat clears private content and stops requests that would mark unopened messages read", async () => {
    const ui = await widget({ operator: true });
    await ui.openCase(7);
    await ui.close();
    const count = ui.requests.length;
    await ui.tick();
    assert.equal(ui.requests.length, count);
    assert.equal(content(ui.node("messages")).trim(), "");
    await ui.openCase(7);
    assert.match(content(ui.node("messages")), /Chỉ dẫn riêng ca 7/);
});

test("case chat rejects an unexpected case payload and login redirects instead of showing stale private data", async () => {
    for (const response of [
        { ok: true, json: async () => caseState(8) },
        { ok: true, redirected: true, status: 200, json: async () => { throw new Error("HTML login page"); } },
    ]) {
        const ui = await widget({ operator: true });
        await ui.openCase(7);
        ui.intercept = () => response;
        await ui.tick();
        assert.equal(content(ui.node("messages")).trim(), "");
        assert.equal(ui.node("submit").disabled, true);
        assert.equal(ui.node("case-title").textContent, "");
    }
});

test("send validation keeps the draft but revoked permissions remove both messages and draft", async () => {
    const ui = await widget({ operator: true });
    await ui.openCase(7);
    ui.node("textarea").value = "Ghi chú tại hiện trường";
    ui.intercept = (request) => request.options.method === "POST" ? { ok: false, status: 400, json: async () => ({ error: "Hãy kiểm tra nội dung" }) } : null;
    await ui.submit();
    assert.equal(ui.node("textarea").value, "Ghi chú tại hiện trường");
    assert.match(content(ui.node("messages")), /Chỉ dẫn riêng ca 7/);
    ui.intercept = (request) => request.options.method === "POST" ? { ok: false, status: 403, json: async () => ({ error: "Không có quyền" }) } : null;
    await ui.submit();
    assert.equal(ui.node("textarea").value, "");
    assert.equal(content(ui.node("messages")).trim(), "");
    assert.equal(ui.node("submit").disabled, true);
});

test("a late send response never erases the draft or shows the messages of a different case", async () => {
    const ui = await widget({ operator: true });
    await ui.openCase(7);
    const oldResponse = deferred();
    ui.intercept = (request) => request.options.method === "POST" ? oldResponse.promise : null;
    ui.node("textarea").value = "Gửi ở ca 7";
    const sending = ui.submit();
    await ui.openCase(8);
    ui.node("textarea").value = "Bản nháp của ca 8";
    oldResponse.resolve({ ok: true, status: 201, json: async () => caseState(7) });
    await sending;
    assert.equal(ui.node("textarea").value, "Bản nháp của ca 8");
    assert.match(content(ui.node("messages")), /Chỉ dẫn riêng ca 8/);
    assert.doesNotMatch(content(ui.node("messages")), /Chỉ dẫn riêng ca 7/);
    assert.equal(ui.node("submit").disabled, false);
});

test("a pending successful send cannot restore private content after a poll revokes access", async () => {
    const ui = await widget({ operator: true });
    await ui.openCase(7);
    const pendingSend = deferred();
    ui.intercept = (request) => request.options.method === "POST" ? pendingSend.promise : { ok: false, status: 404, json: async () => ({ error: "Không còn được giao ca" }) };
    ui.node("textarea").value = "Đang gửi chỉ dẫn";
    const sending = ui.submit();
    await ui.tick();
    pendingSend.resolve({ ok: true, status: 201, json: async () => caseState(7) });
    await sending;
    assert.equal(content(ui.node("messages")).trim(), "");
    assert.equal(ui.node("recipient").children.length, 0);
    assert.equal(ui.node("submit").disabled, true);
});

test("private chat renders names, case titles and bodies as text rather than HTML", async () => {
    const ui = await widget({ operator: true });
    const dangerous = '<img src=x onerror="alert(1)">';
    ui.states.set(7, caseState(7, { title: dangerous, recipients: [{ id: 2, name: dangerous }], messages: [{ ...caseState().messages[0], body: dangerous, sender_name: dangerous }] }));
    await ui.openCase(7);
    assert.equal(ui.node("case-title").textContent, dangerous);
    assert.match(content(ui.node("messages")), /<img src=x/);
    assert.equal(descendants(ui.node("messages")).filter((item) => item.tagName === "img").length, 0);
    assert.ok(descendants(ui.node("messages")).every((item) => item.innerHTML === undefined));
});

test("middle, modified and external case links keep native browser navigation", async () => {
    const ui = await widget({ operator: true });
    for (const options of [{ button: 1 }, { ctrlKey: true }, { metaKey: true }, { shiftKey: true }, { altKey: true }, { defaultPrevented: true }]) {
        assert.equal(ui.clickCase(7, options), false);
    }
    let prevented = false;
    ui.document.handlers.click({ button: 0, target: { closest: () => ({ dataset: { caseChatUrl: "https://other.example/cases/7/messages/" } }) }, preventDefault() { prevented = true; } });
    assert.equal(prevented, false);
    assert.equal(ui.requests.length, 0);
});
