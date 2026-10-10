from backend.services.pdf.extractor import PDFExtractor
from backend.services.pdf.cleaner import PDFCleaner
from backend.services.pdf.requirement_extractor import RequirementExtractor
from backend.services.pdf.requirement_mapper import RequirementMapper


PDF_PATH = r"C:\Users\YC\Downloads\Data-Cybersecurity-Controls-.pdf"


def main():
    extracted = PDFExtractor().extract(PDF_PATH)
    cleaned = PDFCleaner().clean(extracted)

    extracted_requirements = RequirementExtractor().extract(cleaned)

    mapped = RequirementMapper().map(
        document_id="dcc_test",
        requirements=extracted_requirements,
    )

    print("=" * 100)
    print("REQUIREMENT MAPPING TEST")
    print("=" * 100)
    print()
    print(f"Final requirements: {len(mapped.requirements)}")
    print()

    for index, item in enumerate(mapped.requirements, start=1):
        print("-" * 100)
        print(f"#{index}")
        print(f"Reference : {item.source_reference}")
        print(f"Page      : {item.page_start}")
        print(f"Title     : {item.source_title}")
        print(f"Confidence: {item.confidence:.2f}")
        print()
        print(item.source_text[:500])


if __name__ == "__main__":
    main()