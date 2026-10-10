from backend.services.pdf.extractor import PDFExtractor
from backend.services.pdf.cleaner import PDFCleaner
from backend.services.pdf.requirement_extractor import RequirementExtractor


PDF_PATH = r"C:\Users\YC\Downloads\Data-Cybersecurity-Controls-.pdf"


def main():
    print("=" * 100)
    print("SAHL REQUIREMENT CONTINUATION TEST")
    print("=" * 100)

    print()
    print("1. Extracting PDF...")

    extracted = PDFExtractor().extract(
        PDF_PATH
    )

    print(
        f"   Pages: {len(extracted.pages)}"
    )

    print()
    print("2. Cleaning PDF...")

    cleaned = PDFCleaner().clean(
        extracted
    )

    print(
        f"   Cleaned pages: "
        f"{len(cleaned.pages)}"
    )

    print()
    print("3. Extracting requirements...")

    requirements = (
        RequirementExtractor().extract(
            cleaned
        )
    )

    print(
        f"   Requirements found: "
        f"{len(requirements)}"
    )

    print()

    target_references = {
        "1-2-1",
        "1-2-1-1",
        "1-2-1-2",
    }

    found = False

    for requirement in requirements:
        if (
            requirement.source_reference
            not in target_references
        ):
            continue

        found = True

        print("-" * 100)

        print(
            f"REFERENCE: "
            f"{requirement.source_reference}"
        )

        print(
            f"PAGES: "
            f"{requirement.page_start} - "
            f"{requirement.page_end}"
        )

        print(
            f"BLOCKS: "
            f"{requirement.source_block_ids}"
        )

        print()

        print("SOURCE TITLE:")

        print(
            requirement.source_title
        )

        print()

        print("SOURCE TEXT:")

        print(
            requirement.source_text
        )

        print()

    if not found:
        print(
            "Target requirements were not found."
        )

    print("=" * 100)
    print("CONTINUATION TEST COMPLETED")
    print("=" * 100)


if __name__ == "__main__":
    main()