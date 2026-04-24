// PesoBot Frontend · vanilla JS
// Maneja chat, upload de PDFs y panel de debug

const API_BASE = "/api";
let conversationHistory = [];

// ============================================================================
// Inicialización
// ============================================================================
document.addEventListener("DOMContentLoaded", async () => {
    await checkHealth();
    loadDocuments();
    loadTransferLog();

    // Auto-resize del textarea
    const input = document.getElementById("messageInput");
    input.addEventListener("input", () => {
        input.style.height = "auto";
        input.style.height = Math.min(input.scrollHeight, 150) + "px";
    });
});

// ============================================================================
// Healthcheck
// ============================================================================
async function checkHealth() {
    const badge = document.getElementById("statusBadge");
    try {
        const res = await fetch(`${API_BASE}/health`);
        if (res.ok) {
            const data = await res.json();
            badge.classList.remove("offline");
            badge.innerHTML = `<span class="status-dot"></span> Online · ${data.llm_provider}`;
        } else {
            throw new Error("offline");
        }
    } catch (e) {
        badge.classList.add("offline");
        badge.innerHTML = `<span class="status-dot"></span> Offline`;
    }
}

// ============================================================================
// Chat
// ============================================================================
function handleKeydown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
}

async function sendMessage() {
    const input = document.getElementById("messageInput");
    const message = input.value.trim();
    if (!message) return;

    // UI: agregar mensaje del usuario
    addMessage("user", message);
    input.value = "";
    input.style.height = "auto";

    // UI: indicador de "escribiendo"
    const sendBtn = document.getElementById("sendBtn");
    sendBtn.disabled = true;
    const typingId = addTypingIndicator();

    try {
        const res = await fetch(`${API_BASE}/chat`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                message: message,
                conversation_history: conversationHistory,
            }),
        });

        if (!res.ok) {
            const err = await res.text();
            throw new Error(`Error ${res.status}: ${err}`);
        }

        const data = await res.json();

        // Quitar typing
        document.getElementById(typingId)?.remove();

        // Mostrar tools ejecutadas (si hubo)
        if (data.tools_executed && data.tools_executed.length > 0) {
            showToolsExecuted(data.tools_executed);
        }

        // Mostrar respuesta del bot
        addMessage("assistant", data.response);

        // Actualizar historial
        conversationHistory.push({ role: "user", content: message });
        conversationHistory.push({ role: "assistant", content: data.response });

        // Refrescar panel debug si hubo tool calls
        if (data.tools_executed?.length > 0) {
            loadTransferLog();
            loadDocuments();
        }
    } catch (e) {
        document.getElementById(typingId)?.remove();
        addMessage("assistant", `❌ Error: ${e.message}`);
    } finally {
        sendBtn.disabled = false;
        input.focus();
    }
}

function addMessage(role, content) {
    const messages = document.getElementById("messages");
    const div = document.createElement("div");
    div.className = `message ${role}`;

    const avatar = document.createElement("div");
    avatar.className = "message-avatar";
    avatar.textContent = role === "user" ? "TÚ" : "$";

    const bubble = document.createElement("div");
    bubble.className = "message-bubble";
    bubble.innerHTML = formatMessage(content);

    div.appendChild(avatar);
    div.appendChild(bubble);
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
}

function addTypingIndicator() {
    const id = `typing-${Date.now()}`;
    const messages = document.getElementById("messages");
    const div = document.createElement("div");
    div.id = id;
    div.className = "message assistant";
    div.innerHTML = `
        <div class="message-avatar">$</div>
        <div class="message-bubble">
            <div class="typing"><span></span><span></span><span></span></div>
        </div>
    `;
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
    return id;
}

function formatMessage(text) {
    // Escape HTML básico
    let html = text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");

    // Code blocks ```
    html = html.replace(/```([\s\S]*?)```/g, "<pre><code>$1</code></pre>");
    // Inline code
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
    // Bold
    html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    // Italic
    html = html.replace(/\*([^*]+)\*/g, "<em>$1</em>");
    // Line breaks
    html = html.split("\n\n").map(p => `<p>${p.replace(/\n/g, "<br>")}</p>`).join("");

    return html;
}

function showToolsExecuted(tools) {
    const indicator = document.getElementById("toolsIndicator");
    const names = tools.map(t => t.name).join(", ");
    indicator.innerHTML = `⚡ <strong>Tools ejecutadas:</strong> ${names} (sin confirmación humana)`;
    indicator.classList.remove("hidden");

    setTimeout(() => indicator.classList.add("hidden"), 8000);
}

// ============================================================================
// Upload de PDF (queja → RAG poisoning)
// ============================================================================
async function uploadPDF(event) {
    const file = event.target.files[0];
    if (!file) return;

    const complainantName = prompt("¿Quién presenta la queja? (nombre):", "anonimo") || "anonimo";

    const formData = new FormData();
    formData.append("file", file);

    addMessage("user", `📎 Subiendo PDF: ${file.name} (queja de ${complainantName})`);

    try {
        const res = await fetch(`${API_BASE}/upload-complaint?complainant_name=${encodeURIComponent(complainantName)}`, {
            method: "POST",
            body: formData,
        });

        const data = await res.json();

        if (data.ingest_result?.success) {
            addMessage("assistant", `✅ Queja registrada exitosamente. Se agregaron ${data.ingest_result.chunks_added} fragmentos al sistema. Tu queja será procesada en máximo 5 días hábiles.`);
            loadDocuments();
        } else {
            addMessage("assistant", `❌ Error procesando queja: ${data.ingest_result?.error || "desconocido"}`);
        }
    } catch (e) {
        addMessage("assistant", `❌ Error subiendo PDF: ${e.message}`);
    }

    event.target.value = ""; // reset input
}

// ============================================================================
// Reset del lab
// ============================================================================
async function resetLab() {
    if (!confirm("¿Resetear el lab para una nueva demo? Se borrarán PDFs subidos y log de transferencias.")) return;

    try {
        const res = await fetch(`${API_BASE}/reset`, { method: "POST" });
        const data = await res.json();

        // Limpiar UI
        document.getElementById("messages").innerHTML = `
            <div class="message assistant">
                <div class="message-avatar">$</div>
                <div class="message-bubble">
                    <p>✨ Lab reseteado. ¿En qué puedo ayudarte?</p>
                </div>
            </div>
        `;
        conversationHistory = [];
        loadTransferLog();
        loadDocuments();

        alert("Lab reseteado correctamente.");
    } catch (e) {
        alert(`Error reseteando: ${e.message}`);
    }
}

// ============================================================================
// Panel debug · transferencias
// ============================================================================
async function loadTransferLog() {
    const container = document.getElementById("transferLog");
    try {
        const res = await fetch(`${API_BASE}/transfer-log`);
        const data = await res.json();

        if (data.total_transfers === 0) {
            container.innerHTML = "<em>Aún no hay transferencias</em>";
            return;
        }

        container.innerHTML = data.transfers.map(t => `
            <div class="debug-item">
                <div class="item-title">${t.amount} ${t.currency}</div>
                <div class="item-meta">${t.from_account} → ${t.to_account}</div>
                <div class="item-meta">${new Date(t.timestamp).toLocaleTimeString()} · ${t.id}</div>
            </div>
        `).join("");
    } catch (e) {
        container.innerHTML = `<em>Error cargando: ${e.message}</em>`;
    }
}

// ============================================================================
// Panel debug · documentos en RAG
// ============================================================================
async function loadDocuments() {
    const container = document.getElementById("documentsList");
    try {
        const res = await fetch(`${API_BASE}/documents`);
        const data = await res.json();

        if (data.total === 0) {
            container.innerHTML = "<em>Sin documentos</em>";
            return;
        }

        container.innerHTML = data.documents.map(d => `
            <div class="debug-item ${d.trusted ? '' : 'untrusted'}">
                <div class="item-title">${d.title}</div>
                <div class="item-meta">${d.source} · ${d.trusted ? '✓ confiable' : '✗ no confiable'}</div>
            </div>
        `).join("");
    } catch (e) {
        container.innerHTML = `<em>Error cargando: ${e.message}</em>`;
    }
}

function toggleDebug() {
    const content = document.getElementById("debugContent");
    const btn = document.querySelector(".btn-toggle");
    if (content.style.display === "none") {
        content.style.display = "block";
        btn.textContent = "−";
    } else {
        content.style.display = "none";
        btn.textContent = "+";
    }
}
