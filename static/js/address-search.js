// ===== CHỨC NĂNG CHÍNH: TÌM ĐỊA CHỈ VÀ CHỌN GHIM =====
// Chỉ tìm khi bấm nút; hủy kết quả cũ và yêu cầu người báo kiểm tra đúng hiện trường.
(function () {
    "use strict";

    const panel = document.querySelector("[data-address-search]");
    if (!panel) return;
    const addressInput = document.getElementById("id_address");
    const searchButton = document.getElementById("find-address");
    const resultsElement = document.getElementById("address-search-results");
    const statusElement = document.getElementById("address-search-status");
    if (!addressInput || !searchButton || !resultsElement || !statusElement) return;

    const deadline = 7000;
    const unavailableMessage = "Chưa thể tìm địa chỉ. Bạn có thể chọn ghim trên bản đồ.";
    const failureMessage = "Không tìm được địa chỉ lúc này. Vui lòng thử lại hoặc chọn ghim trên bản đồ.";
    let generation = 0;
    let activeRequest = null;

    function setBusy(busy) {
        searchButton.disabled = busy;
        searchButton.setAttribute("aria-busy", String(busy));
        panel.setAttribute("aria-busy", String(busy));
    }

    function isCurrent(request) {
        return activeRequest === request && request.generation === generation;
    }

    function finish(request) {
        if (!isCurrent(request)) return;
        window.clearTimeout(request.timer);
        activeRequest = null;
        setBusy(false);
    }

    function cancelSearch() {
        generation += 1;
        const request = activeRequest;
        activeRequest = null;
        if (request) {
            window.clearTimeout(request.timer);
            request.controller.abort();
        }
        resultsElement.replaceChildren();
        statusElement.textContent = "";
        setBusy(false);
    }

    function searchUrl() {
        const configuredUrl = panel.dataset.searchUrl;
        if (!configuredUrl) throw new Error("Missing search endpoint");
        const current = new URL(window.location.href);
        const url = new URL(configuredUrl, current);
        if (!/^https?:$/.test(url.protocol) || url.origin !== current.origin || url.username || url.password) {
            throw new Error("Invalid search endpoint");
        }
        return url.href;
    }

    function validResults(payload) {
        if (!payload || !Array.isArray(payload.results) || payload.results.length > 5) return false;
        return payload.results.every(function (result) {
            return result && typeof result === "object" && !Array.isArray(result)
                && typeof result.label === "string" && result.label.trim().length > 0 && result.label.length <= 500
                && typeof result.latitude === "number" && Number.isFinite(result.latitude)
                && typeof result.longitude === "number" && Number.isFinite(result.longitude)
                && result.latitude >= 15.85 && result.latitude <= 16.25
                && result.longitude >= 107.75 && result.longitude <= 108.35;
        });
    }

    function renderResults(results, resultGeneration) {
        resultsElement.replaceChildren();
        results.forEach(function (result) {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "address-search-result";
            const label = document.createElement("span");
            label.textContent = result.label;
            const hint = document.createElement("span");
            hint.className = "address-search-result-hint";
            hint.textContent = "Gợi ý địa chỉ — hãy kiểm tra và chỉnh ghim trên bản đồ.";
            button.appendChild(label);
            button.appendChild(hint);
            button.addEventListener("click", function () {
                if (generation !== resultGeneration || activeRequest || document.hidden) return;
                cancelSearch();
                panel.dispatchEvent(new CustomEvent("rescue:address-selected", {
                    bubbles: true,
                    detail: { latitude: result.latitude, longitude: result.longitude, label: result.label },
                }));
                statusElement.textContent = "Đã chọn gợi ý. Hãy kiểm tra, chỉnh ghim đúng hiện trường và xác nhận vị trí.";
            });
            resultsElement.appendChild(button);
        });
        statusElement.textContent = results.length
            ? "Chọn một gợi ý, sau đó kiểm tra ghim trên bản đồ trước khi xác nhận vị trí."
            : "Chưa tìm thấy địa chỉ phù hợp tại Đà Nẵng. Hãy thêm số nhà, tên đường hoặc chọn ghim trên bản đồ.";
    }

    function responseError(status) {
        if (status === 401 || status === 403) return "Phiên làm việc đã hết hạn. Vui lòng tải lại trang rồi thử lại.";
        if (status === 400) return "Địa chỉ chưa hợp lệ. Hãy nhập địa chỉ cụ thể tại Đà Nẵng rồi thử lại.";
        if (status === 429) return "Bạn đang tìm quá nhiều lần. Vui lòng đợi một lúc rồi thử lại.";
        if (status === 503) return "Dịch vụ tìm địa chỉ hiện chưa sẵn sàng. Bạn có thể chọn ghim trên bản đồ.";
        return failureMessage;
    }

    async function search() {
        if (activeRequest || document.hidden) return;
        const address = addressInput.value.trim();
        if (!address) {
            statusElement.textContent = "Nhập địa chỉ hoặc mốc nhận biết tại Đà Nẵng trước khi tìm.";
            return;
        }
        let url;
        try {
            url = searchUrl();
            if (!panel.dataset.csrfToken || typeof fetch !== "function" || typeof AbortController !== "function") {
                throw new Error("Search unavailable");
            }
        } catch (_) {
            statusElement.textContent = unavailableMessage;
            return;
        }

        cancelSearch();
        const request = { generation: generation, controller: new AbortController(), timer: null };
        activeRequest = request;
        setBusy(true);
        statusElement.textContent = "Đang tìm địa chỉ…";
        request.timer = window.setTimeout(function () {
            if (!isCurrent(request)) return;
            cancelSearch();
            statusElement.textContent = "Tìm địa chỉ quá thời gian. Vui lòng thử lại hoặc chọn ghim trên bản đồ.";
        }, deadline);
        panel.dispatchEvent(new CustomEvent("rescue:address-search-start", { bubbles: true }));
        if (!isCurrent(request)) return;

        try {
            const response = await fetch(url, {
                method: "POST",
                headers: { "Accept": "application/json", "X-CSRFToken": panel.dataset.csrfToken },
                body: new URLSearchParams({ address: address }),
                credentials: "same-origin",
                cache: "no-store",
                redirect: "error",
                signal: request.controller.signal,
            });
            if (!isCurrent(request)) return;
            if (!response.ok) {
                statusElement.textContent = responseError(response.status);
                return;
            }
            if (response.redirected || !/^application\/json\b/i.test(response.headers.get("content-type") || "")) {
                throw new Error("Invalid response");
            }
            const payload = await response.json();
            if (!isCurrent(request)) return;
            if (!validResults(payload)) throw new Error("Invalid results");
            renderResults(payload.results, request.generation);
        } catch (_) {
            if (isCurrent(request)) statusElement.textContent = failureMessage;
        } finally {
            finish(request);
        }
    }

    searchButton.type = "button";
    searchButton.addEventListener("click", search);
    addressInput.addEventListener("input", cancelSearch);
    panel.addEventListener("rescue:cancel-address-search", cancelSearch);
    window.addEventListener("pagehide", cancelSearch);
    document.addEventListener("visibilitychange", function () {
        if (document.hidden || document.visibilityState === "hidden") cancelSearch();
    });
    setBusy(false);
}());
