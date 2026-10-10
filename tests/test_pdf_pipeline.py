from pathlib import Path

from backend.services.pdf.extractor import PDFExtractor
from backend.services.pdf.cleaner import PDFCleaner
from backend.services.pdf.structure import StructureDetector
from backend.services.pdf.chunker import DocumentChunker


def print_tree(nodes, indent=0):
    for node in nodes:
        print(
            " " * indent
            + f"- [{node.level}] {node.title} "
            + f"(pages {node.page_start}-{node.page_end})"
        )

        if node.children:
            print_tree(node.children, indent + 2)


def main():
    pdf_path = input("Enter PDF path: ").strip().strip('"')

    if not Path(pdf_path).exists():
        raise FileNotFoundError(pdf_path)

    extractor = PDFExtractor()
    cleaner = PDFCleaner()
    detector = StructureDetector()
    chunker = DocumentChunker()

    print("\n[1/4] Extracting PDF...")
    extracted = extractor.extract(pdf_path)

    print(
        f"Pages extracted: {len(extracted.pages)}"
    )

    print("\n[2/4] Cleaning document...")
    cleaned = cleaner.clean(extracted)

    print(
        f"Pages after cleaning: {len(cleaned.pages)}"
    )

    print("\n[3/4] Detecting document structure...")
    structure = detector.detect(cleaned)

    print(
        f"Top-level sections detected: "
        f"{len(structure.nodes)}"
    )

    print("\nDetected hierarchy:")
    print_tree(structure.nodes)

    print("\n[4/4] Creating AI chunks...")
    chunks = chunker.create_chunks(
        cleaned,
        structure,
    )

    print(
        f"\nChunks created: {len(chunks)}"
    )

    for chunk in chunks[:10]:
        print(
            f"\n{chunk.chunk_id}"
            f" | Pages {chunk.page_start}-{chunk.page_end}"
            f" | {chunk.character_count} chars"
        )
        print(chunk.text[:500])

    print("\nPipeline test completed successfully.")


if __name__ == "__main__":
    main()