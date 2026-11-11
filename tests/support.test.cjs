const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

function element(tagName = "div") {
    const classes = new Set();
    const item = {
        tagName, dataset: {}, children: [], textContent: "", hidden: false,
        value: "", files: [], scrollTop: 0, scrollHeight: 100, handlers: {},
        classList: {
            add(name) { classes.add(name); },
            remove(name) { classes.delete(name); },
            toggle(name, value) {
                const present = value === undefined ? !classes.has(name) : Boolean(value);
                if (present) classes.add(name); else classes.delete(name);
            },
            [Symbol.iterator]() { return classes[Symbol.iterator](); },
        },
        append(...items) {
            for (const child of items) {
                if (child.isFragment) this.children.push(...child.children);
                else this.children.push(child);
            }
        },
        appendChild(child) { this.append(child); return child; },
        replaceChildren(...items) { this.children = []; this.append(...items); },
        setAttribute(name, value) { this[name] = value; },
        addEventListener(name, callback) { this.handlers[name] = callback; },
        focus() {},
    };
    return item;
}

function descendants(item) {
    return [item, ...item.children.flatMap(descendants)];
}

function message(body = "Original request") {
    return { id: 1, body, sender_name: "User", is_admin: false, created_at: "10:00", attachments: [] };
}

async function supportUI({ inbox = false, closed = false } = {}) {
    const nodes = new Map();
    function node(selector) {
        if (!nodes.has(selector)) nodes.set(selector, element());
        return nodes.get(selector);
    }
    const root = node("root");
    const threadMessages = node("messages");
    const status = node("status");
    const reply = closed ? null : node("reply");
    const query = {
        "[data-conversation-list]": node("conversations"),
        "[data-conversation-count]": node("count"),
        "[data-thread-messages]": threadMessages,
        "[data-thread-status]": status,
        "[data-admin-reply-form]": reply,
        "[data-support-close]": node("close"),
        "[data-support-messages]": threadMessages,
        "[data-support-form]": node("form"),
        "[data-support-file-input]": node("file"),
        "[data-support-attachment-preview]": node("preview"),
        "[data-support-feedback]": node("feedback"),
        "[data-support-status]": status,
        "[data-support-badge]": node("badge"),
        "[data-support-toggle-title]": node("toggleTitle"),
        "[data-support-toggle-copy]": node("toggleCopy"),
        "[data-support-mode-tools]": node("modeTools"),
        "[data-support-default]": node("defaultButton"),
        "[data-support-full-page]": node("fullPageLink"),
        "[data-support-case-title]": node("caseTitle"),
        "[data-case-chat-recipient]": node("recipientControl"),
        "[data-case-chat-recipient-select]": node("recipientSelect"),
        "[data-support-attach-button]": node("attachButton"),
        "[data-support-privacy]": node("privacy"),
    };
    root.querySelector = (selector) => query[selector] || null;
    root.dataset = { stateUrl: "/support/state/", sendUrl: "/support/send/", selectedId: "1" };
    for (const form of [reply, node("form")].filter(Boolean)) {
        form.querySelector = (selector) => ({
            textarea: node("textarea"),
            "[data-admin-file-input]": node("file"),
            "[data-admin-attachment-preview]": node("preview"),
            "[data-support-file-input]": node("file"),
            "[data-support-attachment-preview]": node("preview"),
            "button[type='submit']": node("submit"),
        })[selector] || null;
    }
    let payload = inbox ? {
        conversations: [{ id: 1, name: "User", avatar: "U", status_label: "Waiting", last_message_at: "10:00", url: "/support/inbox/?conversation=1" }],
        selected: { id: 1, status: closed ? "closed" : "waiting_admin", status_label: "Waiting", messages: [message()] },
    } : { status_label: "Waiting", unread_count: 0, messages: [message()] };
    let poll;
    const navigations = [];
    const errors = [];
    let reloads = 0;
    const context = {
        URL,
        document: {
            hidden: false,
            handlers: {},
            querySelector() { return inbox ? root : null; },
            getElementById(id) {
                return { "support-chat": root, "support-chat-toggle": node("toggle"), "support-chat-panel": node("panel"), "support-chat-title": node("title") }[id] || null;
            },
            createElement: element,
            createDocumentFragment() { return { ...element(), isFragment: true }; },
            addEventListener(name, callback) { this.handlers[name] = callback; },
        },
        window: {
            location: {
                origin: "http://localhost:8000", pathname: "/support/inbox/",
                assign(url) { navigations.push(url); }, reload() { reloads += 1; },
            },
            setInterval(callback) { poll = callback; },
        },
        fetch: async () => ({ ok: true, json: async () => payload }),
        console: { warn(value) { errors.push(value); } },
    };
    const file = inbox ? "../static/admin/js/support-inbox.js" : "../static/js/support-chat.js";
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, file), "utf8"), context);
    await new Promise(setImmediate);
    return {
        messages: threadMessages, conversations: node("conversations"), root, document: context.document,
        navigations, errors,
        get reloads() { return reloads; },
        get payload() { return payload; },
        async update(next) { payload = next; await poll(); },
    };
}

for (const inbox of [false, true]) {
    test(`${inbox ? "admin inbox" : "user chat"} polling displays body corrections with the same message ID`, async () => {
        const ui = await supportUI({ inbox });
        assert.equal(descendants(ui.messages).find((item) => item.tagName === "p").textContent, "Original request");
        const next = structuredClone(ui.payload);
        (inbox ? next.selected.messages : next.messages)[0].body = '<script>alert("corrected")</script>';
        await ui.update(next);
        const body = descendants(ui.messages).find((item) => item.tagName === "p");
        assert.equal(body.textContent, '<script>alert("corrected")</script>');
        assert.equal(body.innerHTML, undefined);
        assert.deepEqual(ui.errors, []);
    });

    test(`${inbox ? "admin inbox" : "user chat"} polling removes deleted attachments from an existing message`, async () => {
        const ui = await supportUI({ inbox });
        const next = structuredClone(ui.payload);
        const messages = inbox ? next.selected.messages : next.messages;
        messages[0].attachments = [{ id: 4, media_type: "image", name: "private.png", url: "/support/attachments/4/" }];
        await ui.update(next);
        assert.equal(descendants(ui.messages).filter((item) => item.tagName === "img").length, 1);
        const withoutAttachment = structuredClone(next);
        (inbox ? withoutAttachment.selected.messages : withoutAttachment.messages)[0].attachments = [];
        await ui.update(withoutAttachment);
        assert.equal(descendants(ui.messages).filter((item) => item.tagName === "img").length, 0);
        assert.deepEqual(ui.errors, []);
    });
}

test("admin inbox refreshes its server-rendered controls when another operator closes or reopens", async () => {
    for (const closed of [false, true]) {
        const ui = await supportUI({ inbox: true, closed });
        const next = structuredClone(ui.payload);
        next.selected.status = closed ? "waiting_admin" : "closed";
        await ui.update(next);
        assert.equal(ui.reloads, 1);
        assert.deepEqual(ui.errors, []);
    }
});

test("admin inbox leaves a thread when reassignment removes its access", async () => {
    const ui = await supportUI({ inbox: true });
    await ui.update({
        conversations: [{ id: 2, name: "Other user", avatar: "O", status_label: "Waiting", last_message_at: "10:00", url: "/support/inbox/?conversation=2" }],
        selected: { id: 2, status: "waiting_admin", status_label: "Waiting", messages: [message("Other request")] },
    });
    assert.deepEqual(ui.navigations, ["/support/inbox/?conversation=2"]);
    assert.deepEqual(ui.errors, []);
});

test("admin inbox returns to the empty inbox after its final thread is deleted", async () => {
    const ui = await supportUI({ inbox: true });
    await ui.update({ conversations: [], selected: null });
    assert.deepEqual(ui.navigations, ["/support/inbox/"]);
    assert.deepEqual(ui.errors, []);
});

test("unchanged inbox polling preserves conversation links and their native navigation", async () => {
    const ui = await supportUI({ inbox: true });
    const link = descendants(ui.conversations).find((item) => item.tagName === "a");
    assert.equal(link.href, "/support/inbox/?conversation=1");
    await ui.update(structuredClone(ui.payload));
    const afterPoll = descendants(ui.conversations).find((item) => item.tagName === "a");
    assert.equal(afterPoll, link);
    assert.deepEqual(ui.navigations, []);
});

test("conversation links leave middle and modified clicks to the browser", async () => {
    const ui = await supportUI({ inbox: true });
    const link = descendants(ui.conversations).find((item) => item.tagName === "a");
    const cases = [
        { type: "mousedown", button: 1 },
        { type: "auxclick", button: 1 },
        { type: "click", button: 0, ctrlKey: true },
        { type: "click", button: 0, metaKey: true },
        { type: "click", button: 0, shiftKey: true },
        { type: "click", button: 0, altKey: true },
        { type: "click", button: 0, defaultPrevented: true },
    ];
    for (const options of cases) {
        let preventions = 0;
        const event = {
            target: link, defaultPrevented: false, ctrlKey: false, metaKey: false, shiftKey: false, altKey: false,
            ...options,
            preventDefault() { this.defaultPrevented = true; preventions += 1; },
            stopPropagation() {},
        };
        for (const node of [link, ui.conversations, ui.root, ui.document]) node.handlers[event.type]?.(event);
        assert.equal(preventions, 0, `${event.type}: button=${event.button}`);
        assert.equal(link.href, "/support/inbox/?conversation=1");
    }
    assert.deepEqual(ui.navigations, []);
});
