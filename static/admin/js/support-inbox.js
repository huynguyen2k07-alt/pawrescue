(() => {
    const root = document.querySelector("[data-support-inbox]");
    if (!root) return;

    const conversationList = root.querySelector("[data-conversation-list]");
    const conversationCount = root.querySelector("[data-conversation-count]");
    const messageList = root.querySelector("[data-thread-messages]");
    const threadStatus = root.querySelector("[data-thread-status]");
    const replyForm = root.querySelector("[data-admin-reply-form]");
    const selectedId = Number(root.dataset.selectedId || 0);
    let isLoading = false;
    let messageSignature = "";

    function createEmptyList() {
        const wrapper = document.createElement("div");
        wrapper.className = "support-inbox-empty";
        const icon = document.createElement("span");
        icon.textContent = "✓";
        const copy = document.createElement("p");
        copy.textContent = "Chưa có cuộc trò chuyện nào.";
        wrapper.append(icon, copy);
        return wrapper;
    }

    function createConversation(item) {
        const link = document.createElement("a");
        link.href = item.url;
        link.classList.toggle("is-active", item.id === selectedId);

        const avatar = document.createElement("span");
        avatar.className = "support-conversation-avatar";
        avatar.textContent = item.avatar;

        const copy = document.createElement("span");
        const name = document.createElement("strong");
        name.textContent = item.name;
        const detail = document.createElement("small");
        detail.textContent = `${item.status_label} · ${item.last_message_at}`;
        copy.append(name, detail);
        link.append(avatar, copy);

        if (item.unread_count) {
            const unread = document.createElement("em");
            unread.textContent = item.unread_count;
            link.appendChild(unread);
        }
        return link;
    }

    function renderConversations(items) {
        const previousScroll = conversationList.scrollTop;
        const fragment = document.createDocumentFragment();
        if (!items.length) fragment.appendChild(createEmptyList());
        else items.forEach((item) => fragment.appendChild(createConversation(item)));
        conversationList.replaceChildren(fragment);
        conversationList.scrollTop = previousScroll;
        conversationCount.textContent = items.length;
    }

    function createAttachment(item) {
        if (item.media_type === "image") {
            const link = document.createElement("a");
            link.className = "support-thread-attachment support-thread-attachment-image";
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
        wrapper.className = "support-thread-attachment support-thread-attachment-video";
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
        article.className = `support-thread-message support-thread-message-${item.is_admin ? "admin" : "user"}`;
        const sender = document.createElement("span");
        sender.textContent = item.sender_name;
        article.appendChild(sender);
        if (item.body) {
            const body = document.createElement("p");
            body.textContent = item.body;
            article.appendChild(body);
        }
        if (item.attachments?.length) {
            const attachments = document.createElement("div");
            attachments.className = "support-thread-attachments";
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
        if (!messageList) return;
        const nextSignature = items.map((item) => item.id).join(",");
        if (nextSignature === messageSignature) return;
        messageSignature = nextSignature;
        const fragment = document.createDocumentFragment();
        items.forEach((item) => fragment.appendChild(createMessage(item)));
        messageList.replaceChildren(fragment);
        messageList.scrollTop = messageList.scrollHeight;
    }

    function updateStatus(selected) {
        if (!threadStatus || !selected) return;
        threadStatus.textContent = selected.status_label;
        [...threadStatus.classList]
            .filter((name) => name.startsWith("support-thread-status-") && name !== "support-thread-status")
            .forEach((name) => threadStatus.classList.remove(name));
        threadStatus.classList.add(`support-thread-status-${selected.status}`);
    }

    async function refreshInbox() {
        if (isLoading || document.hidden) return;
        isLoading = true;
        try {
            const stateUrl = new URL(root.dataset.stateUrl, window.location.origin);
            if (selectedId) stateUrl.searchParams.set("conversation", selectedId);
            const response = await fetch(stateUrl, {
                headers: { Accept: "application/json" },
                credentials: "same-origin",
            });
            if (!response.ok) throw new Error("Không thể đồng bộ hộp thư.");
            const data = await response.json();
            if (!selectedId && data.conversations.length) {
                window.location.assign(data.conversations[0].url);
                return;
            }
            renderConversations(data.conversations);
            if (data.selected && data.selected.id === selectedId) {
                renderMessages(data.selected.messages);
                updateStatus(data.selected);
            }
        } catch (error) {
            console.warn(error.message);
        } finally {
            isLoading = false;
        }
    }

    if (replyForm) {
        const textarea = replyForm.querySelector("textarea");
        const fileInput = replyForm.querySelector("[data-admin-file-input]");
        const preview = replyForm.querySelector("[data-admin-attachment-preview]");
        let previewUrls = [];

        function clearPreview() {
            previewUrls.forEach((url) => URL.revokeObjectURL(url));
            previewUrls = [];
            preview.replaceChildren();
            preview.hidden = true;
        }

        fileInput.addEventListener("change", () => {
            clearPreview();
            const files = Array.from(fileInput.files || []);
            files.forEach((file) => {
                const item = document.createElement("div");
                item.className = "support-admin-preview-item";
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
                const name = document.createElement("span");
                name.textContent = file.name;
                item.appendChild(name);
                preview.appendChild(item);
            });
            preview.hidden = !files.length;
        });

        textarea.addEventListener("keydown", (event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
                event.preventDefault();
                if (textarea.value.trim() || fileInput.files.length) {
                    replyForm.requestSubmit();
                }
            }
        });
    }

    document.addEventListener("visibilitychange", () => {
        if (!document.hidden) refreshInbox();
    });
    refreshInbox();
    window.setInterval(refreshInbox, 3000);
})();
