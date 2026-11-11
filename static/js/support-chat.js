(() => {
    const root = document.getElementById("support-chat");
    if (!root) return;

    const toggle = document.getElementById("support-chat-toggle");
    const panel = document.getElementById("support-chat-panel");
    const closeButton = root.querySelector("[data-support-close]");
    const messagesContainer = root.querySelector("[data-support-messages]");
    const form = root.querySelector("[data-support-form]");
    const textarea = form.querySelector("textarea");
    const fileInput = form.querySelector("[data-support-file-input]");
    const attachmentPreview = form.querySelector("[data-support-attachment-preview]");
    const submitButton = form.querySelector("button[type='submit']");
    const feedback = root.querySelector("[data-support-feedback]");
    const status = root.querySelector("[data-support-status]");
    const badge = root.querySelector("[data-support-badge]");
    const title = document.getElementById("support-chat-title");
    const toggleTitle = root.querySelector("[data-support-toggle-title]");
    const toggleCopy = root.querySelector("[data-support-toggle-copy]");
    const modeTools = root.querySelector("[data-support-mode-tools]");
    const defaultButton = root.querySelector("[data-support-default]");
    const fullPageLink = root.querySelector("[data-support-full-page]");
    const caseTitle = root.querySelector("[data-support-case-title]");
    const recipientControl = root.querySelector("[data-case-chat-recipient]");
    const recipientSelect = root.querySelector("[data-case-chat-recipient-select]");
    const attachButton = root.querySelector("[data-support-attach-button]");
    const privacy = root.querySelector("[data-support-privacy]");
    const isOperator = root.dataset.supportOperator === "true";
    const defaultMode = isOperator ? "operator" : "support";
    let mode = defaultMode;
    let caseUrl = "";
    let caseId = "";
    let contextVersion = 0;
    let loadingVersion = null;
    let isSending = false;
    let canSend = !isOperator;
    let allowedRecipients = new Set();
    let messageSignature = "";
    let previewUrls = [];

    function showFeedback(message, isError = false) {
        feedback.textContent = message;
        feedback.classList.toggle("is-error", isError);
        feedback.hidden = !message;
    }

    function formatFileSize(size) {
        if (size < 1024 * 1024) return `${Math.max(1, Math.round(size / 1024))} KB`;
        return `${(size / (1024 * 1024)).toFixed(1)} MB`;
    }

    function createEmptyState() {
        const wrapper = document.createElement("div");
        wrapper.className = "support-chat-empty";
        const icon = document.createElement("span");
        icon.textContent = "👋";
        const title = document.createElement("strong");
        title.textContent = mode === "case" ? "Trao đổi riêng về ca cứu hộ" : mode === "operator" ? "Hộp thư và điều phối cứu hộ" : "PawRescue có thể giúp gì cho bạn?";
        const copy = document.createElement("p");
        copy.textContent = mode === "case" ? "Tin nhắn chỉ dành cho admin chính và cộng tác viên được giao ca." : mode === "operator" ? "Mở một ca để nhắn riêng cho cộng tác viên, hoặc vào hộp thư hỗ trợ người dùng." : "Bạn có thể gửi câu hỏi, ảnh hoặc video để admin chính hỗ trợ chính xác hơn.";
        wrapper.append(icon, title, copy);
        return wrapper;
    }

    function createAttachment(item) {
        if (item.media_type === "image") {
            const link = document.createElement("a");
            link.className = "support-message-attachment support-message-attachment-image";
            link.href = item.url;
            link.target = "_blank";
            link.rel = "noopener";
            const image = document.createElement("img");
            image.src = item.url;
            image.alt = item.name;
            image.loading = "lazy";
            link.appendChild(image);
            return link;
        }

        const wrapper = document.createElement("div");
        wrapper.className = "support-message-attachment support-message-attachment-video";
        const video = document.createElement("video");
        video.controls = true;
        video.preload = "metadata";
        video.playsInline = true;
        video.setAttribute("aria-label", item.name);
        const source = document.createElement("source");
        source.src = item.url;
        source.type = item.content_type;
        video.appendChild(source);
        const name = document.createElement("small");
        name.textContent = item.name;
        wrapper.append(video, name);
        return wrapper;
    }

    function createMessage(item) {
        const article = document.createElement("article");
        const incoming = mode === "case" ? !item.is_own : item.is_admin;
        article.className = `support-message ${incoming ? "support-message-admin" : "support-message-user"}`;
        const meta = document.createElement("span");
        meta.textContent = mode === "case" && item.recipient_name ? `${item.sender_name} → ${item.recipient_name}` : item.sender_name;
        article.appendChild(meta);

        if (item.body) {
            const body = document.createElement("p");
            body.textContent = item.body;
            article.appendChild(body);
        }

        if (mode === "support" && item.attachments?.length) {
            const attachments = document.createElement("div");
            attachments.className = "support-message-attachments";
            item.attachments.forEach((attachment) => {
                attachments.appendChild(createAttachment(attachment));
            });
            article.appendChild(attachments);
        }

        const time = document.createElement("time");
        if (mode === "case") {
            const date = new Date(item.created_at);
            time.textContent = Number.isNaN(date.getTime()) ? "" : date.toLocaleString("vi-VN");
            if (item.is_own && item.read_at) time.textContent += " · Đã đọc";
        } else {
            time.textContent = item.created_at;
        }
        article.appendChild(time);
        return article;
    }

    // So sánh cả nội dung và tệp để nhận ra sửa tin nhắn dù mã tin nhắn không đổi.
    function renderMessages(items) {
        const nextSignature = JSON.stringify(items);
        if (nextSignature === messageSignature) return;
        messageSignature = nextSignature;
        messagesContainer.replaceChildren();
        if (!items.length) {
            messagesContainer.appendChild(createEmptyState());
        } else {
            const fragment = document.createDocumentFragment();
            items.forEach((item) => fragment.appendChild(createMessage(item)));
            messagesContainer.appendChild(fragment);
        }
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    function clearAttachmentPreview() {
        previewUrls.forEach((url) => URL.revokeObjectURL(url));
        previewUrls = [];
        attachmentPreview.replaceChildren();
        attachmentPreview.hidden = true;
    }

    function resetFileInput(message) {
        fileInput.value = "";
        clearAttachmentPreview();
        if (message) showFeedback(message, true);
    }

    function renderAttachmentPreview() {
        clearAttachmentPreview();
        const files = Array.from(fileInput.files || []);
        if (!files.length) return;
        if (files.length > 4) {
            resetFileInput("Mỗi tin nhắn chỉ được gửi tối đa 4 tệp.");
            return;
        }

        let totalSize = 0;
        for (const file of files) {
            const isVideo = file.type.startsWith("video/");
            const maximumSize = isVideo ? 40 * 1024 * 1024 : 8 * 1024 * 1024;
            if ((!file.type.startsWith("image/") && !isVideo) || file.size > maximumSize) {
                const limit = isVideo ? "40 MB" : "8 MB";
                resetFileInput(`Tệp ${file.name} không hợp lệ hoặc vượt quá ${limit}.`);
                return;
            }
            totalSize += file.size;
        }
        if (totalSize > 50 * 1024 * 1024) {
            resetFileInput("Tổng dung lượng tệp phải nhỏ hơn 50 MB.");
            return;
        }

        files.forEach((file) => {
            const item = document.createElement("div");
            item.className = "support-compose-attachment";
            const objectUrl = URL.createObjectURL(file);
            previewUrls.push(objectUrl);
            if (file.type.startsWith("image/")) {
                const image = document.createElement("img");
                image.src = objectUrl;
                image.alt = "";
                item.appendChild(image);
            } else {
                const video = document.createElement("video");
                video.src = objectUrl;
                video.muted = true;
                video.preload = "metadata";
                item.appendChild(video);
            }
            const copy = document.createElement("span");
            const name = document.createElement("strong");
            name.textContent = file.name;
            const size = document.createElement("small");
            size.textContent = formatFileSize(file.size);
            copy.append(name, size);
            item.appendChild(copy);
            attachmentPreview.appendChild(item);
        });
        attachmentPreview.hidden = false;
        showFeedback("");
    }

    function updateComposer() {
        const enabled = canSend && !isSending;
        textarea.disabled = !enabled;
        submitButton.disabled = !enabled || (mode === "case" && !allowedRecipients.has(recipientSelect.value));
        fileInput.disabled = !enabled || mode !== "support";
        recipientSelect.disabled = !enabled || mode !== "case";
    }

    function clearPrivateContent() {
        messageSignature = "";
        messagesContainer.replaceChildren();
        caseTitle.textContent = "";
        textarea.value = "";
        resetFileInput();
        recipientSelect.replaceChildren();
        recipientSelect.value = "";
        allowedRecipients = new Set();
        canSend = false;
        updateComposer();
    }

    function invalidateConversation() {
        contextVersion += 1;
        isSending = false;
        clearPrivateContent();
        badge.hidden = true;
    }

    // Mỗi ca có ngữ cảnh riêng: bỏ kết quả tải cũ và xóa bản nháp khi đổi cuộc trò chuyện.
    function changeMode(nextMode, endpoint = null, label = "") {
        contextVersion += 1;
        mode = nextMode;
        caseUrl = endpoint?.href || "";
        caseId = endpoint?.pathname.match(/^\/cases\/(\d+)\/messages\/$/)?.[1] || "";
        root.classList.toggle("is-case-chat", mode === "case");
        isSending = false;
        clearPrivateContent();
        canSend = mode === "support";
        form.hidden = mode === "operator";
        recipientControl.hidden = mode !== "case";
        attachButton.hidden = mode !== "support";
        modeTools.hidden = mode === "support";
        defaultButton.hidden = mode !== "case";
        caseTitle.hidden = mode !== "case";
        fullPageLink.href = mode === "case" ? caseUrl : root.dataset.supportInboxUrl || "";
        fullPageLink.textContent = mode === "case" ? "Mở trang trao đổi ↗" : "Mở hộp thư hỗ trợ ↗";
        title.textContent = mode === "case" ? label || `Ca #${caseId}` : mode === "operator" ? "Hộp thư PawRescue" : "Hỗ trợ PawRescue";
        toggleTitle.textContent = mode === "case" ? `Trao đổi ca #${caseId}` : isOperator ? "Hộp thư PawRescue" : "Chat với PawRescue";
        toggleCopy.textContent = mode === "case" ? "Admin chính và cộng tác viên" : isOperator ? "Người dùng và cộng tác viên" : "Admin chính hỗ trợ";
        status.textContent = mode === "case" ? "Đang tải trao đổi riêng..." : mode === "operator" ? "Chọn hộp thư hoặc một ca cứu hộ" : "Sẵn sàng hỗ trợ";
        textarea.placeholder = mode === "case" ? "Nhập tin nhắn riêng về ca cứu hộ..." : "Nhập tin nhắn hoặc gửi ảnh/video...";
        privacy.textContent = mode === "case" ? "Trao đổi riêng giữa admin chính và cộng tác viên được giao ca. Người dùng khác không xem được." : "Tối đa 4 tệp · Ảnh 8 MB · Video 40 MB · Chỉ đội hỗ trợ có quyền mới xem.";
        badge.hidden = true;
        showFeedback("");
        renderMessages([]);
        updateComposer();
    }

    function applyCaseState(data) {
        if (String(data.case_id) !== caseId || !Array.isArray(data.messages) || !Array.isArray(data.recipients)) {
            throw new Error("Không thể xác nhận cuộc trò chuyện này. Hãy mở lại ca cứu hộ.");
        }
        const previousRecipient = recipientSelect.value;
        const recipients = data.recipients.filter((item) => Number.isInteger(item.id) && typeof item.name === "string");
        allowedRecipients = new Set(recipients.map((item) => String(item.id)));
        recipientSelect.replaceChildren();
        const placeholder = document.createElement("option");
        placeholder.value = "";
        placeholder.textContent = recipients.length ? "Chọn người nhận" : "Chưa có người nhận được phân công";
        recipientSelect.appendChild(placeholder);
        recipients.forEach((item) => {
            const option = document.createElement("option");
            option.value = String(item.id);
            option.textContent = item.name;
            recipientSelect.appendChild(option);
        });
        recipientSelect.value = allowedRecipients.has(previousRecipient) ? previousRecipient : recipients.length === 1 ? String(recipients[0].id) : "";
        canSend = recipients.length > 0;
        status.textContent = "Trao đổi riêng: admin chính và cộng tác viên";
        caseTitle.textContent = data.title || `Ca #${caseId}`;
        renderMessages(data.messages);
        showFeedback(canSend ? "" : "Ca chưa có cộng tác viên đang phụ trách. Admin chính cần giao ca trước khi nhắn tin.");
        updateComposer();
    }

    async function loadMessages() {
        // Không tải chat riêng khi đóng, tránh đánh dấu đã đọc tin nhắn chưa xem.
        if (mode === "operator" || (mode === "case" && panel.hidden) || document.hidden) return;
        const requestVersion = contextVersion;
        if (loadingVersion === requestVersion) return;
        loadingVersion = requestVersion;
        const markRead = !panel.hidden;
        try {
            const stateUrl = new URL(mode === "case" ? caseUrl : root.dataset.stateUrl, window.location.origin);
            if (markRead && mode === "support") stateUrl.searchParams.set("mark_read", "1");
            const response = await fetch(stateUrl, {
                headers: { Accept: "application/json" },
                credentials: "same-origin",
                cache: "no-store",
            });
            if (requestVersion !== contextVersion) return;
            if (!response.ok || response.redirected) throw new Error("Không thể mở cuộc trò chuyện hoặc quyền truy cập đã thay đổi.");
            const data = await response.json();
            if (requestVersion !== contextVersion) return;
            if (mode === "case") {
                applyCaseState(data);
                return;
            }
            if (!Array.isArray(data.messages)) throw new Error("Không thể tải cuộc trò chuyện. Hãy đăng nhập lại.");
            status.textContent = data.status_label;
            canSend = true;
            updateComposer();
            if (!panel.hidden) {
                renderMessages(data.messages);
                badge.hidden = true;
                showFeedback("");
            } else {
                badge.textContent = data.unread_count;
                badge.hidden = data.unread_count === 0;
            }
        } catch (error) {
            if (requestVersion !== contextVersion) return;
            invalidateConversation();
            status.textContent = "Cuộc trò chuyện chưa khả dụng";
            if (!panel.hidden) showFeedback(error.message, true);
        } finally {
            if (loadingVersion === requestVersion) loadingVersion = null;
        }
    }

    function openChat() {
        panel.hidden = false;
        toggle.setAttribute("aria-expanded", "true");
        toggle.setAttribute("aria-label", "Đóng cửa sổ chat hỗ trợ PawRescue");
        root.classList.add("is-open");
        loadMessages();
        textarea.focus();
    }

    function closeChat() {
        panel.hidden = true;
        toggle.setAttribute("aria-expanded", "false");
        toggle.setAttribute("aria-label", "Mở cửa sổ chat hỗ trợ PawRescue");
        root.classList.remove("is-open");
        if (mode === "case") {
            invalidateConversation();
        }
        toggle.focus();
    }

    toggle.addEventListener("click", () => {
        if (panel.hidden) openChat();
        else closeChat();
    });
    closeButton.addEventListener("click", closeChat);
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && !panel.hidden) closeChat();
    });
    textarea.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
            event.preventDefault();
            form.requestSubmit();
        }
    });
    fileInput.addEventListener("change", renderAttachmentPreview);
    recipientSelect.addEventListener("change", updateComposer);
    defaultButton.addEventListener("click", () => {
        changeMode(defaultMode);
        openChat();
    });
    // ===== CHỨC NĂNG CHÍNH: CHAT RIÊNG ADMIN VÀ CỘNG TÁC VIÊN =====
    // Mở trao đổi đúng ca trong khung chung; chuột giữa hoặc Ctrl vẫn mở liên kết ở tab mới.
    document.addEventListener("click", (event) => {
        if (event.defaultPrevented || (event.button !== undefined && event.button !== 0) || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        const link = event.target.closest?.("[data-case-chat-url]");
        if (!link) return;
        let endpoint;
        try {
            endpoint = new URL(link.dataset.caseChatUrl, window.location.origin);
        } catch (_) {
            return;
        }
        if (endpoint.origin !== window.location.origin || !/^\/cases\/[1-9]\d*\/messages\/$/.test(endpoint.pathname)) return;
        event.preventDefault();
        if (mode !== "case" || caseUrl !== endpoint.href) changeMode("case", endpoint, link.dataset.caseChatTitle);
        openChat();
    });

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        if (!canSend || isSending || mode === "operator") return;
        const body = textarea.value.trim();
        if (!body && (mode === "case" || !fileInput.files.length)) {
            showFeedback(mode === "case" ? "Hãy nhập nội dung tin nhắn." : "Hãy nhập nội dung hoặc chọn ảnh/video.", true);
            return;
        }
        if (mode === "case" && !allowedRecipients.has(recipientSelect.value)) {
            showFeedback("Hãy chọn người nhận đang phụ trách ca.", true);
            return;
        }

        const requestVersion = contextVersion;
        const formData = new FormData(form);
        formData.set("body", body);
        if (mode === "case") {
            formData.delete("attachments");
            formData.set("recipient", recipientSelect.value);
        }
        isSending = true;
        updateComposer();
        showFeedback("Đang gửi...");
        let responseStatus;
        try {
            const response = await fetch(mode === "case" ? caseUrl : root.dataset.sendUrl, {
                method: "POST",
                body: formData,
                headers: { Accept: "application/json" },
                credentials: "same-origin",
                cache: "no-store",
            });
            if (requestVersion !== contextVersion) return;
            responseStatus = response.status;
            if (response.redirected || [401, 403, 404].includes(response.status)) {
                throw new Error("Quyền truy cập cuộc trò chuyện đã thay đổi. Hãy mở lại ca hoặc đăng nhập lại.");
            }
            const data = await response.json();
            if (requestVersion !== contextVersion) return;
            if (!response.ok) throw new Error(data.error || "Không thể gửi tin nhắn.");
            textarea.value = "";
            fileInput.value = "";
            clearAttachmentPreview();
            showFeedback("");
            if (mode === "case") applyCaseState(data);
            else {
                status.textContent = data.status_label;
                await loadMessages();
            }
        } catch (error) {
            if (requestVersion !== contextVersion) return;
            if (responseStatus !== 400) invalidateConversation();
            showFeedback(error.message, true);
        } finally {
            if (requestVersion === contextVersion) {
                isSending = false;
                updateComposer();
                if (canSend) textarea.focus();
            }
        }
    });

    changeMode(defaultMode);
    loadMessages();
    window.setInterval(loadMessages, 3000);
})();
