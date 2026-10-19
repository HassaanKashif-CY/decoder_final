import csv
import io
import json
import re
import shutil
import time
import uuid
from pathlib import Path

import fitz
from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    UploadFile,
    Request,
)
from fastapi.responses import FileResponse

from backend.core.config import get_settings
from backend.models.breakdown import (
    ComplianceBreakdown,
    DecoderMetadata,
)
from backend.services.ai.analyzer import (
    ComplianceDocumentAnalyzer,
    DocumentAnalysisError,
)
from backend.services.slack.sender import SlackSenderError, send_slack_message
from backend.services.export.csv_export import CSVExporter
from backend.services.export.json_export import JSONExporter
from backend.services.mapping.requirements import RequirementExtractor
from backend.services.pdf.cleaner import PDFCleaner
from backend.services.pdf.extractor import PDFExtractor


router = APIRouter(
    prefix="/api",
    tags=["Compliance Decoder"],
)

settings = get_settings()


def safe_filename(filename: str) -> str:
    value = Path(filename).stem

    value = re.sub(
        r"[^A-Za-z0-9._-]+",
        "_",
        value,
    )

    value = re.sub(
        r"_+",
        "_",
        value,
    )

    return (
        value.strip("_")
        or "compliance_document"
    )


def validate_pdf(
    filename: str,
    content_type: str | None,
) -> None:
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are supported.",
        )

    if content_type and content_type not in {
        "application/pdf",
        "application/octet-stream",
    }:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file must be a PDF.",
        )


def inspect_pdf(
    pdf_path: Path,
) -> int:
    try:
        with fitz.open(pdf_path) as document:
            page_count = len(document)

        if page_count == 0:
            raise ValueError(
                "The PDF contains no pages."
            )

        if page_count > settings.max_pdf_pages:
            raise ValueError(
                "PDF exceeds the maximum allowed "
                f"page count of {settings.max_pdf_pages}."
            )

        return page_count

    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Unable to read PDF: {exc}",
        ) from exc


@router.post("/decode")
async def decode_pdf(
    file: UploadFile = File(...),
    company_name: str = Form(""),
    user_email: str = Form(""),
):
    validate_pdf(
        filename=file.filename or "",
        content_type=file.content_type,
    )

    settings.ensure_directories()

    original_filename = (
        file.filename
        or "document.pdf"
    )

    base_name = safe_filename(
        original_filename
    )

    job_id = uuid.uuid4().hex[:12]

    upload_filename = (
        f"{base_name}_{job_id}.pdf"
    )

    upload_path = (
        settings.upload_path
        / upload_filename
    )

    try:
        with upload_path.open("wb") as output:
            shutil.copyfileobj(
                file.file,
                output,
            )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to save uploaded PDF: "
                f"{exc}"
            ),
        ) from exc

    finally:
        await file.close()

    file_size = upload_path.stat().st_size

    max_bytes = (
        settings.max_upload_mb
        * 1024
        * 1024
    )

    if file_size > max_bytes:
        upload_path.unlink(
            missing_ok=True
        )

        raise HTTPException(
            status_code=413,
            detail=(
                "PDF exceeds the maximum upload "
                f"size of {settings.max_upload_mb} MB."
            ),
        )

    page_count = inspect_pdf(
        upload_path
    )

    document_id = (
        f"{base_name}_{job_id}"
    )

    try:
        print("")
        print("=" * 60)
        print("SAHL COMPLIANCE DECODER")
        print("=" * 60)

        print("")
        print("1. EXTRACTING PDF...")

        extractor = PDFExtractor()
        extracted = extractor.extract(
            upload_path
        )

        print(
            f"   Pages: {extracted.metadata.page_count}"
        )

        print("")
        print("2. CLEANING PDF...")

        cleaner = PDFCleaner()
        cleaned = cleaner.clean(
            extracted
        )

        print(
            f"   Cleaned pages: {len(cleaned.pages)}"
        )

        print("")
        print("3. EXTRACTING REQUIREMENTS...")

        requirement_extractor = RequirementExtractor()

        requirements = requirement_extractor.extract(
            cleaned
        )

        print(
            f"   Requirements found: "
            f"{len(requirements)}"
        )

        if not requirements:
            raise DocumentAnalysisError(
                "No compliance requirements could be "
                "detected in the uploaded PDF."
            )

        print("")
        print("4. ANALYZING REQUIREMENTS WITH OPENAI...")

        analyzer = ComplianceDocumentAnalyzer(
            batch_size=10
        )

        analyses = analyzer.analyze_many(
            document_name=(
                extracted.metadata.filename
            ),
            requirements=requirements,
        )

        print("")
        print(
            "   AI analysis completed."
        )

        print("")
        print("5. EXPORTING MASTER JSON...")

        profile = requirement_extractor.last_profile or {}
        document_title = (
            str(profile.get("document_title") or "").strip()
            or str(extracted.metadata.title or "").strip()
            or Path(original_filename).stem
        )
        framework_name = (
            str(profile.get("framework_name") or "").strip()
            or document_title
        )

        breakdown = ComplianceBreakdown(
            metadata=DecoderMetadata(
                document_id=document_id,
                filename=original_filename,
                page_count=page_count,
                requirement_count=len(analyses),
                document_title=document_title,
                document_type=str(profile.get("document_type") or "Compliance Document"),
                framework_name=framework_name,
                version=str(profile.get("version") or ""),
                jurisdiction=str(profile.get("jurisdiction") or ""),
                requirement_unit_name=str(profile.get("requirement_unit_name") or ""),
                hierarchy_description=str(profile.get("hierarchy_description") or ""),
                hierarchy_levels=profile.get("hierarchy_levels") or [],
                regulation_summary=str(profile.get("regulation_summary") or "").strip(),
                applicability_conditions=str(profile.get("applicability_conditions") or "").strip(),
                applicable_industries=profile.get("applicable_industries") or [],
                ai_model=settings.openai_model,
            ),
            structure=[],
            requirements=analyses,
            warnings=list(requirement_extractor.last_warnings or []),
        )

        json_filename = (
            f"{document_id}_breakdown.json"
        )

        csv_filename = (
            f"{document_id}_import.csv"
        )

        json_path = (
            settings.output_path
            / json_filename
        )

        csv_path = (
            settings.output_path
            / csv_filename
        )

        JSONExporter().export(
            breakdown=breakdown,
            output_path=json_path,
        )

        CSVExporter().export(
            breakdown=breakdown,
            output_path=csv_path,
        )

        print(
            "   JSON and CSV exports completed."
        )

        slack_status = "not_configured"
        try:
            print("\n6. SENDING SLACK NOTIFICATION...")
            send_slack_message(
                "*Sahl Compliance Decoder — Decode Completed*\n"
                f"*Document:* {original_filename}\n"
                f"*Framework:* {document_title}\n"
                f"*Requirements:* {len(analyses)}\n"
                f"*Document ID:* {document_id}\n"
                "*Status:* Decode completed successfully"
            )
            slack_status = "sent"
            print("   Slack notification sent.")
        except SlackSenderError as exc:
            slack_status = "failed"
            print(f"   Slack notification failed: {exc}")

        print("")
        print("=" * 60)
        print("DECODING COMPLETED")
        print("=" * 60)
        print("")

        return {
            "status": "completed",
            "job_id": job_id,
            "document_id": document_id,
            "filename": original_filename,
            "page_count": page_count,
            "requirement_count": len(
                analyses
            ),
            "slack_status": slack_status,
            "downloads": {
                "pdf": (
                    f"/api/download/pdf/"
                    f"{document_id}"
                ),
                "json": (
                    f"/api/download/json/"
                    f"{document_id}"
                ),
                "csv": (
                    f"/api/download/csv/"
                    f"{document_id}"
                ),
            },
            "results": breakdown.model_dump(
                mode="json"
            ),
        }

    except HTTPException:
        raise
    except DocumentAnalysisError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        # Keep server logs useful while returning a concise API error.
        print(f"Decode pipeline error: {type(exc).__name__}: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Decode pipeline failed ({type(exc).__name__}): {exc}",
        ) from exc



@router.post("/slack/notify")
async def notify_sahl_on_slack(request: Request):
    """Send the user's edited compliance data to Slack, not just metadata."""
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="A valid JSON body is required.") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="The request body must be a JSON object.")

    document_id = str(payload.get("document_id") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,180}", document_id):
        raise HTTPException(status_code=400, detail="Invalid or missing document ID.")

    filename = str(payload.get("filename") or "Compliance document")[:250]
    framework = str(payload.get("framework_name") or "Not identified")[:250]
    company = str(payload.get("company_name") or "Not provided")[:250]
    user_email = str(payload.get("user_email") or "Not provided")[:250]
    requirements = payload.get("requirements")
    if not isinstance(requirements, list):
        raise HTTPException(status_code=400, detail="Edited requirements must be a JSON array.")
    if len(requirements) > 1000:
        raise HTTPException(status_code=413, detail="This submission contains too many requirements.")

    # Use the edited browser payload as the source of truth. This ensures edits
    # made before clicking Add regulation to Sahl are what Slack receives.
    regulation = payload.get("regulation")
    if not isinstance(regulation, dict):
        regulation = {}
    regulation = dict(regulation)
    regulation["filename"] = filename
    regulation["document_id"] = document_id
    regulation["results"] = dict(regulation.get("results") or {})
    regulation["results"]["requirements"] = requirements
    metadata = dict(regulation["results"].get("metadata") or {})
    metadata["framework_name"] = framework
    regulation["results"]["metadata"] = metadata

    json_text = json.dumps(regulation, ensure_ascii=False, indent=2, default=str)
    csv_buffer = io.StringIO(newline="")
    writer = csv.writer(csv_buffer)
    writer.writerow(["Reference", "Title", "Source requirement", "Summary", "Implementation action", "Implementation description", "Policies", "Documents", "Evidence"])

    def item_names(value):
        if not isinstance(value, list):
            return str(value or "")
        names = []
        for entry in value:
            if isinstance(entry, dict):
                names.append(str(entry.get("name") or entry.get("title") or json.dumps(entry, ensure_ascii=False)))
            else:
                names.append(str(entry))
        return "; ".join(names)

    for item in requirements:
        if not isinstance(item, dict):
            continue
        todo = item.get("todo") if isinstance(item.get("todo"), dict) else {}
        writer.writerow([
            item.get("source_reference", ""), item.get("source_title", ""),
            item.get("source_text", ""), item.get("source_summary", ""),
            todo.get("name", ""), todo.get("description", ""),
            item_names(item.get("policies")), item_names(item.get("documents")),
            item_names(item.get("evidence")),
        ])
    csv_text = csv_buffer.getvalue()

    header = (
        "*Sahl Compliance Decoder — Regulation Submitted*\n"
        f"*Document:* {filename}\n*Framework:* {framework}\n"
        f"*Company:* {company}\n*Submitted by:* {user_email}\n"
        f"*Requirements:* {len(requirements)}\n*Document ID:* {document_id}\n"
        "*Payload:* Edited JSON and CSV are included in following messages."
    )

    # Slack messages have practical size limits. Send readable chunks rather
    # than relying on temporary Render file links or sending only a summary.
    def split_text(label: str, text_value: str, max_chars: int = 2800) -> list[str]:
        if not text_value:
            return [f"{label}\n(empty)"]
        chunks = []
        total = (len(text_value) + max_chars - 1) // max_chars
        for idx in range(total):
            piece = text_value[idx * max_chars:(idx + 1) * max_chars]
            chunks.append(f"*{label} — part {idx + 1}/{total}*\n```\n{piece}\n```")
        return chunks

    messages = [header] + split_text("EDITED REGULATION JSON", json_text) + split_text("EDITED REGULATION CSV", csv_text)
    try:
        for index, message in enumerate(messages):
            if index:
                time.sleep(1.05)
            send_slack_message(message)
    except SlackSenderError as exc:
        print(f"Slack submission failed: {exc}")
        raise HTTPException(status_code=502, detail=f"Slack could not receive the full submission: {exc}") from exc

    return {
        "status": "sent",
        "channel": "slack",
        "document_id": document_id,
        "requirements_sent": len(requirements),
        "json_characters": len(json_text),
        "csv_characters": len(csv_text),
        "slack_messages_sent": len(messages),
    }


def find_uploaded_pdf(
    document_id: str,
) -> Path | None:

    matches = list(
        settings.upload_path.glob(
            f"{document_id}.pdf"
        )
    )

    if matches:
        return matches[0]

    fallback_matches = list(
        settings.upload_path.glob(
            f"*_{document_id.split('_')[-1]}.pdf"
        )
    )

    if fallback_matches:
        return fallback_matches[0]

    return None


def find_output_file(
    document_id: str,
    suffix: str,
) -> Path | None:

    path = (
        settings.output_path
        / f"{document_id}{suffix}"
    )

    if path.exists():
        return path

    return None


@router.get(
    "/download/pdf/{document_id}"
)
def download_pdf(
    document_id: str,
):
    pdf_path = find_uploaded_pdf(
        document_id
    )

    if pdf_path is None:
        raise HTTPException(
            status_code=404,
            detail="Original PDF not found.",
        )

    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=pdf_path.name,
    )


@router.get(
    "/download/json/{document_id}"
)
def download_json(
    document_id: str,
):
    json_path = find_output_file(
        document_id,
        "_breakdown.json",
    )

    if json_path is None:
        raise HTTPException(
            status_code=404,
            detail="JSON output not found.",
        )

    return FileResponse(
        path=json_path,
        media_type="application/json",
        filename=json_path.name,
    )


@router.get(
    "/download/csv/{document_id}"
)
def download_csv(
    document_id: str,
):
    csv_path = find_output_file(
        document_id,
        "_import.csv",
    )

    if csv_path is None:
        raise HTTPException(
            status_code=404,
            detail="CSV output not found.",
        )

    return FileResponse(
        path=csv_path,
        media_type="text/csv",
        filename=csv_path.name,
    )
