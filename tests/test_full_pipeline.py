import json
import re
from pathlib import Path

from backend.models.breakdown import (
    ComplianceBreakdown,
    DecoderMetadata,
)
from backend.services.ai.analyzer import RequirementAnalyzer
from backend.services.export.csv_export import CSVExporter
from backend.services.export.json_export import JSONExporter
from backend.services.mapping.requirements import RequirementExtractor
from backend.services.pdf.cleaner import PDFCleaner
from backend.services.pdf.extractor import PDFExtractor


PDF_PATH = r"C:\Users\YC\Downloads\Data-Cybersecurity-Controls-.pdf"

OUTPUT_DIR = Path("data/outputs")


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

    return value.strip("_") or "compliance_document"


def main():
    print("=" * 110)
    print("SAHL COMPLIANCE DECODER - FULL PIPELINE")
    print("=" * 110)

    pdf_path = Path(PDF_PATH)

    if not pdf_path.exists():
        raise FileNotFoundError(
            f"PDF not found: {pdf_path}"
        )

    print()
    print("1. EXTRACTING PDF...")
    extractor = PDFExtractor()
    extracted = extractor.extract(pdf_path)

    print(f"   Pages: {extracted.metadata.page_count}")
    print(f"   Filename: {extracted.metadata.filename}")

    print()
    print("2. CLEANING PDF...")
    cleaner = PDFCleaner()
    cleaned = cleaner.clean(extracted)

    print(f"   Cleaned pages: {len(cleaned.pages)}")

    print()
    print("3. EXTRACTING REQUIREMENTS...")
    requirement_extractor = RequirementExtractor()
    requirements = requirement_extractor.extract(cleaned)

    print(f"   Requirements found: {len(requirements)}")

    if not requirements:
        raise RuntimeError(
            "No requirements were extracted from the PDF."
        )

    print()
    print("4. ANALYZING REQUIREMENTS WITH OPENAI...")
    print()

    analyzer = RequirementAnalyzer()

    analyses = []

    total = len(requirements)

    for index, requirement in enumerate(requirements, start=1):
        print(
            f"   [{index}/{total}] "
            f"{requirement.source_reference}"
        )

        analysis = analyzer.analyze(
            document_name=extracted.metadata.filename,
            requirement=requirement,
        )

        analyses.append(analysis)

    print()
    print("   AI analysis completed.")

    document_id = safe_filename(
        extracted.metadata.filename
    )

    breakdown = ComplianceBreakdown(
        metadata=DecoderMetadata(
            document_id=document_id,
            filename=extracted.metadata.filename,
            page_count=extracted.metadata.page_count,
            requirement_count=len(analyses),
        ),
        requirements=analyses,
        warnings=[],
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    json_path = (
        OUTPUT_DIR
        / f"{document_id}_breakdown.json"
    )

    csv_path = (
        OUTPUT_DIR
        / f"{document_id}_import.csv"
    )

    print()
    print("5. EXPORTING MASTER JSON...")

    JSONExporter().export(
        breakdown=breakdown,
        output_path=json_path,
    )

    print(f"   JSON: {json_path}")

    print()
    print("6. EXPORTING CSV...")

    CSVExporter().export(
        breakdown=breakdown,
        output_path=csv_path,
    )

    print(f"   CSV: {csv_path}")

    print()
    print("=" * 110)
    print("PIPELINE COMPLETED SUCCESSFULLY")
    print("=" * 110)

    print()
    print("OUTPUT SUMMARY")
    print("-" * 110)
    print(f"Document:       {extracted.metadata.filename}")
    print(f"Pages:           {extracted.metadata.page_count}")
    print(f"Requirements:   {len(analyses)}")
    print(f"JSON:            {json_path}")
    print(f"CSV:             {csv_path}")
    print()

    print("FIRST REQUIREMENT")
    print("-" * 110)

    if analyses:
        first = analyses[0]

        print(
            json.dumps(
                first.model_dump(
                    mode="json"
                ),
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()