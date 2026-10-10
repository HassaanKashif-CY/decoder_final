from backend.services.pdf.extractor import PDFExtractor
from backend.services.pdf.cleaner import PDFCleaner
from backend.services.pdf.requirement_extractor import RequirementExtractor


PDF_PATH = r"C:\Users\YC\Downloads\Data-Cybersecurity-Controls-.pdf"


def main():
    extracted = PDFExtractor().extract(PDF_PATH)
    cleaned = PDFCleaner().clean(extracted)

    extractor = RequirementExtractor()

    requirements = extractor.extract(cleaned)

    print("=" * 100)
    print("REQUIREMENT EXTRACTION TEST")
    print("=" * 100)

    print()
    print(f"Total candidates: {len(requirements)}")

    print()

    for index, requirement in enumerate(
        requirements,
        start=1,
    ):
        print("-" * 100)
        print(f"#{index}")
        print(f"Reference : {requirement.source_reference}")
        print(f"Page     : {requirement.page_start}")
        print(f"Title    : {requirement.source_title}")
        print(f"Confidence: {requirement.confidence:.2f}")
        print(f"Blocks   : {requirement.source_block_ids}")
        print()
        print("SOURCE TEXT:")
        print(requirement.source_text[:1000])


if __name__ == "__main__":
    main()