
const API_BASE = "";

const uploadView = document.getElementById("uploadView");
const processingView = document.getElementById("processingView");
const resultsView = document.getElementById("resultsView");

const dropZone = document.getElementById("dropZone");
const fileInput = document.getElementById("fileInput");
const selectedFile = document.getElementById("selectedFile");

const companyInput = document.getElementById("companyInput");
const emailInput = document.getElementById("emailInput");

const decodeButton = document.getElementById("decodeButton");

const processingFile = document.getElementById("processingFile");
const processingText = document.getElementById("processingText");
const processingStage = document.getElementById("processingStage");
const progressPercent = document.getElementById("progressPercent");
const progressBar = document.getElementById("progressBar");

const toast = document.getElementById("toast");
const resultsRoot = document.getElementById("resultsRoot");

const MAX_FILE_SIZE = 100 * 1024 * 1024;

let selectedPdf = null;
let progressTimer = null;
let currentProgress = 8;
let processingStartedAt = null;
let latestDecodeResult = null;


/* =========================================================
   BASIC HELPERS
   ========================================================= */

function showView(view) {
    uploadView.classList.add("hidden");
    processingView.classList.add("hidden");
    resultsView.classList.add("hidden");

    view.classList.remove("hidden");

    window.scrollTo({
        top: 0,
        behavior: "instant"
    });
}


function showToast(message, isError = false) {
    toast.textContent = message;

    toast.classList.toggle("error", isError);
    toast.classList.add("show");

    window.clearTimeout(showToast.timer);

    showToast.timer = window.setTimeout(() => {
        toast.classList.remove("show");
    }, 3500);
}


function formatBytes(bytes) {
    if (!bytes) {
        return "0 B";
    }

    if (bytes < 1024) {
        return `${bytes} B`;
    }

    if (bytes < 1024 * 1024) {
        return `${(bytes / 1024).toFixed(1)} KB`;
    }

    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}


function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}


function arrayValue(value) {
    return Array.isArray(value) ? value : [];
}


/* =========================================================
   FILE SELECTION
   ========================================================= */

function validateFile(file) {
    if (!file) {
        return false;
    }

    const isPdf =
        file.type === "application/pdf" ||
        file.name.toLowerCase().endsWith(".pdf");

    if (!isPdf) {
        showToast(
            "Please select a PDF file.",
            true
        );

        return false;
    }

    if (file.size > MAX_FILE_SIZE) {
        showToast(
            "The PDF exceeds the 100 MB upload limit.",
            true
        );

        return false;
    }

    return true;
}


function setSelectedFile(file) {
    if (!validateFile(file)) {
        selectedPdf = null;
        fileInput.value = "";
        selectedFile.innerHTML = "";
        selectedFile.classList.add("hidden");
        decodeButton.disabled = true;
        return;
    }

    selectedPdf = file;

    selectedFile.innerHTML = `
        <div class="selected-file-left">
            <div class="file-badge">PDF</div>

            <div>
                <div class="selected-file-name">
                    ${escapeHtml(file.name)}
                </div>

                <div class="selected-file-size">
                    ${formatBytes(file.size)}
                </div>
            </div>
        </div>
        <div class="selected-file-actions">
            <button type="button" class="secondary-button" id="replacePdfButton">Replace PDF</button>
            <button type="button" class="secondary-button" id="removePdfButton">Remove PDF</button>
        </div>
    `;

    selectedFile.classList.remove("hidden");

    decodeButton.disabled = false;
    const replaceButton = document.getElementById("replacePdfButton");
    const removeButton = document.getElementById("removePdfButton");
    replaceButton?.addEventListener("click", () => fileInput.click());
    removeButton?.addEventListener("click", clearSelectedPdf);
}

function clearSelectedPdf() {
    selectedPdf = null;
    fileInput.value = "";
    selectedFile.innerHTML = "";
    selectedFile.classList.add("hidden");
    decodeButton.disabled = true;
    showToast("PDF removed. Choose a PDF to continue.");
}


fileInput.addEventListener(
    "change",
    () => {
        const file = fileInput.files?.[0];

        if (file) {
            setSelectedFile(file);
        }
    }
);


/* =========================================================
   DRAG AND DROP
   ========================================================= */

dropZone.addEventListener(
    "dragover",
    (event) => {
        event.preventDefault();
        dropZone.classList.add("dragover");
    }
);


dropZone.addEventListener(
    "dragleave",
    () => {
        dropZone.classList.remove("dragover");
    }
);


dropZone.addEventListener(
    "drop",
    (event) => {
        event.preventDefault();

        dropZone.classList.remove("dragover");

        const file = event.dataTransfer.files?.[0];

        if (file) {
            setSelectedFile(file);
        }
    }
);


/* =========================================================
   PROCESSING PROGRESS
   ========================================================= */

const processingStages = [
    {
        max: 20,
        title: "Reading PDF",
        text:
            "Reading the uploaded document and extracting its content.",
        step: 1
    },
    {
        max: 42,
        title: "Understanding document structure",
        text:
            "Detecting sections, hierarchy and terminology used by the document.",
        step: 2
    },
    {
        max: 67,
        title: "Identifying requirements",
        text:
            "Finding the actual actionable compliance requirements in the document.",
        step: 3
    },
    {
        max: 84,
        title: "Building implementation guidance",
        text:
            "Preparing practical actions, policies, documents and evidence recommendations.",
        step: 4
    },
    {
        max: 94,
        title: "Preparing Sahl-ready output",
        text:
            "Finalizing the compliance breakdown and preparing JSON and CSV outputs.",
        step: 5
    }
];


function updateProcessingStage(progress) {
    const stage =
        processingStages.find(
            item => progress <= item.max
        ) ||
        processingStages[
            processingStages.length - 1
        ];

    processingStage.textContent = stage.title;
    processingText.textContent = stage.text;

    for (let i = 1; i <= 5; i++) {
        const step =
            document.getElementById(`step${i}`);

        if (!step) {
            continue;
        }

        step.classList.remove(
            "active",
            "completed"
        );

        if (i < stage.step) {
            step.classList.add("completed");
        }

        if (i === stage.step) {
            step.classList.add("active");
        }
    }
}


function setProgress(value) {
    currentProgress = Math.max(
        0,
        Math.min(100, value)
    );

    progressBar.style.width =
        `${currentProgress}%`;

    progressPercent.textContent =
        `${Math.round(currentProgress)}%`;

    updateProcessingStage(
        currentProgress
    );
}


function startFakeProgress() {
    processingStartedAt = Date.now();

    currentProgress = 8;

    setProgress(currentProgress);

    window.clearInterval(
        progressTimer
    );

    progressTimer = window.setInterval(
        () => {

            if (currentProgress >= 92) {
                return;
            }

            let increment = 0.35;

            if (currentProgress < 25) {
                increment = 1.0;
            } else if (currentProgress < 50) {
                increment = 0.65;
            } else if (currentProgress < 72) {
                increment = 0.4;
            } else {
                increment = 0.18;
            }

            setProgress(
                currentProgress + increment
            );

        },
        900
    );
}


function finishProgress() {
    window.clearInterval(
        progressTimer
    );

    setProgress(100);

    for (let i = 1; i <= 5; i++) {
        const step =
            document.getElementById(`step${i}`);

        if (step) {
            step.classList.remove("active");
            step.classList.add("completed");
        }
    }

    processingStage.textContent =
        "Decoding completed";

    processingText.textContent =
        "Your compliance workspace is ready.";
}


/* =========================================================
   START DECODING
   ========================================================= */

decodeButton.addEventListener(
    "click",
    async () => {

        if (!selectedPdf) {
            showToast(
                "Please select a PDF first.",
                true
            );
            return;
        }

        const companyName =
            companyInput.value.trim();

        const userEmail =
            emailInput.value.trim();

        if (!companyName) {
            showToast(
                "Please enter your company name.",
                true
            );

            companyInput.focus();

            return;
        }

        if (
            !userEmail ||
            !userEmail.includes("@")
        ) {
            showToast(
                "Please enter a valid business email.",
                true
            );

            emailInput.focus();

            return;
        }

        const formData =
            new FormData();

        formData.append(
            "file",
            selectedPdf
        );

        formData.append(
            "company_name",
            companyName
        );

        formData.append(
            "user_email",
            userEmail
        );


        processingFile.textContent =
            selectedPdf.name;

        showView(processingView);

        startFakeProgress();

        decodeButton.disabled = true;


        try {

            const response =
                await fetch(
                    `${API_BASE}/api/decode`,
                    {
                        method: "POST",
                        body: formData
                    }
                );


            let data = null;

            try {
                data = await response.json();
            } catch {
                data = null;
            }


            if (!response.ok) {

                const errorMessage =
                    data?.detail ||
                    "The compliance document could not be decoded.";

                throw new Error(
                    errorMessage
                );
            }


            latestDecodeResult = data;
            saveScanToLocalHistory(data);

            finishProgress();


            await new Promise(
                resolve =>
                    setTimeout(resolve, 700)
            );


            renderResults(data);

            showView(resultsView);


        } catch (error) {

            window.clearInterval(
                progressTimer
            );

            showView(uploadView);

            decodeButton.disabled = false;

            showToast(
                error?.message ||
                "Something went wrong while decoding the PDF.",
                true
            );
        }

    }
);


/* =========================================================
   RESULTS RENDERING
   ========================================================= */


let complianceEditMode = false;

function setComplianceEditMode(enabled) {
    complianceEditMode = Boolean(enabled);
    document.querySelectorAll("[data-edit-field]").forEach(field => {
        field.contentEditable = complianceEditMode ? "true" : "false";
        field.classList.toggle("editing", complianceEditMode);
    });
    const button = document.getElementById("toggleEditButton");
    if (button) button.textContent = complianceEditMode ? "Finish editing" : "Edit compliance";
}

function toggleComplianceEditing() {
    if (complianceEditMode) {
        collectEditedFields();
        setComplianceEditMode(false);
        showToast("Editing finished. Use Save changes or Save as to keep your edits.");
    } else {
        setComplianceEditMode(true);
        showToast("Edit the requirement fields, then choose Save changes or Save as.");
    }
}

function renderResults(data) {

    const results =
        data?.results || {};

    const metadata =
        results?.metadata || {};

    const requirements =
        arrayValue(
            results?.requirements
        );

    const documentName =
        data?.filename ||
        metadata?.filename ||
        "Compliance document";

    const pageCount =
        data?.page_count ||
        metadata?.page_count ||
        0;

    const requirementCount =
        data?.requirement_count ||
        metadata?.requirement_count ||
        requirements.length;

    const documentTitle =
        metadata?.document_title ||
        metadata?.framework_name ||
        documentName;


    resultsRoot.innerHTML = `

        <div class="results-container">

            <div class="results-header">

                <div>

                    <div class="results-eyebrow">
                        MY COMPLIANCES / DECODER
                    </div>

                    <h1 class="results-title">
                        ${escapeHtml(documentTitle)}
                    </h1>

                    <p class="results-subtitle">
                        ${escapeHtml(documentName)}
                    </p>

                </div>


                <div class="results-actions">
                    <button class="secondary-button" type="button" id="toggleEditButton" onclick="toggleComplianceEditing()">Edit compliance</button>
                    <button class="secondary-button" type="button" onclick="downloadOutput('pdf')">Original PDF</button>
                    <button class="secondary-button" type="button" onclick="downloadEditedRegulation('json')">Download regulation</button>
                    <button class="secondary-button" type="button" onclick="downloadEditedRegulation('csv')">CSV</button>
                    <button class="secondary-button" type="button" onclick="saveEditedRegulation()">Save changes</button>
                    <button class="secondary-button" type="button" onclick="saveAsRegulation()">Save as…</button>
                    <button class="secondary-button" type="button" onclick="removeCurrentDocument()">Remove document</button>
                    <button class="send-button" type="button" onclick="handleSendToSahl()">Add regulation to Sahl</button>
                    <button class="secondary-button" type="button" onclick="decodeAnother()">Decode another</button>
                </div>

            </div>


            <section class="regulation-overview">
                <h2>Regulation overview</h2>
                <p class="overview-summary">${escapeHtml(metadata?.regulation_summary || "A regulation summary was not returned for this document. Review the source PDF for scope and intent.")}</p>
                <div class="overview-details">
                    ${metadata?.document_type ? `<p><strong>Document type</strong><span>${escapeHtml(metadata.document_type)}</span></p>` : ""}
                    ${metadata?.framework_name ? `<p><strong>Framework</strong><span>${escapeHtml(metadata.framework_name)}</span></p>` : ""}
                    ${metadata?.version ? `<p><strong>Version</strong><span>${escapeHtml(metadata.version)}</span></p>` : ""}
                    ${metadata?.jurisdiction ? `<p><strong>Jurisdiction</strong><span>${escapeHtml(metadata.jurisdiction)}</span></p>` : ""}
                    ${metadata?.applicability_conditions ? `<p><strong>Applicability</strong><span>${escapeHtml(metadata.applicability_conditions)}</span></p>` : ""}
                    ${arrayValue(metadata?.applicable_industries).length ? `<p><strong>Industries</strong><span>${arrayValue(metadata.applicable_industries).map(escapeHtml).join(", ")}</span></p>` : ""}
                </div>
            </section>

            <div class="summary-grid">

                <div class="summary-card">

                    <div class="summary-label">
                        Document
                    </div>

                    <div
                        class="summary-value"
                        style="font-size:13px;"
                    >
                        ${escapeHtml(documentName)}
                    </div>

                </div>


                <div class="summary-card">

                    <div class="summary-label">
                        Pages
                    </div>

                    <div class="summary-value">
                        ${pageCount}
                    </div>

                </div>


                <div class="summary-card">

                    <div class="summary-label">
                        Requirements
                    </div>

                    <div class="summary-value">
                        ${requirementCount}
                    </div>

                </div>


                <div class="summary-card">

                    <div class="summary-label">
                        Status
                    </div>

                    <div
                        class="summary-value"
                        style="font-size:14px;color:#159447;"
                    >
                        Decoded
                    </div>

                </div>

            </div>


            <div class="requirements-section">

                <div class="section-heading">

                    <div class="section-heading-left">

                        <span class="section-badge">
                            Requirements
                        </span>

                        <strong>
                            Compliance requirements
                        </strong>

                    </div>

                    <span
                        style="
                            color:#958c9e;
                            font-size:10px;
                        "
                    >
                        ${requirementCount} items
                    </span>

                </div>


                ${requirements.length
                    ? requirements
                        .map(
                            (requirement, index) =>
                                renderRequirement(
                                    requirement,
                                    index
                                )
                        )
                        .join("")
                    : renderEmptyRequirements()
                }

            </div>

        </div>
    `;
    setComplianceEditMode(false);
}


function renderSendButton(data) {

    const slackStatus =
        data?.slack_status || "";

    if (slackStatus === "sent") {

        return `
            <button
                class="send-button sent"
                type="button"
                disabled
            >
                ✓ Sent to Sahl on Slack
            </button>
        `;
    }

    if (slackStatus === "failed") {

        return `
            <button
                class="send-button failed"
                type="button"
                onclick="handleSendToSahl()"
            >
                Retry Slack notification
            </button>
        `;
    }

    return `
        <button
            class="send-button"
            type="button"
            onclick="handleSendToSahl()"
        >
            Send to Sahl
        </button>
    `;
}


function renderRequirement(
    requirement,
    index
) {

    const reference =
        requirement?.source_reference ||
        `Requirement ${index + 1}`;

    const title =
        requirement?.source_title ||
        reference;

    const sourceText =
        requirement?.source_text ||
        "Source requirement text unavailable.";

    const summary =
        requirement?.source_summary ||
        "";

    const todo =
        requirement?.todo || {};

    const policies =
        arrayValue(
            requirement?.policies
        );

    const documents =
        arrayValue(
            requirement?.documents
        );

    const evidence =
        arrayValue(
            requirement?.evidence
        );

    const pageStart =
        requirement?.page_start;

    const pageEnd =
        requirement?.page_end;


    return `

        <article
            class="requirement-card ${index === 0 ? "open" : ""}"
            data-requirement-index="${index}"
        >

            <button
                type="button"
                class="requirement-header"
                onclick="toggleRequirement(this)"
            >

                <div class="requirement-title-wrap">

                    <span class="requirement-reference">
                        ${escapeHtml(reference)}
                    </span>

                    <span class="requirement-title editable-field" contenteditable="true" spellcheck="true" data-edit-field="source_title">
                        ${escapeHtml(title)}
                    </span>

                </div>

                <span class="requirement-chevron">
                   ⌄
                </span>

            </button>


            <div class="requirement-body">

                <div class="content-label">
                    Source requirement
                </div>


                <div class="source-box editable-field" contenteditable="true" spellcheck="true" data-edit-field="source_text">
                    ${escapeHtml(sourceText)}
                </div>


                ${
                    pageStart
                    ? `
                        <div class="source-meta">
                            Source pages:
                            ${escapeHtml(pageStart)}
                            ${
                                pageEnd &&
                                pageEnd !== pageStart
                                ? `–${escapeHtml(pageEnd)}`
                                : ""
                            }
                        </div>
                    `
                    : ""
                }


                ${
                    summary
                    ? `
                        <div class="implementation-box">

                            <h4>
                                Requirement summary
                            </h4>

                            <p class="editable-field" contenteditable="true" spellcheck="true" data-edit-field="source_summary">
                                ${escapeHtml(summary)}
                            </p>

                        </div>
                    `
                    : ""
                }


                <div class="implementation-box">

                    <h4>
                        Implementation action
                    </h4>

                    <p class="editable-field" contenteditable="true" spellcheck="true" data-edit-field="todo.name">
                        ${escapeHtml(todo?.name || "Implementation action")}
                    </p>

                    ${
                        todo?.description
                        ? `
                            <p class="editable-field" contenteditable="true" spellcheck="true" data-edit-field="todo.description" style="margin-top:5px;">
                                ${escapeHtml(todo.description)}
                            </p>
                        `
                        : ""
                    }

                </div>


                <div class="recommendation-grid">

                    ${renderRecommendationCard(
                        "Policies",
                        policies
                    )}

                    ${renderRecommendationCard(
                        "Documents",
                        documents
                    )}

                    ${renderRecommendationCard(
                        "Evidence",
                        evidence
                    )}
                    ${renderRecommendationCard(
                        "Automation tests",
                        arrayValue(requirement?.automation_tests),
                        "No suitable automation test was identified for this requirement. Manual verification may be needed."
                    )}

                </div>

            </div>

        </article>
    `;
}


function renderRecommendationCard(
    title,
    items,
    emptyMessage = "No recommendations were generated for this section."
) {

    if (!items.length) {

        return `
            <div class="recommendation-card">

                <h4>
                    ${escapeHtml(title)}
                </h4>

                <div class="recommendation-item">

                    <strong>
                        Not available
                    </strong>
                    <p>${escapeHtml(emptyMessage)}</p>

                </div>

            </div>
        `;
    }


    return `
        <div class="recommendation-card">

            <h4>
                ${escapeHtml(title)}
            </h4>

            ${items
                .map(
                    item => `
                        <div class="recommendation-item">

                            <strong>
                                ${escapeHtml(
                                    item?.name ||
                                    ""
                                )}
                            </strong>

                            ${
                                item?.description
                                ? `
                                    <p>
                                        ${escapeHtml(
                                            item.description
                                        )}
                                    </p>
                                `
                                : ""
                            }

                        </div>
                    `
                )
                .join("")
            }

        </div>
    `;
}


function renderEmptyRequirements() {

    return `
        <div
            style="
                padding:40px 20px;
                text-align:center;
                color:#8e8597;
                font-size:12px;
            "
        >
            No requirements were returned by the decoder.
        </div>
    `;
}


/* =========================================================
   REQUIREMENT ACCORDION
   ========================================================= */

function toggleRequirement(button) {

    const card =
        button.closest(
            ".requirement-card"
        );

    if (!card) {
        return;
    }

    card.classList.toggle("open");
}


/* =========================================================
   DOWNLOADS
   ========================================================= */

function downloadOutput(type) {

    if (!latestDecodeResult) {
        return;
    }

    const documentId =
        latestDecodeResult.document_id;

    if (!documentId) {
        showToast(
            "The output file is not available.",
            true
        );

        return;
    }

    const url =
        `${API_BASE}/api/download/${type}/${encodeURIComponent(
            documentId
        )}`;

    window.open(
        url,
        "_blank"
    );
}


/* =========================================================
   SEND TO SAHL
   ========================================================= */

async function handleSendToSahl() {
    if (!latestDecodeResult?.document_id) {
        showToast("Decode a regulation before adding it to Sahl.", true);
        return;
    }

    if (latestDecodeResult.slack_status === "sent") {
        showToast("This regulation has already been sent to Sahl on Slack.");
        return;
    }

    collectEditedFields();
    const button = document.querySelector(".send-button");
    const originalText = button?.textContent || "Add regulation to Sahl";
    if (button) {
        button.disabled = true;
        button.textContent = "Sending to Slack…";
    }

    const metadata = latestDecodeResult?.results?.metadata || {};
    const requirements = arrayValue(latestDecodeResult?.results?.requirements);
    const payload = {
        document_id: latestDecodeResult.document_id,
        filename: latestDecodeResult.filename || metadata.filename || "Compliance document",
        framework_name: metadata.framework_name || metadata.document_title || latestDecodeResult.framework_name || "Not identified",
        company_name: companyInput?.value?.trim() || "Not provided",
        user_email: emailInput?.value?.trim() || "Not provided",
        requirement_count: requirements.length,
        requirements,
        regulation: latestDecodeResult
    };

    try {
        const response = await fetch(`${API_BASE}/api/slack/notify`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        let data = {};
        try { data = await response.json(); } catch {}
        if (!response.ok) {
            throw new Error(data?.detail || "Slack notification failed.");
        }
        latestDecodeResult.slack_status = "sent";
        saveEditedRegulation(false);
        renderResults(latestDecodeResult);
        showToast(`Sent edited compliance to Slack (${data?.slack_messages_sent || "multiple"} messages).`);
    } catch (error) {
        latestDecodeResult.slack_status = "failed";
        renderResults(latestDecodeResult);
        showToast(error?.message || "Could not notify Sahl on Slack. Check SLACK_WEBHOOK_URL and retry.", true);
    } finally {
        const currentButton = document.querySelector(".send-button");
        if (currentButton && currentButton.disabled) {
            currentButton.disabled = false;
            currentButton.textContent = originalText;
        }
    }
}

function collectEditedFields() {
    if (!latestDecodeResult) return;
    const requirements = arrayValue(latestDecodeResult?.results?.requirements);
    document.querySelectorAll("[data-requirement-index]").forEach(card => {
        const index = Number(card.dataset.requirementIndex);
        const item = requirements[index];
        if (!item) return;
        card.querySelectorAll("[data-edit-field]").forEach(field => {
            const key = field.dataset.editField;
            const value = field.innerText.trim();
            if (key === "todo.name") {
                item.todo = item.todo || {}; item.todo.name = value;
            } else if (key === "todo.description") {
                item.todo = item.todo || {}; item.todo.description = value;
            } else {
                item[key] = value;
            }
        });
    });
}

function saveEditedRegulation(showMessage = true) {
    if (!latestDecodeResult) {
        showToast("No regulation is open to save.", true);
        return false;
    }
    collectEditedFields();
    const key = "sahlComplianceDecoderSavedRegulations";
    try {
        const existing = JSON.parse(localStorage.getItem(key) || "[]");
        const id = latestDecodeResult.document_id || latestDecodeResult.filename || `regulation-${Date.now()}`;
        const record = { id, saved_at: new Date().toISOString(), data: latestDecodeResult };
        const next = [record, ...existing.filter(x => x.id !== id)].slice(0, 20);
        localStorage.setItem(key, JSON.stringify(next));
        saveScanToLocalHistory(latestDecodeResult);
        if (showMessage) showToast("Changes saved in this browser.");
        return true;
    } catch (error) {
        if (showMessage) showToast("Could not save locally. The browser may be out of storage space.", true);
        return false;
    }
}

function saveAsRegulation() {
    if (!latestDecodeResult) { showToast("No regulation is open to save.", true); return; }
    collectEditedFields();
    const suggested = (latestDecodeResult.filename || "regulation").replace(/\.pdf$/i, "");
    const name = window.prompt("Save regulation as:", suggested);
    if (name === null) return;
    const safeName = name.trim().replace(/[<>:"/\\|?*]+/g, "-") || "regulation";
    downloadBlob(JSON.stringify(latestDecodeResult, null, 2), `${safeName}.json`, "application/json");
    showToast(`Saved as ${safeName}.json`);
}

function downloadEditedRegulation(type = "json") {
    if (!latestDecodeResult) { showToast("No regulation is open to download.", true); return; }
    collectEditedFields();
    const requirements = arrayValue(latestDecodeResult?.results?.requirements);
    const baseName = (latestDecodeResult.filename || "regulation").replace(/\.pdf$/i, "");
    if (type === "csv") {
        const rows = [["Reference", "Title", "Source requirement", "Summary", "Implementation action", "Policies", "Documents", "Evidence"]];
        requirements.forEach(r => rows.push([r.source_reference || "", r.source_title || "", r.source_text || "", r.source_summary || "", r.todo?.name || "", arrayValue(r.policies).map(x => x.name || "").join("; "), arrayValue(r.documents).map(x => x.name || "").join("; "), arrayValue(r.evidence).map(x => x.name || "").join("; ")]));
        const csv = rows.map(row => row.map(v => `"${String(v ?? "").replace(/"/g, '""')}"`).join(",")).join("\r\n");
        downloadBlob(csv, `${baseName}_regulation.csv`, "text/csv;charset=utf-8");
    } else {
        downloadBlob(JSON.stringify(latestDecodeResult, null, 2), `${baseName}_regulation.json`, "application/json");
    }
}

function downloadBlob(content, filename, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url; link.download = filename;
    document.body.appendChild(link); link.click(); link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function removeCurrentDocument() {
    if (!latestDecodeResult && !selectedPdf) { showToast("There is no document to remove.", true); return; }
    if (!window.confirm("Remove this document from the current workspace? Saved history will remain.")) return;
    decodeAnother();
    showToast("Document removed from the current workspace.");
}



function saveScanToLocalHistory(data) {
    try {
        const key = "sahlComplianceDecoderHistory";
        const existing = JSON.parse(localStorage.getItem(key) || "[]");
        const metadata = data?.results?.metadata || {};
        const record = {
            document_id: data?.document_id || metadata?.document_id || "",
            filename: data?.filename || metadata?.filename || "Compliance document",
            framework_name: metadata?.framework_name || metadata?.document_title || "",
            requirement_count: data?.requirement_count || metadata?.requirement_count || 0,
            scanned_at: new Date().toISOString(),
            data: data
        };
        if (record.document_id) {
            const filtered = existing.filter(item => item.document_id !== record.document_id);
            filtered.unshift(record);
            localStorage.setItem(key, JSON.stringify(filtered.slice(0, 10)));
            renderScanHistory();
        }
    } catch (error) {
        console.warn("Could not save local scan history.", error);
    }
}

/* =========================================================
   DECODE ANOTHER
   ========================================================= */

function decodeAnother() {

    latestDecodeResult = null;
    selectedPdf = null;

    fileInput.value = "";

    selectedFile.innerHTML = "";
    selectedFile.classList.add("hidden");

    decodeButton.disabled = true;

    companyInput.value = "";
    emailInput.value = "";

    currentProgress = 8;

    setProgress(8);

    showView(uploadView);
}


/* =========================================================
   SCAN HISTORY UI
   ========================================================= */

function ensureHistoryPanel() {
    if (document.getElementById("scanHistoryPanel")) return;
    const pageContainer = uploadView.querySelector(".page-container");
    if (!pageContainer) return;
    const panel = document.createElement("section");
    panel.id = "scanHistoryPanel";
    panel.className = "scan-history-panel";
    panel.innerHTML = `<div class="history-heading"><div><span class="history-eyebrow">YOUR WORKSPACE</span><h2>Recent scans</h2><p>Previously decoded regulations saved in this browser.</p></div><button class="secondary-button" type="button" onclick="clearScanHistory()">Clear history</button></div><div id="scanHistoryList" class="scan-history-list"></div>`;
    pageContainer.appendChild(panel);
}

function renderScanHistory() {
    ensureHistoryPanel();
    const list = document.getElementById("scanHistoryList");
    if (!list) return;
    let records = [];
    try { records = JSON.parse(localStorage.getItem("sahlComplianceDecoderHistory") || "[]"); } catch {}
    if (!records.length) {
        list.innerHTML = `<div class="history-empty"><strong>No scan history yet</strong><span>Your decoded regulations will appear here after the first successful scan.</span></div>`;
        return;
    }
    list.innerHTML = records.map((record, index) => `<article class="history-card"><div class="history-file-icon">PDF</div><div class="history-info"><strong>${escapeHtml(record.framework_name || record.filename || "Compliance document")}</strong><span>${escapeHtml(record.filename || "Compliance document")}</span><small>${Number(record.requirement_count || 0)} requirements · ${escapeHtml(new Date(record.scanned_at).toLocaleString())}</small></div><div class="history-actions">${record.data ? `<button class="secondary-button" type="button" onclick="openHistoryScan(${index})">Open</button>` : ""}<button class="secondary-button" type="button" onclick="removeHistoryScan(${index})">Remove</button></div></article>`).join("");
}

function openHistoryScan(index) {
    try {
        const records = JSON.parse(localStorage.getItem("sahlComplianceDecoderHistory") || "[]");
        const record = records[index];
        if (!record?.data) { showToast("This history item has summary details only. Decode it again to reopen the full regulation.", true); return; }
        latestDecodeResult = record.data;
        renderResults(latestDecodeResult);
        showView(resultsView);
    } catch { showToast("Could not open this history item.", true); }
}

function removeHistoryScan(index) {
    const records = JSON.parse(localStorage.getItem("sahlComplianceDecoderHistory") || "[]");
    records.splice(index, 1);
    localStorage.setItem("sahlComplianceDecoderHistory", JSON.stringify(records));
    renderScanHistory();
    showToast("History item removed.");
}

function clearScanHistory() {
    if (!window.confirm("Clear all recent scan history from this browser?")) return;
    localStorage.removeItem("sahlComplianceDecoderHistory");
    renderScanHistory();
    showToast("Scan history cleared.");
}

/* =========================================================
   INITIAL STATE
   ========================================================= */

showView(uploadView);
renderScanHistory();
