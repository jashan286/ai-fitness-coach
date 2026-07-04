// AI Fitness Coach - client-side interactivity

document.addEventListener("DOMContentLoaded", () => {
    const chatForm = document.getElementById("chat-form");
    const chatInput = document.getElementById("chat-input");
    const chatWindow = document.getElementById("chat-window");

    if (!chatForm) return; // Not on the chatbot page

    function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

function formatBotMessage(text) {
    const escaped = escapeHtml(text);
    const lines = escaped.split(/\r?\n/);

    let html = "";
    let inList = false;

    for (let rawLine of lines) {
        const line = rawLine.trim();
        const isBullet = /^[-*]\s+/.test(line);

        if (isBullet) {
            if (!inList) {
                html += "<ul>";
                inList = true;
            }
            const content = line.replace(/^[-*]\s+/, "");
            html += `<li>${boldify(content)}</li>`;
        } else {
            if (inList) {
                html += "</ul>";
                inList = false;
            }
            if (line) {
                html += `<p>${boldify(line)}</p>`;
            }
        }
    }
    if (inList) html += "</ul>";

    return html;
}

function boldify(str) {
    return str.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

function appendMessage(text, sender) {
    const messageDiv = document.createElement("div");
    messageDiv.classList.add("chat-message", sender);

    const avatar = document.createElement("span");
    avatar.classList.add("chat-avatar");
    avatar.innerHTML = sender === "user"
        ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/></svg>'
        : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-8.5 8.5 8.5 8.5 0 0 1-4-1L3 20l1-5.5A8.38 8.38 0 0 1 3.5 11 8.5 8.5 0 0 1 12 3a8.38 8.38 0 0 1 9 8.5Z"/></svg>';

    const bubble = document.createElement("span");
    bubble.classList.add("bubble");
    if (sender === "bot") {
        bubble.innerHTML = formatBotMessage(text);
    } else {
        bubble.textContent = text;
    }

    messageDiv.appendChild(avatar);
    messageDiv.appendChild(bubble);
    chatWindow.appendChild(messageDiv);
    chatWindow.scrollTop = chatWindow.scrollHeight;
    return messageDiv;
}

    function showTypingIndicator() {
        const messageDiv = document.createElement("div");
        messageDiv.classList.add("chat-message", "bot", "typing-indicator");
        messageDiv.id = "typing-indicator";

        const avatar = document.createElement("span");
        avatar.classList.add("chat-avatar");
        avatar.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-8.5 8.5 8.5 8.5 0 0 1-4-1L3 20l1-5.5A8.38 8.38 0 0 1 3.5 11 8.5 8.5 0 0 1 12 3a8.38 8.38 0 0 1 9 8.5Z"/></svg>';

        const bubble = document.createElement("span");
        bubble.classList.add("bubble");
        bubble.innerHTML = '<span class="dot"></span><span class="dot"></span><span class="dot"></span>';

        messageDiv.appendChild(avatar);
        messageDiv.appendChild(bubble);
        chatWindow.appendChild(messageDiv);
        chatWindow.scrollTop = chatWindow.scrollHeight;
    }

    function removeTypingIndicator() {
        const indicator = document.getElementById("typing-indicator");
        if (indicator) indicator.remove();
    }

    chatForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const message = chatInput.value.trim();
        if (!message) return;

        appendMessage(message, "user");
        chatInput.value = "";
        chatInput.disabled = true;

        showTypingIndicator();

        try {
            const response = await fetch("/api/chatbot", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message }),
            });
            const data = await response.json();
            removeTypingIndicator();
            appendMessage(data.reply, "bot");
        } catch (err) {
            removeTypingIndicator();
            appendMessage("Sorry, something went wrong. Please try again.", "bot");
        } finally {
            chatInput.disabled = false;
            chatInput.focus();
        }
    });
});
