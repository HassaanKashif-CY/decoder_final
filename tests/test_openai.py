from pathlib import Path

from backend.services.pdf.extractor import PDFExtractor
from backend.services.pdf.cleaner import PDFCleaner
from backend.services.pdf.structure import StructureDetector
from backend.services.pdf.chunker import DocumentChunker
from backend.services.ai.analyzer import ComplianceAnalyzer


def main():
    pdf_path = input("Enter PDF path: ").strip().strip('"')

    if not Path(pdf_path).exists():
        raise FileNotFoundError(pdf_path)

    extractor = PDFExtractor()
    cleaner = PDFCleaner()
    detector = StructureDetector()
    chunker = DocumentChunker()

    print("\nExtracting PDF...")
    extracted = extractor.extract(pdf_path)

    print("Cleaning PDF...")
    cleaned = cleaner.clean(extracted)

    print("Detecting structure...")
    structure = detector.detect(cleaned)

    print("Creating chunks...")
    chunks = chunker.create_chunks(
        cleaned,
        structure,
    )

    print(
        f"Chunks available: {len(chunks)}"
    )

    analyzer = ComplianceAnalyzer()

    print("\nAnalyzing document profile...")
    profile = analyzer.analyze_document_profile(
        structure,
        chunks,
    )

    print("\nDOCUMENT PROFILE")
    print(profile)

    print("\nAnalyzing first chunk...")
    result = analyzer.analyze_chunk(
        chunks[0]
    )

    print("\nAI RESULT")
    print(result)


if __name__ == "__main__":
    main()