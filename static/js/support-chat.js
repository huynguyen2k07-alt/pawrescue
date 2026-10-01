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
    let isLoading = false;
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
        title.textContent = "PawRescue có thể giúp gì cho bạn?";
        const copy = document.createElement("p");
        copy.textContent = "Bạn có thể gửi câu hỏi, ảnh hoặc video để quản trị viên hỗ trợ chính xác hơn.";
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
        article.className = `support-message ${item.is_admin ? "support-message-admin" : "support-message-user"}`;
        const meta = document.createElement("span");
        meta.textContent = item.sender_name;
        article.appendChild(meta);

        if (item.body) {
            const body = document.createElement("p");
            body.textContent = item.body;
            article.appendChild(body);
        }

        if (item.attachments?.length) {
            const attachments = document.createElement("div");
            attachments.className = "support-message-attachments";
            item.attachments.forEach((attachment) => {
                attachments.appendChild(createAttachment(attachment));
            });
            article.appendChild(attachments);
        }

        const time = document.createElement("time");
        time.textContent = item.created_at;
        article.appendChild(time);
        return article;
    }

    function renderMessages(items) {
        const nextSignature = items
            .map((item) => `${item.id}:${(item.attachments || []).map((file) => file.id).join("-")}`)
            .join(",");
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

    async function loadMessages() {
        if (isLoading) return;
        isLoading = true;
        const markRead = !panel.hidden;
        try {
            const stateUrl = new URL(root.dataset.stateUrl, window.location.origin);
            if (markRead) stateUrl.searchParams.set("mark_read", "1");
            const response = await fetch(stateUrl, {
                headers: { Accept: "application/json" },
                credentials: "same-origin",
            });
            if (!response.ok) throw new Error("Không thể tải cuộc trò chuyện.");
            const data = await response.json();
            status.textContent = data.status_label;
            if (!panel.hidden) {
                renderMessages(data.messages);
                badge.hidden = true;
                showFeedback("");
            } else {
                badge.textContent = data.unread_count;
                badge.hidden = data.unread_count === 0;
            }
        } catch (error) {
            if (!panel.hidden) showFeedback(error.message, true);
        } finally {
            isLoading = false;
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

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const body = textarea.value.trim();
        if (!body && !fileInput.files.length) {
            showFeedback("Hãy nhập nội dung hoặc chọn ảnh/video.", true);
            return;
        }

        const formData = new FormData(form);
        formData.set("body", body);
        submitButton.disabled = true;
        fileInput.disabled = true;
        showFeedback("Đang gửi...");
        try {
            const response = await fetch(root.dataset.sendUrl, {
                method: "POST",
                body: formData,
                headers: { Accept: "application/json" },
                credentials: "same-origin",
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || "Không thể gửi tin nhắn.");
            textarea.value = "";
            fileInput.value = "";
            clearAttachmentPreview();
            status.textContent = data.status_label;
            showFeedback("");
            await loadMessages();
        } catch (error) {
            showFeedback(error.message, true);
        } finally {
            submitButton.disabled = false;
            fileInput.disabled = false;
            textarea.focus();
        }
    });

    loadMessages();
    window.setInterval(loadMessages, 3000);
})();
