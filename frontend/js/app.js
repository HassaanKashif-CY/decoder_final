const API_BASE = "http://127.0.0.1:8000";

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
    `;

    selectedFile.classList.remove("hidden");

    decodeButton.disabled = false;
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

                    <button
                        class="secondary-button"
                        type="button"
                        onclick="downloadOutput('json')"
                    >
                        JSON
                    </button>


                    <button
                        class="secondary-button"
                        type="button"
                        onclick="downloadOutput('csv')"
                    >
                        CSV
                    </button>


                    ${renderSendButton(data)}


                    <button
                        class="secondary-button"
                        type="button"
                        onclick="decodeAnother()"
                    >
                        Decode another
                    </button>

                </div>

            </div>


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
}


function renderSendButton(data) {

    const emailStatus =
        data?.email_status || "";

    if (emailStatus === "sent") {

        return `
            <button
                class="send-button sent"
                type="button"
                disabled
            >
                ✓ Sent to Sahl
            </button>
        `;
    }

    if (emailStatus === "failed") {

        return `
            <button
                class="send-button failed"
                type="button"
                onclick="handleSendToSahl()"
            >
                Retry sending to Sahl
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

                    <span class="requirement-title">
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


                <div class="source-box">
                    ${escapeHtml(sourceText)}
                </div>


                ${
                    pageStart
                    ? `
                        <div class="source-meta">
                            Source pages:
                            ${escapeHtml(pageStart)}${
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

                            <p>
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

                    <p>
                        ${
                            escapeHtml(
                                todo?.name ||
                                "Implementation action"
                            )
                        }
                    </p>

                    ${
                        todo?.description
                        ? `
                            <p style="margin-top:5px;">
                                ${escapeHtml(
                                    todo.description
                                )}
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

                </div>

            </div>

        </article>
    `;
}


function renderRecommendationCard(
    title,
    items
) {

    if (!items.length) {

        return `
            <div class="recommendation-card">

                <h4>
                    ${escapeHtml(title)}
                </h4>

                <div class="recommendation-item">

                    <strong>
                        No recommendations
                    </strong>

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
    formData.append("company_name", companyInput?.value?.trim() || "");
    formData.append("user_email", emailInput?.value?.trim() || "");

    try {
        const response = await fetch(
            `${API_BASE}/api/send-to-sahl/${encodeURIComponent(latestDecodeResult.document_id)}`,
            { method: "POST", body: formData }
        );
        let data = {};
        try { data = await response.json(); } catch { /* non-JSON response */ }
        if (!response.ok) {
            throw new Error(data?.detail || "Email submission failed.");
        }

        latestDecodeResult.email_status = "sent";
        latestDecodeResult.email_recipients = (data.recipients || []).join(", ");
        renderResults(latestDecodeResult);
        showToast("Successfully sent the decoded files to Sahl.");
    } catch (error) {
        latestDecodeResult.email_status = "failed";
        renderResults(latestDecodeResult);
        showToast(error?.message || "Could not send the files to Sahl. Check SMTP settings and retry.", true);
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
   INITIAL STATE
   ========================================================= */

showView(uploadView);