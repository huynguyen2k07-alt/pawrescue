(function () {
    "use strict";

    const root = document.querySelector("[data-live-notifications]");
    if (!root) return;
    const userId = root.dataset.userId;
    const baselineId = Number(root.dataset.latestId || 0);
    const toastContainer = root.querySelector("[data-notification-toasts]");
    const list = document.querySelector("[data-live-notification-list]");
    const seenIds = new Set();
    let timer = null;
    let activeRequest = null;
    let generation = 0;
    let stopped = false;
    let pageSuspended = false;
    let failures = 0;
    let etag = "";
    let version = "";
    let readRequest = null;

    function sameOriginUrl(value) {
        if (typeof value !== "string" || !value || value.length > 2048) return null;
        try {
            const url = new URL(value, window.location.origin);
            if (url.origin !== window.location.origin || !["http:", "https:"].includes(url.protocol) || url.username || url.password) return null;
            return url.pathname + url.search + url.hash;
        } catch (_) {
            return null;
        }
    }

    const stateUrl = sameOriginUrl(root.dataset.stateUrl);
    const listUrl = sameOriginUrl(root.dataset.listUrl);
    if (!stateUrl || !listUrl || !/^\d+$/.test(userId || "")) return;

    function available() {
        return !stopped && !pageSuspended && !document.hidden && document.visibilityState !== "hidden" && navigator.onLine !== false;
    }

    function setText(element, value) {
        if (element.textContent !== value) element.textContent = value;
    }

    function updateCounts(unread, total, supportUnread) {
        document.querySelectorAll("[data-notification-link]").forEach(function (link) {
            link.classList.toggle("has-unread", unread > 0);
            link.setAttribute("aria-label", unread ? `Thông báo, ${unread} chưa đọc` : "Thông báo");
        });
        document.querySelectorAll("[data-notification-count]").forEach(function (badge) {
            setText(badge, String(unread));
            badge.hidden = unread === 0;
        });
        document.querySelectorAll("[data-support-unread-count]").forEach(function (badge) {
            setText(badge, String(supportUnread));
            badge.hidden = supportUnread === 0;
        });
        document.querySelectorAll("[data-notification-total-count]").forEach(function (node) { setText(node, String(total)); });
        document.querySelectorAll("[data-notification-unread-count]").forEach(function (node) { setText(node, String(unread)); });
        document.querySelectorAll("[data-notification-read-all]").forEach(function (node) { node.hidden = unread === 0; });
    }

    function pause() {
        generation += 1;
        window.clearTimeout(timer);
        timer = null;
        if (activeRequest) {
            const request = activeRequest;
            activeRequest = null;
            window.clearTimeout(request.timeout);
            request.cancel();
        }
    }

    function endSession() {
        stopped = true;
        pause();
        updateCounts(0, 0, 0);
        if (toastContainer) toastContainer.replaceChildren();
        if (list) list.replaceChildren();
        document.querySelectorAll("[data-notification-new-items]").forEach(function (node) { node.hidden = true; });
        document.querySelectorAll("[data-notification-older]").forEach(function (node) { node.hidden = true; });
    }

    function validCount(value) {
        return Number.isSafeInteger(value) && value >= 0;
    }

    // ===== CHỨC NĂNG CHÍNH: KIỂM TRA THÔNG BÁO RIÊNG TRƯỚC KHI HIỂN THỊ =====
    // Kiểm tra toàn bộ dữ liệu và liên kết trước; không cập nhật nửa chừng khi phản hồi sai định dạng.
    function validateState(data) {
        if (!data || typeof data !== "object" || Array.isArray(data)) throw new Error("Invalid notification state");
        if (String(data.user_id) !== userId) {
            if (validCount(data.user_id) || (typeof data.user_id === "string" && /^\d+$/.test(data.user_id))) endSession();
            throw new Error("Notification session changed");
        }
        if (typeof data.version !== "string" || !/^[\w.:-]{1,200}$/.test(data.version) ||
            !validCount(data.unread_count) || !validCount(data.total_count) || !validCount(data.latest_id) ||
            !validCount(data.support_unread_count) || data.unread_count > data.total_count) throw new Error("Invalid notification counts");

        function itemsFrom(items, onlyUnread) {
            if (!Array.isArray(items) || items.length > 20) throw new Error("Invalid notification items");
            const ids = new Set();
            return items.map(function (item) {
                if (!item || typeof item !== "object" || !Number.isSafeInteger(item.id) || item.id <= 0 || item.id > data.latest_id || ids.has(item.id) ||
                    typeof item.kind !== "string" || !/^[a-z_]{1,40}$/.test(item.kind) ||
                    typeof item.title !== "string" || item.title.length > 500 ||
                    typeof item.is_read !== "boolean" || (onlyUnread && item.is_read) ||
                    typeof item.created_at !== "string" || !Number.isFinite(Date.parse(item.created_at))) throw new Error("Invalid notification item");
                const url = sameOriginUrl(item.url);
                const openUrl = sameOriginUrl(item.open_url);
                if (!url || !openUrl) throw new Error("Unsafe notification link");
                ids.add(item.id);
                return { id: item.id, kind: item.kind, title: item.title, is_read: item.is_read, created_at: item.created_at, url, open_url: openUrl };
            });
        }

        const items = itemsFrom(data.items, false);
        const unreadItems = itemsFrom(data.unread_items, true);
        if (items.length > data.total_count || unreadItems.length > data.unread_count) throw new Error("Inconsistent notification counts");
        return { ...data, items, unread_items: unreadItems };
    }

    function makeToast(title, url, id) {
        const article = document.createElement("article");
        article.className = "live-notification-toast";
        article.setAttribute(id ? "data-notification-toast-id" : "data-notification-toast-summary", id ? String(id) : "");
        const copy = document.createElement("p");
        copy.textContent = title;
        const link = document.createElement("a");
        link.href = url;
        link.textContent = "Xem";
        const close = document.createElement("button");
        close.type = "button";
        close.className = "notification-toast-close";
        close.setAttribute("aria-label", "Đóng thông báo");
        close.textContent = "×";
        close.addEventListener("click", function () { article.remove(); });
        article.append(copy, link, close);
        return article;
    }

    function showNewNotifications(state) {
        if (toastContainer) {
            const unreadIds = new Set(state.unread_items.map(function (item) { return item.id; }));
            toastContainer.querySelectorAll("[data-notification-toast-id]").forEach(function (toast) {
                if (!unreadIds.has(Number(toast.dataset.notificationToastId))) toast.remove();
            });
            toastContainer.querySelectorAll("[data-notification-toast-summary]").forEach(function (toast) { toast.remove(); });
        }
        const arrivals = state.unread_items.filter(function (item) {
            return item.id > baselineId && !seenIds.has(item.id);
        });
        state.items.concat(state.unread_items).forEach(function (item) { seenIds.add(item.id); });
        if (!toastContainer || !arrivals.length) return;
        if (arrivals.length > 3) {
            toastContainer.replaceChildren();
            arrivals.slice(0, 2).forEach(function (item) { toastContainer.appendChild(makeToast(item.title, item.url, item.id)); });
            toastContainer.appendChild(makeToast(`Có ${arrivals.length} thông báo mới.`, listUrl));
        } else {
            arrivals.forEach(function (item) { toastContainer.appendChild(makeToast(item.title, item.url, item.id)); });
            while (toastContainer.children.length > 3) toastContainer.firstElementChild.remove();
        }
    }

    function displayTime(value) {
        return new Date(value).toLocaleString("vi-VN", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
    }

    function makeReadForm(item) {
        const token = list.dataset.csrfToken;
        if (!token) return null;
        const form = document.createElement("form");
        form.setAttribute("data-notification-read-form", "");
        form.method = "post";
        form.action = item.open_url;
        const csrf = document.createElement("input");
        csrf.type = "hidden";
        csrf.name = "csrfmiddlewaretoken";
        csrf.value = token;
        const button = document.createElement("button");
        button.type = "submit";
        button.className = "button button-ghost button-small";
        button.textContent = "Đánh dấu đã đọc";
        form.append(csrf, button);
        return form;
    }

    function makeRow(item) {
        const row = document.createElement("article");
        row.className = "notification-item";
        row.setAttribute("data-notification-id", String(item.id));
        const wrapper = document.createElement("div");
        wrapper.className = "notification-open";
        const icon = document.createElement("span");
        icon.className = `notification-kind notification-kind-${item.kind}`;
        icon.setAttribute("aria-hidden", "true");
        icon.textContent = "↻";
        const content = document.createElement("div");
        content.className = "notification-content";
        const heading = document.createElement("div");
        heading.className = "notification-title-row";
        const strong = document.createElement("strong");
        const title = document.createElement("a");
        title.setAttribute("data-notification-title", "");
        const time = document.createElement("time");
        strong.appendChild(title);
        heading.append(strong, time);
        content.appendChild(heading);
        const actions = document.createElement("div");
        actions.className = "notification-live-actions";
        const link = document.createElement("a");
        link.href = item.url;
        link.textContent = "Xem nội dung →";
        actions.appendChild(link);
        const form = makeReadForm(item);
        if (form) actions.appendChild(form);
        content.appendChild(actions);
        const dot = document.createElement("span");
        dot.className = "unread-dot";
        dot.setAttribute("aria-label", "Chưa đọc");
        wrapper.append(icon, content, dot);
        row.appendChild(wrapper);
        return row;
    }

    function setRowRead(row, isRead) {
        row.classList.toggle("unread", !isRead);
        row.setAttribute("data-notification-read", String(isRead));
        const form = row.querySelector("[data-notification-read-form]");
        if (form) form.hidden = isRead;
        const dot = row.querySelector(".unread-dot");
        if (dot) dot.hidden = isRead;
    }

    function updateRow(row, item) {
        setRowRead(row, item.is_read);
        const title = row.querySelector("[data-notification-title]");
        if (title) {
            setText(title, item.title);
            if (title.getAttribute("href") !== item.url) title.href = item.url;
        }
        const actions = row.querySelector(".notification-live-actions");
        if (actions) actions.querySelectorAll("a").forEach(function (link) {
            if (link.getAttribute("href") !== item.url) link.href = item.url;
        });
        const time = row.querySelector("time");
        if (time && time.getAttribute("datetime") !== item.created_at) {
            time.setAttribute("datetime", item.created_at);
            setText(time, displayTime(item.created_at));
        }
        const form = row.querySelector("[data-notification-read-form]");
        if (form) {
            if (form.getAttribute("action") !== item.open_url) form.action = item.open_url;
        }
    }

    function updateList(state) {
        if (!list) return;
        const filter = list.dataset.filter === "unread" ? "unread" : "all";
        const filteredCount = filter === "unread" ? state.unread_count : state.total_count;
        document.querySelectorAll("[data-notification-older]").forEach(function (node) { node.hidden = filteredCount <= 20; });
        const cue = document.querySelector("[data-notification-new-items]");
        if (Number(list.dataset.page || 1) !== 1) {
            if (cue && state.latest_id > baselineId) cue.hidden = false;
            return;
        }
        const items = filter === "unread" ? state.unread_items : state.items;
        const existing = new Map(Array.from(list.querySelectorAll("[data-notification-id]")).map(function (row) { return [Number(row.dataset.notificationId), row]; }));
        const wanted = new Set(items.map(function (item) { return item.id; }));
        existing.forEach(function (row, id) { if (!wanted.has(id)) row.remove(); });
        let previous = null;
        items.forEach(function (item) {
            const row = existing.get(item.id) || makeRow(item);
            updateRow(row, item);
            const expected = previous ? previous.nextElementSibling : list.firstElementChild;
            if (expected !== row) list.insertBefore(row, expected);
            previous = row;
        });
        const empty = list.querySelector("[data-notification-empty]");
        if (items.length && empty) empty.remove();
        if (!items.length && !empty) {
            const message = document.createElement("p");
            message.className = "empty-state compact-empty";
            message.setAttribute("data-notification-empty", "");
            message.textContent = filter === "unread" ? "Bạn đã đọc hết thông báo." : "Chưa có thông báo nào.";
            list.appendChild(message);
        }
        if (cue) cue.hidden = true;
    }

    function schedule(delay) {
        window.clearTimeout(timer);
        if (available()) timer = window.setTimeout(refresh, delay);
    }

    // ===== CHỨC NĂNG CHÍNH: TỰ CẬP NHẬT THÔNG BÁO Ở MỌI TRANG =====
    // Mỗi lần chỉ có một yêu cầu; dừng khi ẩn tab hoặc mất mạng và bỏ qua phản hồi của phiên cũ.
    async function refresh() {
        if (!available() || activeRequest || readRequest) return;
        window.clearTimeout(timer);
        const requestGeneration = generation;
        const controller = typeof AbortController !== "undefined" ? new AbortController() : null;
        let rejectWait;
        const cancelled = new Promise(function (_, reject) { rejectWait = reject; });
        const request = {
            timeout: null,
            cancel() {
                if (controller) controller.abort();
                rejectWait(new Error("Notification request cancelled"));
            },
        };
        activeRequest = request;
        request.timeout = window.setTimeout(request.cancel, 8000);
        const headers = { Accept: "application/json" };
        if (etag) headers["If-None-Match"] = etag;
        try {
            const responseAndData = (async function () {
                const response = await fetch(stateUrl, { credentials: "same-origin", cache: "no-store", headers, ...(controller ? { signal: controller.signal } : {}) });
                const data = response.status === 304 || response.status === 401 || response.status === 403 || response.redirected || !response.ok ? null : await response.json();
                return { response, data };
            })();
            const result = await Promise.race([responseAndData, cancelled]);
            if (generation !== requestGeneration || activeRequest !== request || !available()) return;
            const { response, data } = result;
            if (response.status === 401 || response.status === 403 || response.redirected) {
                endSession();
                return;
            }
            if (response.status !== 304) {
                if (!response.ok) throw new Error("Cannot load notifications");
                const state = validateState(data);
                if (stopped) return;
                if (state.version !== version) {
                    updateCounts(state.unread_count, state.total_count, state.support_unread_count);
                    updateList(state);
                    showNewNotifications(state);
                    version = state.version;
                }
                const responseEtag = response.headers && response.headers.get("ETag");
                etag = typeof responseEtag === "string" && responseEtag && !/[\r\n]/.test(responseEtag) ? responseEtag : `"${state.version}"`;
            }
            failures = 0;
        } catch (_) {
            if (generation === requestGeneration && !stopped) failures += 1;
        } finally {
            window.clearTimeout(request.timeout);
            if (activeRequest === request) activeRequest = null;
            if (generation === requestGeneration) schedule(Math.min(30000, 2000 * (2 ** Math.min(failures, 4))));
        }
    }

    // Đánh dấu bằng POST có CSRF, cập nhật tại chỗ và giữ nguyên trang cùng vị trí cuộn.
    document.addEventListener("submit", async function (event) {
        const form = event.target;
        const readAll = form.matches("[data-notification-read-all]");
        if (!list || (!readAll && !form.matches("[data-notification-read-form]"))) return;
        event.preventDefault();
        if (readRequest || stopped) return;
        const status = document.querySelector("[data-notification-read-status]");
        const action = sameOriginUrl(form.action);
        const token = list.dataset.csrfToken;
        if (!action || !token) {
            if (status) status.textContent = "Không thể đánh dấu. Hãy đăng nhập lại rồi thử lại.";
            return;
        }
        pause();
        const requestGeneration = generation;
        const button = form.querySelector("button");
        if (button) button.disabled = true;
        form.setAttribute("aria-busy", "true");
        if (status) status.textContent = "Đang đánh dấu đã đọc…";
        const controller = typeof AbortController !== "undefined" ? new AbortController() : null;
        let rejectWait;
        const cancelled = new Promise(function (_, reject) { rejectWait = reject; });
        const request = {
            timeout: null,
            cancel() {
                if (controller) controller.abort();
                rejectWait(new Error("Read request cancelled"));
            },
        };
        readRequest = request;
        request.timeout = window.setTimeout(request.cancel, 8000);
        try {
            const responseAndData = (async function () {
                const response = await fetch(action, {
                    method: "POST", credentials: "same-origin", cache: "no-store", redirect: "error",
                    headers: { Accept: "application/json", "X-CSRFToken": token },
                    ...(controller ? { signal: controller.signal } : {}),
                });
                if (!response.ok || response.redirected) throw new Error("Cannot mark notification read");
                return response.json();
            })();
            const data = await Promise.race([responseAndData, cancelled]);
            if (generation !== requestGeneration || stopped) return;
            const state = validateState(data);
            if (stopped) return;
            if (readAll) list.querySelectorAll("[data-notification-id]").forEach(function (row) { setRowRead(row, true); });
            else {
                const row = form.closest("[data-notification-id]");
                if (row) setRowRead(row, true);
            }
            updateCounts(state.unread_count, state.total_count, state.support_unread_count);
            updateList(state);
            showNewNotifications(state);
            version = state.version;
            etag = "";
            if (status) status.textContent = readAll ? "Đã đánh dấu tất cả thông báo là đã đọc." : "Đã đánh dấu thông báo là đã đọc.";
        } catch (_) {
            if (generation === requestGeneration && !stopped && status) status.textContent = "Chưa đánh dấu được. Kiểm tra kết nối rồi thử lại.";
        } finally {
            window.clearTimeout(request.timeout);
            readRequest = null;
            if (button) button.disabled = false;
            form.setAttribute("aria-busy", "false");
            refresh();
        }
    });

    document.addEventListener("visibilitychange", function () {
        if (available()) refresh();
        else pause();
    });
    window.addEventListener("offline", pause);
    window.addEventListener("online", refresh);
    window.addEventListener("focus", refresh);
    window.addEventListener("pagehide", function () { pageSuspended = true; pause(); });
    window.addEventListener("pageshow", function () { pageSuspended = false; refresh(); });
    refresh();
})();
