
const API_BASE =
    ["localhost", "127.0.0.1"].includes(window.location.hostname)
        ? "http://127.0.0.1:8000"
        : "";

const MAX_FILE_SIZE = 100 * 1024 * 1024;
const HISTORY_KEY = "sahl-compliance-decoder-history-v1";
const SAVE_KEY = "sahl-compliance-decoder-saved-v1";
const MAX_UNDO_STEPS = 50;

const $ = (id) => document.getElementById(id);
const uploadView = $("uploadView");
const processingView = $("processingView");
const resultsView = $("resultsView");
const dropZone = $("dropZone");
const fileInput = $("fileInput");
const selectedFile = $("selectedFile");
const companyInput = $("companyInput");
const emailInput = $("emailInput");
const decodeButton = $("decodeButton");
const processingFile = $("processingFile");
const processingText = $("processingText");
const processingStage = $("processingStage");
const progressPercent = $("progressPercent");
const progressBar = $("progressBar");
const toast = $("toast");
const resultsRoot = $("resultsRoot");

let selectedPdf = null;
let progressTimer = null;
let currentProgress = 8;
let latestDecodeResult = null;
let isEditing = false;
let undoStack = [];
let redoStack = [];
let isDirty = false;
let historyItems = safeRead(HISTORY_KEY, []);

const processingStages = [
    {
        max: 20,
        title: "Reading PDF",
        text: "Extracting selectable text and tables from the document.",
        step: 1
    },
    {
        max: 42,
        title: "Understanding document structure",
        text: "Detecting the hierarchy and terminology used by this document.",
        step: 2
    },
    {
        max: 67,
        title: "Identifying requirements",
        text: "Identifying requirements grounded in the uploaded source.",
        step: 3
    },
    {
        max: 84,
        title: "Building implementation guidance",
        text: "Preparing actions, policies, documents, evidence and applicable tests.",
        step: 4
    },
    {
        max: 94,
        title: "Preparing output",
        text: "Preparing the decoded workspace and export files.",
        step: 5
    }
];

/* ------------------------- Helpers ------------------------- */

function safeRead(key, fallback) {
    try {
        const value = JSON.parse(localStorage.getItem(key));
        return value ?? fallback;
    } catch {
        return fallback;
    }
}

function safeWrite(key, value) {
    try {
        localStorage.setItem(key, JSON.stringify(value));
        return true;
    } catch {
        showToast(
            "Browser storage is full or unavailable. Download a backup instead.",
            true
        );
        return false;
    }
}

function clone(value) {
    return JSON.parse(JSON.stringify(value));
}

function arrayValue(value) {
    return Array.isArray(value) ? value : [];
}

function textValue(value, fallback = "") {
    return typeof value === "string" || typeof value === "number"
        ? String(value)
        : fallback;
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function formatBytes(bytes) {
    if (!bytes) return "0 B";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function showToast(message, isError = false) {
    if (!toast) {
        window.alert(message);
        return;
    }

    toast.textContent = message;
    toast.classList.toggle("error", isError);
    toast.classList.add("show");

    window.clearTimeout(showToast.timer);
    showToast.timer = window.setTimeout(() => {
        toast.classList.remove("show");
    }, 4500);
}

function showView(view) {
    [uploadView, processingView, resultsView].forEach((item) => {
        item?.classList.add("hidden");
    });

    view?.classList.remove("hidden");
    window.scrollTo({ top: 0, behavior: "instant" });
}

function apiUrl(path) {
    return `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
}

async function readResponse(response) {
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
        return response.json();
    }

    const body = await response.text();
    return body ? { detail: body } : {};
}

function friendlyError(error, fallback) {
    const message = String(error?.message || fallback || "");

    if (/failed to fetch|networkerror|load failed/i.test(message)) {
        return "Could not connect to the decoder. Check that the backend is running and the Render deployment is available.";
    }

    if (/no text|no requirements|could not be detected|empty document/i.test(message)) {
        return "No usable requirements were extracted. Please upload the official, text-based PDF. Scanned/image-only PDFs may require OCR before they can be decoded.";
    }

    if (/api key|authentication|unauthorized/i.test(message)) {
        return "The AI service could not authenticate. Check the server's OpenAI configuration.";
    }

    return message || fallback || "Something went wrong.";
}

/* ---------------------- File selection --------------------- */

function validateFile(file) {
    if (!file) return false;

    const isPdf =
        file.type === "application/pdf" ||
        file.name.toLowerCase().endsWith(".pdf");

    if (!isPdf) {
        showToast("Please select a PDF file.", true);
        return false;
    }

    if (file.size > MAX_FILE_SIZE) {
        showToast("The PDF exceeds the 100 MB upload limit.", true);
        return false;
    }

    if (file.size === 0) {
        showToast("The selected PDF is empty.", true);
        return false;
    }

    return true;
}

function setSelectedFile(file) {
    if (!validateFile(file)) return;

    selectedPdf = file;

    if (selectedFile) {
        selectedFile.innerHTML = `
            <div class="selected-file-left">
                <div class="file-badge">PDF</div>
                <div>
                    <div class="selected-file-name">${escapeHtml(file.name)}</div>
                    <div class="selected-file-size">${formatBytes(file.size)}</div>
                </div>
            </div>
            <button type="button" class="secondary-button" id="replaceFileButton">
                Replace PDF
            </button>
        `;
        selectedFile.classList.remove("hidden");
        $("replaceFileButton")?.addEventListener("click", () => {
            fileInput.value = "";
            fileInput.click();
        });
    }

    if (decodeButton) decodeButton.disabled = false;
}

fileInput?.addEventListener("change", () => {
    const file = fileInput.files?.[0];
    if (file) setSelectedFile(file);
});

dropZone?.addEventListener("dragover", (event) => {
    event.preventDefault();
    dropZone.classList.add("dragover");
});

dropZone?.addEventListener("dragleave", () => {
    dropZone.classList.remove("dragover");
});

dropZone?.addEventListener("drop", (event) => {
    event.preventDefault();
    dropZone.classList.remove("dragover");

    const file = event.dataTransfer?.files?.[0];
    if (file) setSelectedFile(file);
});

/* ---------------------- Processing UI ---------------------- */

function updateProcessingStage(progress) {
    const stage =
        processingStages.find((item) => progress <= item.max) ||
        processingStages[processingStages.length - 1];

    if (processingStage) processingStage.textContent = stage.title;
    if (processingText) processingText.textContent = stage.text;

    for (let i = 1; i <= 5; i++) {
        const step = $(`step${i}`);
        if (!step) continue;

        step.classList.remove("active", "completed");

        if (i < stage.step) step.classList.add("completed");
        if (i === stage.step) step.classList.add("active");
    }
}

function setProgress(value) {
    currentProgress = Math.max(0, Math.min(100, value));

    if (progressBar) progressBar.style.width = `${currentProgress}%`;
    if (progressPercent) progressPercent.textContent = `${Math.round(currentProgress)}%`;

    updateProcessingStage(currentProgress);
}

function startFakeProgress() {
    currentProgress = 8;
    setProgress(currentProgress);
    window.clearInterval(progressTimer);

    progressTimer = window.setInterval(() => {
        if (currentProgress >= 92) return;

        const increment =
            currentProgress < 25 ? 1 :
            currentProgress < 50 ? 0.65 :
            currentProgress < 72 ? 0.4 : 0.18;

        setProgress(currentProgress + increment);
    }, 900);
}

function finishProgress() {
    window.clearInterval(progressTimer);
    setProgress(100);

    for (let i = 1; i <= 5; i++) {
        const step = $(`step${i}`);
        if (step) {
            step.classList.remove("active");
            step.classList.add("completed");
        }
    }

    if (processingStage) processingStage.textContent = "Decoding completed";
    if (processingText) processingText.textContent = "Your compliance workspace is ready.";
}

/* ----------------------- Decode PDF ------------------------ */

decodeButton?.addEventListener("click", async () => {
    if (!selectedPdf) {
        showToast("Please select a PDF first.", true);
        return;
    }

    const companyName = companyInput?.value.trim() || "";
    const userEmail = emailInput?.value.trim() || "";

    if (!companyName) {
        showToast("Please enter your company name.", true);
        companyInput?.focus();
        return;
    }

    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(userEmail)) {
        showToast("Please enter a valid business email.", true);
        emailInput?.focus();
        return;
    }

    const formData = new FormData();
    formData.append("file", selectedPdf);
    formData.append("company_name", companyName);
    formData.append("user_email", userEmail);

    if (processingFile) processingFile.textContent = selectedPdf.name;
    showView(processingView);
    startFakeProgress();
    decodeButton.disabled = true;

    try {
        const response = await fetch(apiUrl("/api/decode"), {
            method: "POST",
            body: formData
        });

        const data = await readResponse(response);

        if (!response.ok) {
            throw new Error(data?.detail || data?.message || `Decode failed (${response.status}).`);
        }

        const requirements = arrayValue(data?.results?.requirements);

        if (requirements.length === 0) {
            const warnings = arrayValue(data?.results?.warnings);
            const detail = warnings.length
                ? warnings.join(" ")
                : "No actionable requirements were extracted from the PDF.";

            throw new Error(
                `${detail} Upload the official text-based framework PDF.`
            );
        }

        latestDecodeResult = data;
        isEditing = false;
        isDirty = false;
        undoStack = [];
        redoStack = [];

        finishProgress();
        await new Promise((resolve) => window.setTimeout(resolve, 350));

        addHistoryEntry(data);
        renderResults(data);
        showView(resultsView);
    } catch (error) {
        window.clearInterval(progressTimer);
        showView(uploadView);
        if (decodeButton) decodeButton.disabled = false;

        showToast(
            friendlyError(error, "The compliance document could not be decoded."),
            true
        );
    }
});

/* ------------------------- History ------------------------- */

function addHistoryEntry(data) {
    const entry = {
        document_id: data?.document_id || "",
        filename: data?.filename || "Compliance document",
        title:
            data?.results?.metadata?.document_title ||
            data?.results?.metadata?.framework_name ||
            data?.filename ||
            "Compliance document",
        requirement_count:
            data?.requirement_count ||
            arrayValue(data?.results?.requirements).length,
        saved_at: new Date().toISOString()
    };

    historyItems = [
        entry,
        ...historyItems.filter((item) =>
            item.document_id !== entry.document_id
        )
    ].slice(0, 30);

    safeWrite(HISTORY_KEY, historyItems);
}

function renderHistory() {
    if (!historyItems.length) {
        return `<p class="muted-note">No previous scans are saved in this browser yet.</p>`;
    }

    return `
        <div class="history-list">
            ${historyItems.map((item) => `
                <div class="history-item">
                    <div>
                        <strong>${escapeHtml(item.title)}</strong>
                        <p>${escapeHtml(item.filename)} · ${Number(item.requirement_count) || 0} requirements</p>
                        <small>${escapeHtml(new Date(item.saved_at).toLocaleString())}</small>
                    </div>
                    <button type="button" class="secondary-button"
                        onclick="reopenHistoryItem('${escapeHtml(item.document_id)}')">
                        Reopen
                    </button>
                </div>
            `).join("")}
        </div>
    `;
}

async function reopenHistoryItem(documentId) {
    if (!documentId) {
        showToast("This history entry has no server document ID.", true);
        return;
    }

    showToast("History currently stores scan details only in this browser. Re-decoding the PDF is required to rebuild the full workspace.", true);
}

/* ------------------------ Edit history --------------------- */

function snapshotForUndo() {
    if (!latestDecodeResult) return;

    undoStack.push(clone(latestDecodeResult));
    if (undoStack.length > MAX_UNDO_STEPS) undoStack.shift();

    redoStack = [];
    isDirty = true;
    updateEditorStatus();
}

function undoEdit() {
    if (!undoStack.length || !latestDecodeResult) return;

    redoStack.push(clone(latestDecodeResult));
    latestDecodeResult = undoStack.pop();
    isDirty = true;

    renderResults(latestDecodeResult);
    showToast("Last edit undone.");
}

function redoEdit() {
    if (!redoStack.length || !latestDecodeResult) return;

    undoStack.push(clone(latestDecodeResult));
    latestDecodeResult = redoStack.pop();
    isDirty = true;

    renderResults(latestDecodeResult);
    showToast("Edit restored.");
}

function updateEditorStatus() {
    const status = $("editorStatus");
    if (!status) return;

    status.textContent = isDirty
        ? "Unsaved changes"
        : "All changes saved";
}

function getByPath(object, path) {
    return path.split(".").reduce((value, key) => value?.[key], object);
}

function setByPath(object, path, value) {
    const keys = path.split(".");
    const last = keys.pop();
    const target = keys.reduce((current, key) => current[key], object);
    target[last] = value;
}

function applyFieldEdit(element) {
    if (!latestDecodeResult || !isEditing) return;

    const path = element.dataset.editPath;
    if (!path) return;

    const previous = String(getByPath(latestDecodeResult, path) ?? "");
    const next = element.value;

    if (previous === next) return;

    snapshotForUndo();
    setByPath(latestDecodeResult, path, next);
    updateEditorStatus();
}

function toggleEditing() {
    isEditing = !isEditing;
    renderResults(latestDecodeResult);
    showToast(isEditing ? "Edit mode enabled." : "Edit mode disabled.");
}

/* ----------------------- Export / Save --------------------- */

function downloadBlob(filename, content, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");

    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();

    URL.revokeObjectURL(url);
}

function saveWorkspace() {
    if (!latestDecodeResult) return;

    const key = latestDecodeResult.document_id || "current";
    const saved = safeWrite(`${SAVE_KEY}:${key}`, latestDecodeResult);

    if (saved) {
        isDirty = false;
        updateEditorStatus();
        showToast("Saved in this browser. Download JSON for a portable backup.");
    }
}

function saveAsJson() {
    if (!latestDecodeResult) return;

    const filename = safeFilename(
        latestDecodeResult?.results?.metadata?.document_title ||
        latestDecodeResult?.filename ||
        "compliance-regulation"
    );

    downloadBlob(
        `${filename}.json`,
        JSON.stringify(latestDecodeResult, null, 2),
        "application/json;charset=utf-8"
    );
}

function safeFilename(value) {
    return String(value)
        .replace(/[<>:"/\\|?*\x00-\x1F]/g, "-")
        .replace(/\s+/g, "-")
        .slice(0, 100) || "compliance-regulation";
}

function downloadOutput(type) {
    if (!latestDecodeResult?.document_id) {
        showToast("No server output is available. Download the edited workspace as JSON instead.", true);
        return;
    }

    const allowedTypes = new Set(["json", "csv"]);
    if (!allowedTypes.has(type)) {
        showToast("Unsupported export type.", true);
        return;
    }

    const url = apiUrl(
        `/api/download/${type}/${encodeURIComponent(latestDecodeResult.document_id)}`
    );

    window.open(url, "_blank", "noopener");
}

/* ------------------------ Rendering ------------------------ */

function renderResults(data) {
    if (!resultsRoot) return;

    const results = data?.results || {};
    const metadata = results?.metadata || {};
    const requirements = arrayValue(results?.requirements);
    const documentName = data?.filename || "Compliance document";
    const documentTitle =
        metadata?.document_title ||
        metadata?.framework_name ||
        documentName;

    const pageCount = data?.page_count || metadata?.page_count || "—";
    const requirementCount = data?.requirement_count || requirements.length;

    const profileSummary =
        metadata?.regulation_summary ||
        metadata?.document_summary ||
        metadata?.summary ||
        "";

    const warnings = arrayValue(results?.warnings);

    resultsRoot.innerHTML = `
        <div class="results-container">
            <div class="results-header">
                <div>
                    <div class="results-eyebrow">MY COMPLIANCES / DECODER</div>
                    <h1 class="results-title">${escapeHtml(documentTitle)}</h1>
                    <p class="results-subtitle">${escapeHtml(documentName)}</p>
                </div>
                <div class="results-actions">
                    <button class="secondary-button" type="button" onclick="downloadOutput('json')">JSON</button>
                    <button class="secondary-button" type="button" onclick="downloadOutput('csv')">CSV</button>
                    <button class="secondary-button" type="button" onclick="saveAsJson()">Save As JSON</button>
                    <button class="secondary-button" type="button" onclick="saveWorkspace()">Save</button>
                    <button class="secondary-button" type="button" onclick="toggleEditing()">${isEditing ? "Done Editing" : "Edit Workspace"}</button>
                    <button class="secondary-button" type="button" onclick="undoEdit()" ${undoStack.length ? "" : "disabled"}>Undo</button>
                    <button class="secondary-button" type="button" onclick="redoEdit()" ${redoStack.length ? "" : "disabled"}>Redo</button>
                    ${renderSendButton(data)}
                    <button class="secondary-button" type="button" onclick="decodeAnother()">Replace / Decode Another</button>
                </div>
            </div>

            <div class="editor-status-row">
                <span id="editorStatus">${isDirty ? "Unsaved changes" : "All changes saved"}</span>
                <span>${isEditing ? "Edit mode enabled — change text fields and save." : "Read-only view"}</span>
            </div>

            <div class="summary-grid">
                <div class="summary-card">
                    <div class="summary-label">Document</div>
                    <div class="summary-value summary-document">${escapeHtml(documentName)}</div>
                </div>
                <div class="summary-card">
                    <div class="summary-label">Pages</div>
                    <div class="summary-value">${escapeHtml(pageCount)}</div>
                </div>
                <div class="summary-card">
                    <div class="summary-label">Requirements</div>
                    <div class="summary-value">${escapeHtml(requirementCount)}</div>
                </div>
                <div class="summary-card">
                    <div class="summary-label">Status</div>
                    <div class="summary-value status-success">Decoded</div>
                </div>
            </div>

            ${renderProfile(metadata, profileSummary)}

            ${warnings.length ? `
                <section class="decoder-warning">
                    <h3>Extraction warnings</h3>
                    <ul>${warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}</ul>
                    <p>Verify extracted requirements against the original PDF before importing them into a compliance platform.</p>
                </section>
            ` : ""}

            <section class="requirements-section">
                <div class="section-heading">
                    <div class="section-heading-left">
                        <span class="section-badge">Requirements</span>
                        <strong>Compliance requirements</strong>
                    </div>
                    <span class="requirement-count">${requirements.length} items</span>
                </div>

                ${requirements.length
                    ? requirements.map((item, index) => renderRequirement(item, index)).join("")
                    : renderEmptyRequirements()
                }
            </section>

            <section class="history-section">
                <div class="section-heading"><strong>Recent scans in this browser</strong></div>
                ${renderHistory()}
            </section>
        </div>
    `;
}

function renderProfile(metadata, summary) {
    const fields = [
        ["Document type", "document_type"],
        ["Framework / regulation", "framework_name"],
        ["Version", "version"],
        ["Jurisdiction", "jurisdiction"],
        ["Requirement unit", "requirement_unit_name"],
        ["Hierarchy", "hierarchy_description"]
    ];

    const fieldMarkup = fields.map(([label, key]) => {
        const value = textValue(metadata?.[key]);
        if (!value) return "";

        return `
            <div class="profile-field">
                <span>${escapeHtml(label)}</span>
                ${renderEditableText(value, `results.metadata.${key}`, "profile-value")}
            </div>
        `;
    }).join("");

    return `
        <section class="regulation-profile">
            <h2>Regulation overview</h2>
            ${summary ? `<p class="regulation-summary">${escapeHtml(summary)}</p>` : `
                <p class="muted-note">No AI-generated regulation summary was returned by the backend for this scan.</p>
            `}
            <div class="profile-grid">${fieldMarkup || `<p class="muted-note">No document profile metadata was returned.</p>`}</div>
            ${arrayValue(metadata?.hierarchy_levels).length ? `
                <div class="hierarchy-levels">
                    <strong>Detected hierarchy levels</strong>
                    <div>${metadata.hierarchy_levels.map((level) => `<span>${escapeHtml(level)}</span>`).join("")}</div>
                </div>
            ` : ""}
        </section>
    `;
}

function renderEditableText(value, path, className = "") {
    if (!isEditing) return `<span class="${className}">${escapeHtml(value)}</span>`;

    return `
        <textarea class="decoder-edit-field ${className}"
            data-edit-path="${escapeHtml(path)}"
            rows="2">${escapeHtml(value)}</textarea>
    `;
}

function renderRequirement(requirement, index) {
    const reference = requirement?.source_reference || `Requirement ${index + 1}`;
    const base = `results.requirements.${index}`;

    const title = requirement?.source_title || reference;
    const sourceText = requirement?.source_text || "Source requirement text unavailable.";
    const summary = requirement?.source_summary || "";
    const todo = requirement?.todo || {};
    const policies = arrayValue(requirement?.policies);
    const documents = arrayValue(requirement?.documents);
    const evidence = arrayValue(requirement?.evidence);
    const automationTests = arrayValue(
        requirement?.automation_tests || requirement?.tests || requirement?.automated_tests
    );

    const pageStart = requirement?.page_start;
    const pageEnd = requirement?.page_end;

    return `
        <article class="requirement-card ${index === 0 ? "open" : ""}">
            <button type="button" class="requirement-header" onclick="toggleRequirement(this)">
                <div class="requirement-title-wrap">
                    <span class="requirement-reference">${escapeHtml(reference)}</span>
                    <span class="requirement-title">${escapeHtml(title)}</span>
                </div>
                <span class="requirement-chevron">⌄</span>
            </button>

            <div class="requirement-body">
                <div class="content-label">Source requirement — verify against PDF</div>
                ${renderEditableText(sourceText, `${base}.source_text`, "source-box")}

                ${pageStart ? `
                    <div class="source-meta">
                        Source pages: ${escapeHtml(pageStart)}${pageEnd && pageEnd !== pageStart ? `–${escapeHtml(pageEnd)}` : ""}
                    </div>
                ` : ""}

                ${summary ? `
                    <div class="implementation-box">
                        <h4>Requirement summary</h4>
                        ${renderEditableText(summary, `${base}.source_summary`)}
                    </div>
                ` : ""}

                <div class="implementation-box">
                    <h4>Implementation action / To-do</h4>
                    ${renderEditableText(todo?.name || "Implementation action", `${base}.todo.name`)}
                    ${todo?.description ? renderEditableText(todo.description, `${base}.todo.description`) : ""}
                </div>

                ${renderHierarchyPath(requirement?.hierarchy_path)}

                <div class="recommendation-grid">
                    ${renderRecommendationCard("Policies", policies, `${base}.policies`)}
                    ${renderRecommendationCard("Documents", documents, `${base}.documents`)}
                    ${renderRecommendationCard("Evidence", evidence, `${base}.evidence`)}
                    ${renderRecommendationCard("Automation tests", automationTests, `${base}.automation_tests`)}
                </div>
            </div>
        </article>
    `;
}

function renderHierarchyPath(path) {
    if (!path) return "";

    const parts = Array.isArray(path)
        ? path
        : typeof path === "string"
            ? path.split(/[>/|]/).map((part) => part.trim()).filter(Boolean)
            : [];

    if (!parts.length) return "";

    return `
        <div class="hierarchy-path">
            <div class="content-label">Detected hierarchy</div>
            <div>${parts.map((part) => `<span>${escapeHtml(part)}</span>`).join("<span class='hierarchy-separator'>›</span>")}</div>
        </div>
    `;
}

function renderRecommendationCard(title, items, path) {
    if (!items.length) {
        return `
            <div class="recommendation-card">
                <h4>${escapeHtml(title)}</h4>
                <div class="recommendation-item"><strong>No recommendations returned</strong></div>
            </div>
        `;
    }

    return `
        <div class="recommendation-card">
            <h4>${escapeHtml(title)}</h4>
            ${items.map((item, index) => {
                const itemPath = `${path}.${index}`;
                const name = textValue(item?.name, textValue(item));
                const description = textValue(item?.description);

                return `
                    <div class="recommendation-item">
                        ${renderEditableText(name, `${itemPath}.name`)}
                        ${description ? renderEditableText(description, `${itemPath}.description`) : ""}
                    </div>
                `;
            }).join("")}
        </div>
    `;
}

function renderSendButton(data) {
    if (data?.email_status === "sent") {
        return `<button class="send-button sent" type="button" disabled>✓ Sent to Sahl</button>`;
    }

    const label = data?.email_status === "failed"
        ? "Retry sending to Sahl"
        : "Send to Sahl";

    return `<button class="send-button" type="button" onclick="handleSendToSahl()">${label}</button>`;
}

function renderEmptyRequirements() {
    return `
        <div class="empty-requirements">
            No requirements were returned. Please check the PDF and server extraction warnings.
        </div>
    `;
}

function toggleRequirement(button) {
    button.closest(".requirement-card")?.classList.toggle("open");
}

/* ----------------------- Edit interactions ----------------- */

resultsRoot?.addEventListener("focusout", (event) => {
    if (event.target.matches("[data-edit-path]")) {
        applyFieldEdit(event.target);
    }
});

resultsRoot?.addEventListener("keydown", (event) => {
    if (!(event.ctrlKey || event.metaKey)) return;

    if (event.key.toLowerCase() === "z" && !event.shiftKey) {
        event.preventDefault();
        undoEdit();
    } else if (
        event.key.toLowerCase() === "z" && event.shiftKey ||
        event.key.toLowerCase() === "y"
    ) {
        event.preventDefault();
        redoEdit();
    }
});

/* ------------------------ Send to Sahl --------------------- */

async function handleSendToSahl() {
    if (!latestDecodeResult?.document_id) {
        showToast("No decoded submission is available.", true);
        return;
    }

    if (latestDecodeResult.email_status === "sent") {
        showToast("This decoded document has already been sent to Sahl.");
        return;
    }

    const button = document.querySelector(".send-button");
    if (button) {
        button.disabled = true;
        button.textContent = "Sending…";
    }

    const formData = new FormData();
    formData.append("company_name", companyInput?.value.trim() || "");
    formData.append("user_email", emailInput?.value.trim() || "");

    try {
        const response = await fetch(
            apiUrl(`/api/send-to-sahl/${encodeURIComponent(latestDecodeResult.document_id)}`),
            { method: "POST", body: formData }
        );

        const data = await readResponse(response);

        if (!response.ok) {
            throw new Error(data?.detail || data?.message || `Email submission failed (${response.status}).`);
        }

        latestDecodeResult.email_status = "sent";
        latestDecodeResult.email_recipients = arrayValue(data?.recipients).join(", ");

        renderResults(latestDecodeResult);
        showToast("Successfully sent the decoded files to Sahl.");
    } catch (error) {
        latestDecodeResult.email_status = "failed";
        renderResults(latestDecodeResult);

        showToast(
            friendlyError(error, "Could not send the files to Sahl. Check the server's SMTP settings."),
            true
        );
    }
}

/* ----------------------- Decode another ------------------- */

function decodeAnother() {
    if (isDirty && !window.confirm("You have unsaved edits. Leave this workspace anyway?")) {
        return;
    }

    latestDecodeResult = null;
    selectedPdf = null;
    isEditing = false;
    isDirty = false;
    undoStack = [];
    redoStack = [];

    if (fileInput) fileInput.value = "";
    if (selectedFile) {
        selectedFile.innerHTML = "";
        selectedFile.classList.add("hidden");
    }

    if (decodeButton) decodeButton.disabled = true;
    if (companyInput) companyInput.value = "";
    if (emailInput) emailInput.value = "";

    window.clearInterval(progressTimer);
    setProgress(8);
    showView(uploadView);
}

/* --------------------------- Init -------------------------- */

if (decodeButton) decodeButton.disabled = true;
showView(uploadView);
