import re
import shutil
import uuid
from pathlib import Path

import fitz
from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    UploadFile,
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
from backend.services.email.sender import (
    EmailSender,
    EmailSenderError,
)
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

        email_status = "not_configured"
        email_recipients = ""

        if settings.send_email_on_decode:
            try:
                print("")
                print(
                    "6. SENDING DECODED FILES TO SAHL..."
                )

                recipients = (
                    EmailSender()
                    .send_submission(
                        company_name=(
                            company_name.strip()
                        ),
                        user_email=(
                            user_email.strip()
                        ),
                        document_name=(
                            original_filename
                        ),
                        framework_name=(
                            document_title
                        ),
                        requirement_count=len(
                            analyses
                        ),
                        pdf_path=upload_path,
                        json_path=json_path,
                        csv_path=csv_path,
                    )
                )

                email_status = "sent"

                email_recipients = ", ".join(
                    recipients
                )

                print(
                    "   Sahl submission email sent."
                )

            except EmailSenderError as exc:
                email_status = "failed"

                print(
                    "   Sahl email failed: "
                    f"{exc}"
                )

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
            "email_status": email_status,
            "email_recipients": email_recipients,
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



@router.post("/send-to-sahl/{document_id}")
def send_to_sahl(
    document_id: str,
    company_name: str = Form(""),
    user_email: str = Form(""),
):
    """Send an already-decoded submission to Sahl on explicit user action."""
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,180}", document_id):
        raise HTTPException(status_code=400, detail="Invalid document ID.")

    pdf_path = find_uploaded_pdf(document_id)
    json_path = find_output_file(document_id, "_breakdown.json")
    csv_path = find_output_file(document_id, "_import.csv")

    missing = [
        name for name, path in (("PDF", pdf_path), ("JSON", json_path), ("CSV", csv_path))
        if path is None or not path.exists()
    ]
    if missing:
        raise HTTPException(
            status_code=404,
            detail="Submission files not found: " + ", ".join(missing) + ". Decode the PDF again and retry.",
        )

    if user_email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", user_email.strip()):
        raise HTTPException(status_code=400, detail="Enter a valid business email address.")

    try:
        import json
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}
        recipients = EmailSender().send_submission(
            company_name=company_name.strip(),
            user_email=user_email.strip(),
            document_name=str(metadata.get("filename") or pdf_path.name),
            framework_name=str(metadata.get("framework_name") or metadata.get("document_title") or "Compliance Document"),
            requirement_count=int(metadata.get("requirement_count") or 0),
            pdf_path=pdf_path,
            json_path=json_path,
            csv_path=csv_path,
        )
        if not recipients:
            raise EmailSenderError("No recipients were returned. Check SMTP and SAHL_RECIPIENTS settings.")
        return {"status": "sent", "recipients": recipients}
    except EmailSenderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unable to prepare Sahl submission: {type(exc).__name__}: {exc}") from exc


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
