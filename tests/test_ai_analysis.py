from backend.services.pdf.extractor import PDFExtractor
from backend.services.pdf.cleaner import PDFCleaner
from backend.services.pdf.requirement_extractor import (
    RequirementExtractor,
)
from backend.services.ai.analyzer import (
    RequirementAnalyzer,
)


PDF_PATH = (
    r"C:\Users\YC\Downloads"
    r"\Data-Cybersecurity-Controls-.pdf"
)


def main():

    print("=" * 100)
    print("SAHL AI REQUIREMENT ANALYSIS TEST")
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
        f"   Cleaned pages: {len(cleaned.pages)}"
    )

    print()
    print("3. Extracting requirements...")

    requirements = RequirementExtractor().extract(
        cleaned
    )

    print(
        f"   Requirements found: "
        f"{len(requirements)}"
    )

    if not requirements:
        print("No requirements found.")
        return

    requirement = requirements[0]

    print()
    print("4. Testing first requirement only")
    print()
    print(
        f"Reference: "
        f"{requirement.source_reference}"
    )
    print(
        f"Page: "
        f"{requirement.page_start}"
    )
    print(
        f"Source: "
        f"{requirement.source_text}"
    )

    print()
    print("5. Calling OpenAI...")

    analyzer = RequirementAnalyzer()

    result = analyzer.analyze(
        document_name=extracted.metadata.filename,
        requirement=requirement,
    )

    print()
    print("=" * 100)
    print("AI RESULT")
    print("=" * 100)

    print()
    print(
        "SOURCE REFERENCE:"
    )
    print(result.source_reference)

    print()
    print(
        "SOURCE TEXT:"
    )
    print(result.source_text)

    print()
    print(
        "SOURCE SUMMARY:"
    )
    print(result.source_summary)

    print()
    print(
        "TO-DO:"
    )
    print(
        result.todo.name
    )
    print(
        result.todo.description
    )

    print()
    print(
        "POLICIES:"
    )

    for item in result.policies:
        print(
            f"- {item.name}: "
            f"{item.description}"
        )

    print()
    print(
        "DOCUMENTS:"
    )

    for item in result.documents:
        print(
            f"- {item.name}: "
            f"{item.description}"
        )

    print()
    print(
        "EVIDENCE:"
    )

    for item in result.evidence:
        print(
            f"- {item.name}: "
            f"{item.description}"
        )

    print()
    print("AI analysis test completed.")


if __name__ == "__main__":
    main()