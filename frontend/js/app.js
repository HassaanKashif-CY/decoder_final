"use strict";

/* =========================================================
   SAHL COMPLIANCE DECODER - FRONT END
   ========================================================= */

const API_BASE = "";
const HISTORY_KEY = "sahlComplianceDecoderHistory";
const MAX_HISTORY = 10;
const MAX_FILE_SIZE = 100 * 1024 * 1024;

const ICON_CHEVRON =
    '<svg viewBox="0 0 20 20" width="16" height="16" aria-hidden="true">' +
    '<path d="M5 7.5l5 5 5-5" fill="none" stroke="currentColor" ' +
    'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';


/* =========================================================
   DOM
   ========================================================= */

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

const backButton = document.getElementById("backButton");
const topbarSub = document.getElementById("topbarSub");
const railButtons = Array.from(document.querySelectorAll("[data-nav]"));

const historySection = document.getElementById("historySection");
const historyList = document.getElementById("historyList");
const clearHistoryButton = document.getElementById("clearHistoryButton");


/* =========================================================
   STATE
   ========================================================= */

let selectedPdf = null;
let progressTimer = null;
let currentProgress = 8;
let latestDecodeResult = null;
let currentSubmission = { company: "", email: "" };
let currentViewId = "uploadView";
let railMode = "decode";
let isBusy = false;
let complianceEditMode = false;


/* =========================================================
   BASIC HELPERS
   ========================================================= */

function text(value) {
    return value === null || value === undefined
        ? ""
        : String(value).trim();
}

function arrayValue(value) {
    return Array.isArray(value) ? value : [];
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

function formatWhen(iso) {
    const date = new Date(iso);

    if (Number.isNaN(date.getTime())) return "";

    const minutes = Math.floor((Date.now() - date.getTime()) / 60000);

    if (minutes < 1) return "Just now";
    if (minutes < 60) return `${minutes} min ago`;

    const time = date.toLocaleTimeString([], {
        hour: "numeric",
        minute: "2-digit"
    });

    const now = new Date();
    const yesterday = new Date(now.getTime() - 86400000);

    if (date.toDateString() === now.toDateString()) return `Today, ${time}`;
    if (date.toDateString() === yesterday.toDateString()) {
        return `Yesterday, ${time}`;
    }

    return `${date.toLocaleDateString([], {
        day: "numeric",
        month: "short",
        year: "numeric"
    })}, ${time}`;
}

function showToast(message, isError = false) {
    toast.textContent = message;
    toast.classList.toggle("error", isError);
    toast.classList.add("show");

    window.clearTimeout(showToast.timer);

    showToast.timer = window.setTimeout(() => {
        toast.classList.remove("show");
    }, 3800);
}


/* =========================================================
   VIEWS + CHROME (rail, header)
   ========================================================= */

function showView(view) {
    uploadView.classList.add("hidden");
    processingView.classList.add("hidden");
    resultsView.classList.add("hidden");

    view.classList.remove("hidden");
    currentViewId = view.id;

    updateChrome();

    window.scrollTo({ top: 0, behavior: "instant" });
}

function updateChrome() {
    const onResults = currentViewId === "resultsView";
    const onProcessing = currentViewId === "processingView";

    backButton.classList.toggle("hidden", !onResults);

    topbarSub.textContent = onResults
        ? "Decoder results"
        : onProcessing
            ? "Decoding"
            : "Decoder";

    railButtons.forEach(button => {
        const target = button.dataset.nav;

        if (target === "results") {
            button.classList.toggle("hidden", !latestDecodeResult);
        }

        const active = onResults
            ? target === "results"
            : target === railMode;

        button.classList.toggle("active", active);
    });
}

railButtons.forEach(button => {
    button.addEventListener("click", () => {
        if (isBusy) {
            showToast("Decoding is in progress. Please wait until it finishes.");
            return;
        }

        const target = button.dataset.nav;

        if (target === "results") {
            if (latestDecodeResult) showView(resultsView);
            return;
        }

        railMode = target;
        showView(uploadView);

        if (target === "history") {
            historySection?.scrollIntoView?.({
                behavior: "smooth",
                block: "start"
            });
        }
    });
});

backButton.addEventListener("click", () => {
    if (isBusy) return;

    railMode = "decode";
    showView(uploadView);
});

window.addEventListener("beforeunload", event => {
    if (isBusy) {
        event.preventDefault();
        event.returnValue = "";
    }
});


/* =========================================================
   FILE SELECTION
   ========================================================= */

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

    return true;
}

function setSelectedFile(file) {
    if (!validateFile(file)) {
        clearSelectedPdf(false);
        return;
    }

    selectedPdf = file;

    selectedFile.innerHTML = `
        <div class="selected-file-left">
            <div class="file-badge">PDF</div>

            <div>
                <div class="selected-file-name">${escapeHtml(file.name)}</div>
                <div class="selected-file-size">${formatBytes(file.size)}</div>
            </div>
        </div>

        <div class="selected-file-actions">
            <button type="button" class="secondary-button" id="replacePdfButton">Replace PDF</button>
            <button type="button" class="secondary-button" id="removePdfButton">Remove PDF</button>
        </div>
    `;

    selectedFile.classList.remove("hidden");
    decodeButton.disabled = false;

    document
        .getElementById("replacePdfButton")
        ?.addEventListener("click", () => fileInput.click());

    document
        .getElementById("removePdfButton")
        ?.addEventListener("click", () => clearSelectedPdf(true));
}

function clearSelectedPdf(announce = true) {
    selectedPdf = null;
    fileInput.value = "";
    selectedFile.innerHTML = "";
    selectedFile.classList.add("hidden");
    decodeButton.disabled = true;

    if (announce) showToast("PDF removed. Choose a PDF to continue.");
}

fileInput.addEventListener("change", () => {
    const file = fileInput.files?.[0];
    if (file) setSelectedFile(file);
});

dropZone.addEventListener("dragover", event => {
    event.preventDefault();
    dropZone.classList.add("dragover");
});

dropZone.addEventListener("dragleave", () => {
    dropZone.classList.remove("dragover");
});

dropZone.addEventListener("drop", event => {
    event.preventDefault();
    dropZone.classList.remove("dragover");

    const file = event.dataTransfer.files?.[0];
    if (file) setSelectedFile(file);
});


/* =========================================================
   PROCESSING PROGRESS
   ========================================================= */

const processingStages = [
    {
        max: 20,
        title: "Reading PDF",
        text: "Reading the uploaded document and extracting its content.",
        step: 1
    },
    {
        max: 42,
        title: "Understanding document structure",
        text: "Detecting chapters, sections, hierarchy and terminology used by the document.",
        step: 2
    },
    {
        max: 67,
        title: "Identifying requirements",
        text: "Finding the actual actionable compliance requirements in the document.",
        step: 3
    },
    {
        max: 84,
        title: "Building implementation guidance",
        text: "Preparing practical actions, policies, documents, evidence and automation tests.",
        step: 4
    },
    {
        max: 94,
        title: "Preparing Sahl-ready output",
        text: "Finalizing the compliance breakdown and preparing JSON and CSV outputs.",
        step: 5
    }
];

function updateProcessingStage(progress) {
    const stage =
        processingStages.find(item => progress <= item.max) ||
        processingStages[processingStages.length - 1];

    processingStage.textContent = stage.title;
    processingText.textContent = stage.text;

    for (let i = 1; i <= 5; i++) {
        const step = document.getElementById(`step${i}`);

        if (!step) continue;

        step.classList.remove("active", "completed");

        if (i < stage.step) step.classList.add("completed");
        if (i === stage.step) step.classList.add("active");
    }
}

function setProgress(value) {
    currentProgress = Math.max(0, Math.min(100, value));

    progressBar.style.width = `${currentProgress}%`;
    progressPercent.textContent = `${Math.round(currentProgress)}%`;

    updateProcessingStage(currentProgress);
}

function startFakeProgress() {
    currentProgress = 8;
    setProgress(currentProgress);

    window.clearInterval(progressTimer);

    progressTimer = window.setInterval(() => {
        if (currentProgress >= 92) return;

        let increment = 0.18;

        if (currentProgress < 25) increment = 1.0;
        else if (currentProgress < 50) increment = 0.65;
        else if (currentProgress < 72) increment = 0.4;

        setProgress(currentProgress + increment);
    }, 900);
}

function finishProgress() {
    window.clearInterval(progressTimer);

    setProgress(100);

    for (let i = 1; i <= 5; i++) {
        const step = document.getElementById(`step${i}`);

        if (step) {
            step.classList.remove("active");
            step.classList.add("completed");
        }
    }

    processingStage.textContent = "Decoding completed";
    processingText.textContent = "Your compliance workspace is ready.";
}


/* =========================================================
   START DECODING
   ========================================================= */

function clearUploadForm() {
    clearSelectedPdf(false);
    companyInput.value = "";
    emailInput.value = "";
}

decodeButton.addEventListener("click", async () => {
    if (!selectedPdf) {
        showToast("Please select a PDF first.", true);
        return;
    }

    const companyName = companyInput.value.trim();
    const userEmail = emailInput.value.trim();

    if (!companyName) {
        showToast("Please enter your company name.", true);
        companyInput.focus();
        return;
    }

    if (!userEmail || !userEmail.includes("@")) {
        showToast("Please enter a valid business email.", true);
        emailInput.focus();
        return;
    }

    const formData = new FormData();
    formData.append("file", selectedPdf);
    formData.append("company_name", companyName);
    formData.append("user_email", userEmail);

    processingFile.textContent = selectedPdf.name;

    isBusy = true;
    decodeButton.disabled = true;

    showView(processingView);
    startFakeProgress();

    try {
        const response = await fetch(`${API_BASE}/api/decode`, {
            method: "POST",
            body: formData
        });

        let data = null;

        try {
            data = await response.json();
        } catch {
            data = null;
        }

        if (!response.ok) {
            throw new Error(
                data?.detail ||
                "The compliance document could not be decoded."
            );
        }

        latestDecodeResult = data;
        currentSubmission = { company: companyName, email: userEmail };

        addScanToHistory(data);
        finishProgress();

        await new Promise(resolve => setTimeout(resolve, 700));

        isBusy = false;
        clearUploadForm();

        renderResults(data);
        showView(resultsView);

        // Automatically notify Sahl; the same action stays available
        // as a button for repeat submissions.
        await handleSendToSahl({ auto: true });

    } catch (error) {
        window.clearInterval(progressTimer);

        isBusy = false;
        decodeButton.disabled = !selectedPdf;

        railMode = "decode";
        showView(uploadView);

        showToast(
            error?.message || "Something went wrong while decoding the PDF.",
            true
        );
    } finally {
        isBusy = false;
    }
});


/* =========================================================
   HIERARCHY (chapter > subchapter > control)
   Works with whatever the backend provides:
     requirement.chapter / requirement.subchapter  ({reference,title,objective})
     requirement.hierarchy_path                    (["1 Governance", "1-1 Roles"])
     results.structure                             (flat node list)
   and falls back to the shape of the source reference ("1-1-1").
   ========================================================= */

function parseLabel(label) {
    const value = text(label);

    const match =
        /^([A-Za-z]{0,3}\d+(?:[-.][A-Za-z0-9]+)*)[\s:.\-\u2013\u2014]+(.+)$/.exec(value);

    if (match) {
        return { reference: match[1], title: match[2].trim() };
    }

    return { reference: "", title: value };
}

function toNode(value) {
    if (!value) return null;

    if (typeof value === "string") {
        return { ...parseLabel(value), objective: "" };
    }

    if (typeof value === "object") {
        return {
            reference: text(value.reference),
            title: text(value.title),
            objective: text(value.objective)
        };
    }

    return null;
}

function normRef(reference) {
    return text(reference).toLowerCase().replace(/[.\s]+/g, "-");
}

function deriveFromReference(reference) {
    const ref = text(reference);

    let match =
        /^([A-Za-z]{0,3}\d+)([-.])([A-Za-z0-9]+)(?:[-.][A-Za-z0-9]+)+/.exec(ref);

    if (match) {
        return {
            chapterRef: match[1],
            sectionRef: match[1] + match[2] + match[3]
        };
    }

    match = /^([A-Za-z]{1,3})([-.])(\d+)(?:[-.][A-Za-z0-9]+)+/.exec(ref);

    if (match) {
        return {
            chapterRef: match[1],
            sectionRef: match[1] + match[2] + match[3]
        };
    }

    match = /^([A-Za-z]{0,3}\d+)[-.][A-Za-z0-9]+$/.exec(ref);

    if (match) {
        return { chapterRef: match[1], sectionRef: "" };
    }

    return null;
}

function buildStructureIndex(structure) {
    const index = new Map();

    arrayValue(structure).forEach(node => {
        const reference = normRef(node?.reference);

        if (reference && !index.has(reference)) {
            index.set(reference, node);
        }
    });

    return index;
}

function objectiveFromStructure(node) {
    if (!node) return "";

    if (typeof node.objective === "string" && node.objective.trim()) {
        return node.objective.trim();
    }

    const lines = text(node.text).split("\n");

    if (lines.length > 1 && lines[0].length <= 200) {
        return lines.slice(1).join("\n").trim();
    }

    return "";
}

function fillFromStructure(node, ctx) {
    if (!node || !node.reference) return node;

    const entry = ctx.byRef.get(normRef(node.reference));

    if (!entry) return node;

    return {
        ...node,
        title: node.title || text(entry.title),
        objective: node.objective || objectiveFromStructure(entry)
    };
}

function resolveHierarchy(requirement, ctx) {
    let chapter = toNode(requirement?.chapter);
    let section = toNode(requirement?.subchapter);

    const path = arrayValue(requirement?.hierarchy_path);

    if (!chapter && path.length) chapter = toNode(path[0]);
    if (!section && path.length > 1) section = toNode(path[path.length - 1]);

    if (!chapter) {
        const derived = deriveFromReference(requirement?.source_reference);

        if (derived) {
            chapter = {
                reference: derived.chapterRef,
                title: "",
                objective: ""
            };

            if (derived.sectionRef) {
                section = {
                    reference: derived.sectionRef,
                    title: "",
                    objective: ""
                };
            }
        }
    }

    if (!chapter) {
        return {
            chapter: {
                reference: "",
                title: ctx.documentTitle || "Requirements",
                objective: "",
                flat: true
            },
            section: null
        };
    }

    return {
        chapter: fillFromStructure(chapter, ctx),
        section: section ? fillFromStructure(section, ctx) : null
    };
}

function nodeKey(node) {
    return node.reference
        ? `r:${normRef(node.reference)}`
        : `t:${node.title.toLowerCase()}`;
}

function buildTree(requirements, ctx) {
    const chapters = new Map();

    requirements.forEach((requirement, index) => {
        const resolved = resolveHierarchy(requirement, ctx);

        const chapterKey = resolved.chapter.flat
            ? "__flat__"
            : nodeKey(resolved.chapter);

        if (!chapters.has(chapterKey)) {
            chapters.set(chapterKey, {
                ...resolved.chapter,
                sections: new Map(),
                count: 0
            });
        }

        const chapter = chapters.get(chapterKey);

        if (!chapter.title && resolved.chapter.title) {
            chapter.title = resolved.chapter.title;
        }

        const sectionKey = resolved.section
            ? nodeKey(resolved.section)
            : "__direct__";

        if (!chapter.sections.has(sectionKey)) {
            chapter.sections.set(sectionKey, {
                reference: resolved.section?.reference || "",
                title: resolved.section?.title || "",
                objective: "",
                direct: !resolved.section,
                items: []
            });
        }

        const section = chapter.sections.get(sectionKey);

        if (resolved.section) {
            if (!section.title && resolved.section.title) {
                section.title = resolved.section.title;
            }

            if (!section.objective) {
                section.objective =
                    text(requirement?.objective) ||
                    resolved.section.objective ||
                    "";
            }
        }

        section.items.push({ requirement, index });
        chapter.count += 1;
    });

    return Array.from(chapters.values()).map(chapter => ({
        ...chapter,
        sections: Array.from(chapter.sections.values())
    }));
}

function hierarchyForRequirement(requirement, ctx) {
    const resolved = resolveHierarchy(requirement, ctx);

    const label = node =>
        node
            ? [node.reference, node.title].filter(Boolean).join(" ")
            : "";

    return {
        chapter: resolved.chapter.flat ? "" : label(resolved.chapter),
        section: label(resolved.section)
    };
}

function contextFor(data) {
    const results = data?.results || {};
    const metadata = results.metadata || {};

    return {
        documentTitle:
            text(metadata.document_title) ||
            text(metadata.framework_name) ||
            text(data?.filename).replace(/\.pdf$/i, ""),
        byRef: buildStructureIndex(results.structure)
    };
}


/* =========================================================
   RESULTS RENDERING
   ========================================================= */

function renderResults(data) {
    const results = data?.results || {};
    const metadata = results.metadata || {};
    const requirements = arrayValue(results.requirements);

    const documentName =
        data?.filename || metadata.filename || "Compliance document";

    const pageCount = data?.page_count || metadata.page_count || 0;

    const requirementCount =
        data?.requirement_count ||
        metadata.requirement_count ||
        requirements.length;

    const documentTitle =
        metadata.document_title || metadata.framework_name || documentName;

    const ctx = contextFor(data);
    const tree = buildTree(requirements, ctx);

    const realChapters = tree.filter(chapter => !chapter.flat).length;
    const sectionCount = tree.reduce(
        (sum, chapter) =>
            sum + chapter.sections.filter(section => !section.direct).length,
        0
    );

    const structureNote = realChapters
        ? `${realChapters} chapter${realChapters === 1 ? "" : "s"}` +
          (sectionCount
              ? ` · ${sectionCount} section${sectionCount === 1 ? "" : "s"}`
              : "") +
          ` · ${requirementCount} requirements`
        : `${requirementCount} requirements`;

    const overview = `
        <section class="regulation-overview">
            <h2>Regulation overview</h2>

            <p class="overview-summary">${escapeHtml(
                metadata.regulation_summary ||
                "A regulation summary was not returned for this document. Review the source PDF for scope and intent."
            )}</p>

            <div class="overview-details">
                ${metadata.document_type ? `<p><strong>Document type</strong><span>${escapeHtml(metadata.document_type)}</span></p>` : ""}
                ${metadata.framework_name ? `<p><strong>Framework</strong><span>${escapeHtml(metadata.framework_name)}</span></p>` : ""}
                ${metadata.version ? `<p><strong>Version</strong><span>${escapeHtml(metadata.version)}</span></p>` : ""}
                ${metadata.jurisdiction ? `<p><strong>Jurisdiction</strong><span>${escapeHtml(metadata.jurisdiction)}</span></p>` : ""}
                ${metadata.applicability_conditions ? `<p><strong>Applicability</strong><span>${escapeHtml(metadata.applicability_conditions)}</span></p>` : ""}
                ${arrayValue(metadata.applicable_industries).length ? `<p><strong>Industries</strong><span>${arrayValue(metadata.applicable_industries).map(escapeHtml).join(", ")}</span></p>` : ""}
            </div>
        </section>
    `;

    resultsRoot.innerHTML = `
        <div class="results-container">

            <div>
                <div class="results-eyebrow">MY COMPLIANCES / DECODER</div>
                <h2 class="results-title">${escapeHtml(documentTitle)}</h2>
                <p class="results-subtitle">${escapeHtml(documentName)}</p>
            </div>

            <div class="results-toolbar">
                <div class="toolbar-group">
                    <button class="secondary-button accent" type="button" id="toggleEditButton" data-action="toggle-edit">Edit compliance</button>
                    <button class="secondary-button" type="button" data-action="save">Save changes</button>
                    <button class="secondary-button" type="button" data-action="save-as">Save as…</button>
                </div>

                <span class="toolbar-divider"></span>

                <div class="toolbar-group">
                    <button class="secondary-button" type="button" data-action="download-pdf">Original PDF</button>
                    <button class="secondary-button" type="button" data-action="download-json">Download JSON</button>
                    <button class="secondary-button" type="button" data-action="download-csv">Download CSV</button>
                </div>

                <span class="toolbar-spacer"></span>

                <div class="toolbar-group">
                    <button class="secondary-button danger-text" type="button" data-action="remove">Remove document</button>
                    <button class="secondary-button" type="button" data-action="decode-another">Decode another</button>
                    <button class="send-button" type="button" data-action="send">Add regulation to Sahl</button>
                </div>
            </div>

            ${overview}

            <div class="summary-grid">
                <div class="summary-card">
                    <div class="summary-label">Document</div>
                    <div class="summary-value small">${escapeHtml(documentName)}</div>
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
                    <div class="summary-value ok">Decoded</div>
                </div>
            </div>

            <div class="structure-bar">
                <div>
                    <h2>Compliance structure</h2>
                    <p>${escapeHtml(structureNote)}</p>
                </div>

                <div class="structure-tools">
                    <input id="requirementSearch" class="search-input" type="search" placeholder="Search requirements" aria-label="Search requirements">
                    <button class="secondary-button" type="button" data-action="expand-all">Expand all</button>
                    <button class="secondary-button" type="button" data-action="collapse-all">Collapse all</button>
                </div>
            </div>

            <div id="structureRoot">
                ${requirements.length ? renderTree(tree) : renderEmptyRequirements()}
                <div id="filterEmpty" class="filter-empty hidden">No requirements match your search.</div>
            </div>

        </div>
    `;

    setComplianceEditMode(false);
    updateChrome();
}

function renderTree(tree) {
    let sectionOpenUsed = false;
    let controlOpenUsed = false;
    let chapterNumber = 0;

    return tree.map(chapter => {
        if (!chapter.flat) chapterNumber += 1;

        const badge = chapter.flat
            ? "Requirements"
            : `Chapter ${escapeHtml(chapter.reference || chapterNumber)}`;

        const title =
            chapter.title ||
            (chapter.flat ? "Requirements" : `Controls in chapter ${chapter.reference || chapterNumber}`);

        const body = chapter.sections.map(section => {
            const controls = section.items.map(item => {
                const open = !controlOpenUsed;
                controlOpenUsed = true;
                return renderControl(item.requirement, item.index, open);
            }).join("");

            if (section.direct) {
                return `<div class="control-list flat">${controls}</div>`;
            }

            const openSection = !sectionOpenUsed;
            sectionOpenUsed = true;

            const sectionTitle =
                section.title || `Section ${section.reference}`;

            return `
                <div class="section-card ${openSection ? "open" : ""}">
                    <div class="section-head" role="button" tabindex="0" aria-expanded="${openSection}" data-action="toggle-section">
                        ${section.reference ? `<span class="section-ref">${escapeHtml(section.reference)}</span>` : ""}
                        <h3 class="section-title">${escapeHtml(sectionTitle)}</h3>
                        <span class="section-count">${section.items.length} ${section.items.length === 1 ? "control" : "controls"}</span>
                        <span class="chevron">${ICON_CHEVRON}</span>
                    </div>

                    <div class="section-body">
                        ${section.objective ? `<p class="section-objective">${escapeHtml(section.objective)}</p>` : ""}
                        <div class="control-list">${controls}</div>
                    </div>
                </div>
            `;
        }).join("");

        return `
            <section class="chapter-card">
                <div class="chapter-head">
                    <span class="chapter-badge">${badge}</span>
                    <h2 class="chapter-title">${escapeHtml(title)}</h2>
                    <span class="chapter-count">${chapter.count} ${chapter.count === 1 ? "requirement" : "requirements"}</span>
                </div>

                ${body}
            </section>
        `;
    }).join("");
}

function renderControl(requirement, index, open) {
    const reference = text(requirement?.source_reference);
    const todo = requirement?.todo || {};

    const name =
        text(todo.name) ||
        text(requirement?.source_title) ||
        reference ||
        `Requirement ${index + 1}`;

    const sourceTitle = text(requirement?.source_title);
    const sourceText =
        text(requirement?.source_text) ||
        "Source requirement text unavailable.";

    const summary = text(requirement?.source_summary);

    const pageStart = requirement?.page_start;
    const pageEnd = requirement?.page_end;

    const pages = pageStart
        ? `Source pages: ${escapeHtml(pageStart)}${
              pageEnd && pageEnd !== pageStart ? `–${escapeHtml(pageEnd)}` : ""
          }`
        : "";

    const showSourceTitle =
        sourceTitle &&
        sourceTitle !== name &&
        sourceTitle !== reference;

    const items = [
        ...arrayValue(requirement?.policies).map(item => ({ item, type: "Policy" })),
        ...arrayValue(requirement?.documents).map(item => ({ item, type: "Document" })),
        ...arrayValue(requirement?.evidence).map(item => ({ item, type: "Evidence" })),
        ...arrayValue(requirement?.automation_tests).map(item => ({ item, type: "Automation test" }))
    ];

    const hasTests = arrayValue(requirement?.automation_tests).length > 0;

    const actionList = items.length
        ? items.map(({ item, type }) => `
            <div class="action-item">
                <div class="action-item-head" role="button" tabindex="0" aria-expanded="false" data-action="toggle-item">
                    <span class="chevron">${ICON_CHEVRON}</span>
                    <span class="action-name">${escapeHtml(item?.name || "")}</span>
                    <span class="action-type">(${escapeHtml(type)})</span>
                </div>
                ${item?.description ? `<div class="action-item-body">${escapeHtml(item.description)}</div>` : ""}
            </div>
        `).join("")
        : `<div class="action-empty">No recommendations were generated for this requirement.</div>`;

    return `
        <article class="control-card ${open ? "open" : ""}" data-requirement-index="${index}">

            <div class="control-header" role="button" tabindex="0" aria-expanded="${open}" data-action="toggle-control">
                <div class="control-title">
                    ${reference ? `<span class="control-ref">${escapeHtml(reference)}:</span> ` : ""}<span class="editable-field" contenteditable="false" spellcheck="true" data-edit-field="todo.name">${escapeHtml(name)}</span>
                </div>
                <span class="chevron">${ICON_CHEVRON}</span>
            </div>

            <div class="control-body">

                <div class="field-label">Source requirement</div>

                ${showSourceTitle ? `<div class="source-title-line editable-field" contenteditable="false" spellcheck="true" data-edit-field="source_title">${escapeHtml(sourceTitle)}</div>` : ""}

                <div class="source-text editable-field" contenteditable="false" spellcheck="true" data-edit-field="source_text">${escapeHtml(sourceText)}</div>

                ${pages ? `<div class="source-meta">${pages}</div>` : ""}

                ${summary ? `
                    <div class="note-box">
                        <h4>Requirement summary</h4>
                        <p class="editable-field" contenteditable="false" spellcheck="true" data-edit-field="source_summary">${escapeHtml(summary)}</p>
                    </div>
                ` : ""}

                ${todo.description ? `
                    <div class="note-box">
                        <h4>Implementation action</h4>
                        <p class="editable-field" contenteditable="false" spellcheck="true" data-edit-field="todo.description">${escapeHtml(todo.description)}</p>
                    </div>
                ` : ""}

                <div class="action-list">
                    <div class="action-list-title">Action-List</div>
                    ${actionList}
                    ${items.length && !hasTests ? `<div class="action-empty">No suitable automation test was identified. Manual verification may be needed.</div>` : ""}
                </div>

            </div>
        </article>
    `;
}

function renderEmptyRequirements() {
    return `<div class="empty-state">No requirements were returned by the decoder.</div>`;
}


/* =========================================================
   RESULTS INTERACTIONS (delegated)
   ========================================================= */

function setExpanded(element, expanded) {
    element
        .querySelector(":scope > [aria-expanded]")
        ?.setAttribute("aria-expanded", String(expanded));
}

function toggleCard(trigger, selector) {
    const card = trigger.closest(selector);

    if (!card) return;

    const open = card.classList.toggle("open");
    trigger.setAttribute("aria-expanded", String(open));
}

function onResultsClick(event) {
    const trigger = event.target.closest("[data-action]");

    if (!trigger || !resultsRoot.contains(trigger)) return;

    const action = trigger.dataset.action;

    switch (action) {
        case "toggle-section":
            if (complianceEditMode && event.target.closest("[data-edit-field]")) return;
            toggleCard(trigger, ".section-card");
            break;

        case "toggle-control":
            if (complianceEditMode && event.target.closest("[data-edit-field]")) return;
            toggleCard(trigger, ".control-card");
            break;

        case "toggle-item":
            toggleCard(trigger, ".action-item");
            break;

        case "expand-all":
            setAllOpen(true);
            break;

        case "collapse-all":
            setAllOpen(false);
            break;

        case "toggle-edit":
            toggleComplianceEditing();
            break;

        case "save":
            saveEditedRegulation(true);
            break;

        case "save-as":
            saveAsRegulation();
            break;

        case "download-pdf":
            downloadOutput("pdf");
            break;

        case "download-json":
            downloadEditedRegulation("json");
            break;

        case "download-csv":
            downloadEditedRegulation("csv");
            break;

        case "remove":
            removeCurrentDocument();
            break;

        case "decode-another":
            decodeAnother();
            break;

        case "send":
            handleSendToSahl();
            break;

        default:
            break;
    }
}

function onResultsKeydown(event) {
    if (event.key !== "Enter" && event.key !== " ") return;

    const target = event.target;

    if (!target.matches?.('[data-action][role="button"]')) return;

    event.preventDefault();
    target.click();
}

function setAllOpen(open) {
    resultsRoot
        .querySelectorAll(".section-card, .control-card, .action-item")
        .forEach(card => {
            card.classList.toggle("open", open);

            card
                .querySelector(":scope > [aria-expanded]")
                ?.setAttribute("aria-expanded", String(open));
        });
}

function applyFilter(query) {
    const needle = text(query).toLowerCase();
    const root = document.getElementById("structureRoot");

    if (!root) return;

    let visible = 0;

    root.querySelectorAll(".control-card").forEach(card => {
        const match =
            !needle || card.textContent.toLowerCase().includes(needle);

        card.classList.toggle("is-filtered", !match);

        if (match) visible += 1;
    });

    root.querySelectorAll(".section-card").forEach(section => {
        const has = !!section.querySelector(".control-card:not(.is-filtered)");

        section.classList.toggle("is-filtered", !has);

        if (needle && has) {
            section.classList.add("open");
            setExpanded(section, true);
        }
    });

    root.querySelectorAll(".chapter-card").forEach(chapter => {
        const has = !!chapter.querySelector(".control-card:not(.is-filtered)");
        chapter.classList.toggle("is-filtered", !has);
    });

    document
        .getElementById("filterEmpty")
        ?.classList.toggle("hidden", visible > 0 || !needle);
}

resultsRoot.addEventListener("click", onResultsClick);
resultsRoot.addEventListener("keydown", onResultsKeydown);
resultsRoot.addEventListener("input", event => {
    if (event.target?.id === "requirementSearch") {
        applyFilter(event.target.value);
    }
});


/* =========================================================
   EDITING
   ========================================================= */

function setComplianceEditMode(enabled) {
    complianceEditMode = Boolean(enabled);

    resultsRoot.querySelectorAll("[data-edit-field]").forEach(field => {
        field.contentEditable = complianceEditMode ? "true" : "false";
        field.classList.toggle("editing", complianceEditMode);
    });

    const button = document.getElementById("toggleEditButton");

    if (button) {
        button.textContent = complianceEditMode
            ? "Finish editing"
            : "Edit compliance";
    }
}

function toggleComplianceEditing() {
    if (complianceEditMode) {
        collectEditedFields();
        setComplianceEditMode(false);
        showToast("Editing finished. Use Save changes or Save as to keep your edits.");
    } else {
        setAllOpen(true);
        setComplianceEditMode(true);
        showToast("Edit the highlighted fields, then choose Save changes or Save as.");
    }
}

function collectEditedFields() {
    if (!latestDecodeResult) return;

    const requirements = arrayValue(latestDecodeResult?.results?.requirements);

    resultsRoot.querySelectorAll("[data-requirement-index]").forEach(card => {
        const item = requirements[Number(card.dataset.requirementIndex)];

        if (!item) return;

        card.querySelectorAll("[data-edit-field]").forEach(field => {
            const key = field.dataset.editField;
            const value = text(field.innerText ?? field.textContent);

            if (key === "todo.name") {
                item.todo = item.todo || {};
                item.todo.name = value;
            } else if (key === "todo.description") {
                item.todo = item.todo || {};
                item.todo.description = value;
            } else {
                item[key] = value;
            }
        });
    });
}


/* =========================================================
   DOWNLOADS + SAVE
   ========================================================= */

function downloadOutput(type) {
    const documentId = latestDecodeResult?.document_id;

    if (!documentId) {
        showToast("The output file is not available.", true);
        return;
    }

    window.open(
        `${API_BASE}/api/download/${type}/${encodeURIComponent(documentId)}`,
        "_blank"
    );
}

function safeBaseName() {
    return (
        text(latestDecodeResult?.filename || "regulation")
            .replace(/\.pdf$/i, "")
            .replace(/[<>:"/\\|?*]+/g, "-") || "regulation"
    );
}

function downloadBlob(content, filename, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);

    const link = document.createElement("a");
    link.href = url;
    link.download = filename;

    document.body.appendChild(link);
    link.click();
    link.remove();

    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function buildCsv() {
    const requirements = arrayValue(latestDecodeResult?.results?.requirements);
    const ctx = contextFor(latestDecodeResult);

    const names = list =>
        arrayValue(list).map(item => text(item?.name)).filter(Boolean).join("; ");

    const rows = [[
        "Chapter",
        "Subchapter",
        "Reference",
        "Title",
        "Source requirement",
        "Summary",
        "Implementation action",
        "Implementation description",
        "Policies",
        "Documents",
        "Evidence",
        "Automation tests",
        "Page start",
        "Page end"
    ]];

    requirements.forEach(requirement => {
        const hierarchy = hierarchyForRequirement(requirement, ctx);

        rows.push([
            hierarchy.chapter,
            hierarchy.section,
            requirement.source_reference || "",
            requirement.source_title || "",
            requirement.source_text || "",
            requirement.source_summary || "",
            requirement.todo?.name || "",
            requirement.todo?.description || "",
            names(requirement.policies),
            names(requirement.documents),
            names(requirement.evidence),
            names(requirement.automation_tests),
            requirement.page_start ?? "",
            requirement.page_end ?? ""
        ]);
    });

    return rows
        .map(row =>
            row
                .map(value => `"${String(value ?? "").replace(/"/g, '""')}"`)
                .join(",")
        )
        .join("\r\n");
}

function downloadEditedRegulation(type = "json") {
    if (!latestDecodeResult) {
        showToast("No regulation is open to download.", true);
        return;
    }

    collectEditedFields();

    const base = safeBaseName();

    if (type === "csv") {
        // BOM so Excel reads Arabic and other non-Latin text correctly.
        downloadBlob(
            "\ufeff" + buildCsv(),
            `${base}_regulation.csv`,
            "text/csv;charset=utf-8"
        );
        return;
    }

    downloadBlob(
        JSON.stringify(latestDecodeResult, null, 2),
        `${base}_regulation.json`,
        "application/json"
    );
}

function saveAsRegulation() {
    if (!latestDecodeResult) {
        showToast("No regulation is open to save.", true);
        return;
    }

    collectEditedFields();

    const name = window.prompt("Save regulation as:", safeBaseName());

    if (name === null) return;

    const safeName =
        name.trim().replace(/[<>:"/\\|?*]+/g, "-") || "regulation";

    downloadBlob(
        JSON.stringify(latestDecodeResult, null, 2),
        `${safeName}.json`,
        "application/json"
    );

    showToast(`Saved as ${safeName}.json`);
}

function saveEditedRegulation(showMessage = true) {
    if (!latestDecodeResult) {
        showToast("No regulation is open to save.", true);
        return false;
    }

    collectEditedFields();

    const saved = addScanToHistory(latestDecodeResult, { edited: true });

    if (showMessage) {
        showToast(
            saved
                ? "Changes saved in this browser."
                : "Could not save locally. The browser may be out of storage space.",
            !saved
        );
    }

    return saved;
}

function removeCurrentDocument() {
    if (!latestDecodeResult && !selectedPdf) {
        showToast("There is no document to remove.", true);
        return;
    }

    if (
        !window.confirm(
            "Remove this document from the current workspace? Saved history will remain."
        )
    ) {
        return;
    }

    decodeAnother();
    showToast("Document removed from the current workspace.");
}

function decodeAnother() {
    latestDecodeResult = null;
    currentSubmission = { company: "", email: "" };

    resultsRoot.innerHTML = "";
    clearUploadForm();

    currentProgress = 8;
    setProgress(8);

    railMode = "decode";
    showView(uploadView);
}


/* =========================================================
   SEND TO SAHL (Slack)
   ========================================================= */

function setSendButtonState(button, state) {
    if (!button) return;

    button.classList.remove("sent", "failed");
    button.disabled = false;

    if (state === "sending") {
        button.disabled = true;
        button.textContent = "Sending to Slack…";
    } else if (state === "sent") {
        button.classList.add("sent");
        button.textContent = "✓ Sent to Sahl · Send again";
    } else if (state === "failed") {
        button.classList.add("failed");
        button.textContent = "Retry sending to Sahl";
    } else {
        button.textContent = "Add regulation to Sahl";
    }
}

async function handleSendToSahl({ auto = false } = {}) {
    if (!latestDecodeResult?.document_id) {
        if (!auto) {
            showToast("Decode a regulation before adding it to Sahl.", true);
        }
        return;
    }

    const getButton = () => resultsRoot.querySelector('[data-action="send"]');

    try {
        collectEditedFields();

        setSendButtonState(getButton(), "sending");

        const metadata = latestDecodeResult?.results?.metadata || {};
        const requirements = arrayValue(latestDecodeResult?.results?.requirements);

        const payload = {
            document_id: latestDecodeResult.document_id,
            filename:
                latestDecodeResult.filename ||
                metadata.filename ||
                "Compliance document",
            framework_name:
                metadata.framework_name ||
                metadata.document_title ||
                latestDecodeResult.framework_name ||
                "Not identified",
            company_name: currentSubmission.company || "Not provided",
            user_email: currentSubmission.email || "Not provided",
            requirement_count: requirements.length,
            requirements,
            regulation: latestDecodeResult
        };

        const response = await fetch(`${API_BASE}/api/slack/notify`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        let data = {};

        try {
            data = await response.json();
        } catch {
            data = {};
        }

        if (!response.ok) {
            throw new Error(data?.detail || "Slack notification failed.");
        }

        latestDecodeResult.slack_status = "sent";
        addScanToHistory(latestDecodeResult, { edited: false });

        setSendButtonState(getButton(), "sent");

        showToast(
            `Sent to Sahl on Slack (${data?.slack_messages_sent || "multiple"} messages).`
        );

    } catch (error) {
        if (latestDecodeResult) latestDecodeResult.slack_status = "failed";

        setSendButtonState(getButton(), "failed");

        showToast(
            error?.message ||
            "Could not notify Sahl on Slack. Check SLACK_WEBHOOK_URL and retry.",
            true
        );
    }
}


/* =========================================================
   RECENT SCANS (history kept in this browser)
   ========================================================= */

function readHistory() {
    try {
        const parsed = JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
        return Array.isArray(parsed) ? parsed : [];
    } catch {
        return [];
    }
}

function writeHistory(records) {
    let list = records.slice(0, MAX_HISTORY);

    for (let attempt = 0; attempt < 14; attempt++) {
        try {
            localStorage.setItem(HISTORY_KEY, JSON.stringify(list));
            return true;
        } catch {
            // Storage is full: drop the stored result of the oldest scan
            // that still has one (the newest scan is dropped last).
            let target = -1;

            for (let i = list.length - 1; i >= 0; i--) {
                if (list[i].data) {
                    target = i;
                    break;
                }
            }

            if (target === -1) {
                list = list.slice(0, Math.max(0, list.length - 1));

                if (!list.length) return false;
                continue;
            }

            list = list.map((record, i) =>
                i === target ? { ...record, data: null } : record
            );
        }
    }

    return false;
}

function addScanToHistory(data, { edited = false } = {}) {
    const metadata = data?.results?.metadata || {};
    const id = data?.document_id || metadata.document_id || "";

    if (!id) return false;

    const existing = readHistory();
    const previous = existing.find(record => record.document_id === id);

    const record = {
        document_id: id,
        filename: data?.filename || metadata.filename || "Compliance document",
        framework_name: metadata.framework_name || metadata.document_title || "",
        page_count: data?.page_count || metadata.page_count || 0,
        requirement_count:
            data?.requirement_count ||
            metadata.requirement_count ||
            arrayValue(data?.results?.requirements).length,
        scanned_at: previous?.scanned_at || new Date().toISOString(),
        edited_at: edited ? new Date().toISOString() : previous?.edited_at || "",
        data
    };

    const saved = writeHistory([
        record,
        ...existing.filter(item => item.document_id !== id)
    ]);

    renderScanHistory();

    return saved;
}

function renderScanHistory() {
    const records = readHistory();

    clearHistoryButton.classList.toggle("hidden", !records.length);

    if (!records.length) {
        historyList.innerHTML = `
            <div class="history-empty">
                <strong>No scan history yet</strong>
                <span>Your decoded regulations will appear here after the first successful scan.</span>
            </div>
        `;
        return;
    }

    historyList.innerHTML = records.map(record => {
        const title = record.framework_name || record.filename || "Compliance document";

        const subtitle =
            record.filename && record.filename !== title
                ? record.filename
                : record.page_count
                    ? `${record.page_count} pages`
                    : "";

        const when = record.edited_at
            ? `Edited ${formatWhen(record.edited_at)}`
            : formatWhen(record.scanned_at);

        const count = Number(record.requirement_count || 0);

        return `
            <article class="history-card" data-history-id="${escapeHtml(record.document_id)}">
                <div class="history-icon">PDF</div>

                <div class="history-info">
                    <strong title="${escapeHtml(title)}">${escapeHtml(title)}</strong>
                    ${subtitle ? `<span title="${escapeHtml(subtitle)}">${escapeHtml(subtitle)}</span>` : ""}
                </div>

                <div class="history-stats">
                    <span class="history-pill">${count} ${count === 1 ? "requirement" : "requirements"}</span>
                    <span class="history-when">${escapeHtml(when)}</span>
                </div>

                <div class="history-actions">
                    ${
                        record.data
                            ? `<button class="secondary-button accent" type="button" data-history-action="open">Open</button>`
                            : `<button class="secondary-button" type="button" disabled title="The full result was not kept because browser storage is full.">Summary only</button>`
                    }
                    <button class="secondary-button" type="button" data-history-action="remove">Remove</button>
                </div>
            </article>
        `;
    }).join("");
}

function openHistoryScan(id) {
    const record = readHistory().find(item => item.document_id === id);

    if (!record?.data) {
        showToast(
            "The full result was not kept for this scan. Decode the PDF again to reopen it.",
            true
        );
        return;
    }

    latestDecodeResult = record.data;
    currentSubmission = { company: "", email: "" };

    renderResults(latestDecodeResult);
    showView(resultsView);
}

function removeHistoryScan(id) {
    writeHistory(readHistory().filter(item => item.document_id !== id));
    renderScanHistory();
    showToast("Scan removed from history.");
}

function clearScanHistory() {
    if (!window.confirm("Clear all recent scans from this browser?")) return;

    try {
        localStorage.removeItem(HISTORY_KEY);
    } catch {
        // ignore
    }

    renderScanHistory();
    showToast("Scan history cleared.");
}

historyList.addEventListener("click", event => {
    const button = event.target.closest("[data-history-action]");

    if (!button || button.disabled) return;

    const card = button.closest("[data-history-id]");
    const id = card?.dataset.historyId;

    if (!id) return;

    if (button.dataset.historyAction === "open") openHistoryScan(id);
    if (button.dataset.historyAction === "remove") removeHistoryScan(id);
});

clearHistoryButton.addEventListener("click", clearScanHistory);


/* =========================================================
   INITIAL STATE
   ========================================================= */

showView(uploadView);
renderScanHistory();
