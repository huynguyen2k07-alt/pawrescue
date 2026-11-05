(() => {
    const MIN_POLL_INTERVAL_MS = 5000;
    const REQUEST_TIMEOUT_MS = 10000;
    const MAX_RETRY_DELAY_MS = 30000;
    const DAYS_IN_WINDOW = 7;
    const MILLISECONDS_PER_DAY = 24 * 60 * 60 * 1000;
    const PNG_DATA_URL = /^data:image\/png;base64,[A-Za-z0-9+/]+={0,2}$/;

    const root = document.querySelector("[data-public-statistics]");
    if (!root || typeof fetch !== "function") return;

    const nodes = {
        total: root.querySelector("[data-statistics-total]"),
        rescued: root.querySelector("[data-statistics-rescued]"),
        average: root.querySelector("[data-statistics-average]"),
        statusChart: root.querySelector("[data-statistics-status-chart]"),
        dailyChart: root.querySelector("[data-statistics-daily-chart]"),
        window: root.querySelector("[data-statistics-window]"),
        statusRows: root.querySelector("[data-statistics-status-rows]"),
        dailyRows: root.querySelector("[data-statistics-daily-rows]"),
        status: root.querySelector("[data-statistics-status]"),
        checkedAt: root.querySelector("[data-statistics-checked-at]"),
        refresh: root.querySelector("[data-statistics-refresh]"),
    };
    if (!root.dataset.url || Object.values(nodes).some((node) => !node)) return;

    const configuredInterval = Number(root.dataset.pollInterval);
    const interval = Number.isFinite(configuredInterval) && configuredInterval >= MIN_POLL_INTERVAL_MS
        ? Math.min(configuredInterval, MAX_RETRY_DELAY_MS) : MIN_POLL_INTERVAL_MS;
    let version = root.dataset.version || "";
    let timeZone = root.dataset.timeZone || "Asia/Ho_Chi_Minh";
    let timer = null;
    let inFlight = false;
    let refreshAfterRequest = false;
    let failures = 0;

    function isOnline() {
        return typeof navigator === "undefined" || navigator.onLine !== false;
    }

    function showState(state, text) {
        if (nodes.status.getAttribute("data-state") !== state) nodes.status.setAttribute("data-state", state);
        if (nodes.status.textContent !== text) nodes.status.textContent = text;
    }

    function clearPoll() {
        if (timer !== null) clearTimeout(timer);
        timer = null;
    }

    function schedule(delay) {
        // ===== CHỨC NĂNG CHÍNH: TỰ CẬP NHẬT BIỂU ĐỒ =====
        // Chỉ kiểm tra định kỳ khi trang đang mở và có mạng; mỗi lần chỉ chạy một yêu cầu.
        clearPoll();
        if (document.hidden || !isOnline()) return;
        timer = setTimeout(() => {
            timer = null;
            refresh();
        }, delay);
    }

    function updateCheckedAt(value) {
        if (!isTimestamp(value)) return;
        const date = new Date(value);
        const options = {
            day: "2-digit", month: "2-digit", year: "numeric",
            hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone,
        };
        let formatted;
        try {
            formatted = new Intl.DateTimeFormat("vi-VN", options).format(date);
        } catch {
            formatted = date.toLocaleString("vi-VN");
        }
        nodes.checkedAt.dateTime = value;
        nodes.checkedAt.textContent = formatted;
    }

    function isCount(value) {
        return Number.isSafeInteger(value) && value >= 0;
    }

    function isTimestamp(value) {
        return typeof value === "string" && Number.isFinite(Date.parse(value));
    }

    function isDay(value) {
        if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
        const parsed = new Date(value + "T00:00:00Z");
        return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
    }

    function validStatusRows(rows) {
        return Array.isArray(rows) && rows.length > 0 && rows.length <= 20
            && rows.every((row) => row && typeof row.label === "string" && isCount(row.count));
    }

    function validDailyRows(rows) {
        if (!Array.isArray(rows) || rows.length !== DAYS_IN_WINDOW) return false;
        return rows.every((row, index) => {
            if (!row || !isDay(row.date) || !isCount(row.count)) return false;
            if (index === 0) return true;
            const previousDay = Date.parse(rows[index - 1].date);
            return Date.parse(row.date) - previousDay === MILLISECONDS_PER_DAY;
        });
    }

    function validPayload(data) {
        // ===== CHỨC NĂNG CHÍNH: KIỂM TRA DỮ LIỆU BIỂU ĐỒ =====
        // Kiểm tra đủ ảnh PNG, số đếm và bảy ngày liên tiếp trước khi thay số liệu đang hiển thị.
        if (!data || typeof data !== "object") return false;
        const metadataIsValid = typeof data.version === "string" && data.version.length > 0
            && typeof data.time_zone === "string" && data.time_zone.length > 0
            && isTimestamp(data.checked_at);
        const summaryIsValid = isCount(data.total) && isCount(data.rescued_count)
            && typeof data.daily_average === "number" && Number.isFinite(data.daily_average) && data.daily_average >= 0
            && typeof data.window_label === "string";
        const chartsAreValid = typeof data.status_chart === "string" && PNG_DATA_URL.test(data.status_chart)
            && typeof data.daily_chart === "string" && PNG_DATA_URL.test(data.daily_chart);
        return metadataIsValid && summaryIsValid && chartsAreValid
            && validStatusRows(data.status_rows) && validDailyRows(data.daily_rows);
    }

    function tableRows(rows, heading) {
        return rows.map((row) => {
            const tr = document.createElement("tr");
            const th = document.createElement("th");
            const td = document.createElement("td");
            th.setAttribute("scope", "row");
            th.textContent = heading(row);
            td.textContent = String(row.count);
            tr.appendChild(th);
            tr.appendChild(td);
            return tr;
        });
    }

    function render(data) {
        const statusRows = tableRows(data.status_rows, (row) => row.label);
        const dailyRows = tableRows(data.daily_rows, (row) => row.date.split("-").reverse().join("/"));
        // ===== CHỨC NĂNG CHÍNH: HIỂN THỊ SỐ LIỆU MỚI =====
        // Chỉ cập nhật số liệu; giữ nguyên phần đang mở, vị trí đọc và liên kết trên trang.
        nodes.total.textContent = String(data.total);
        nodes.rescued.textContent = String(data.rescued_count);
        nodes.average.textContent = new Intl.NumberFormat("vi-VN", {
            minimumFractionDigits: 2, maximumFractionDigits: 2,
        }).format(data.daily_average);
        nodes.window.textContent = data.window_label;
        nodes.statusChart.setAttribute("src", data.status_chart);
        nodes.dailyChart.setAttribute("src", data.daily_chart);
        nodes.statusRows.replaceChildren(...statusRows);
        nodes.dailyRows.replaceChildren(...dailyRows);
        version = data.version;
        timeZone = data.time_zone;
        root.dataset.version = version;
        root.dataset.timeZone = timeZone;
    }

    async function refresh() {
        if (document.hidden || !isOnline() || inFlight) return;
        clearPoll();
        inFlight = true;
        nodes.refresh.disabled = true;
        root.setAttribute("aria-busy", "true");
        const controller = typeof AbortController === "function" ? new AbortController() : null;
        const timeout = controller ? setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS) : null;
        let nextDelay = interval;
        try {
            const headers = { Accept: "application/json" };
            if (version) headers["If-None-Match"] = `"${version}"`;
            const options = { credentials: "same-origin", cache: "no-store", headers };
            if (controller) options.signal = controller.signal;
            const response = await fetch(root.dataset.url, options);
            // ===== CHỨC NĂNG CHÍNH: ĐỐI CHIẾU PHIÊN BẢN DỮ LIỆU =====
            // Mã 304 nghĩa là dữ liệu chưa đổi: chỉ cập nhật giờ kiểm tra, giữ nguyên biểu đồ và bảng.
            if (response.status === 304) {
                updateCheckedAt(response.headers.get("X-Statistics-Checked-At"));
                showState("ready", "Số liệu vẫn đang mới nhất.");
            } else {
                if (!response.ok) throw new Error("statistics-unavailable");
                const data = await response.json();
                if (!validPayload(data)) throw new Error("statistics-invalid");
                const changed = data.version !== version;
                if (changed) render(data);
                updateCheckedAt(response.headers.get("X-Statistics-Checked-At") || data.checked_at);
                showState("ready", changed
                    ? `Đã cập nhật số liệu lúc ${nodes.checkedAt.textContent}.`
                    : "Số liệu vẫn đang mới nhất.");
            }
            failures = 0;
        } catch {
            failures += 1;
            nextDelay = Math.min(interval * (2 ** Math.min(failures, 4)), MAX_RETRY_DELAY_MS);
            showState("error", "Chưa cập nhật được. Giữ số liệu đã tải và sẽ thử lại.");
        } finally {
            if (timeout !== null) clearTimeout(timeout);
            inFlight = false;
            nodes.refresh.disabled = false;
            root.setAttribute("aria-busy", "false");
            const updateNow = refreshAfterRequest;
            refreshAfterRequest = false;
            if (document.hidden) {
                showState("paused", "Tạm dừng cập nhật khi bạn rời trang.");
            } else if (!isOnline()) {
                showState("offline", "Mất kết nối mạng. Đang giữ số liệu đã tải.");
            } else if (updateNow) {
                refresh();
            } else {
                schedule(nextDelay);
            }
        }
    }

    function resume() {
        clearPoll();
        if (document.hidden) {
            showState("paused", "Tạm dừng cập nhật khi bạn rời trang.");
        } else if (!isOnline()) {
            showState("offline", "Mất kết nối mạng. Đang giữ số liệu đã tải.");
        } else if (inFlight) {
            refreshAfterRequest = true;
        } else {
            refresh();
        }
    }

    nodes.refresh.addEventListener("click", () => {
        if (!inFlight) resume();
    });
    document.addEventListener("visibilitychange", resume);
    window.addEventListener("online", resume);
    window.addEventListener("offline", resume);
    updateCheckedAt(root.dataset.checkedAt);
    if (document.hidden) {
        showState("paused", "Tạm dừng cập nhật khi bạn rời trang.");
    } else if (!isOnline()) {
        showState("offline", "Mất kết nối mạng. Đang giữ số liệu đã tải.");
    } else {
        schedule(interval);
    }
})();
