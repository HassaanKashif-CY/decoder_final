from backend.services.pdf.extractor import PDFExtractor
from backend.services.pdf.cleaner import PDFCleaner
from backend.services.pdf.structure_discovery import StructureDiscovery


PDF_PATH = r"C:\Users\YC\Downloads\Data-Cybersecurity-Controls-.pdf"


def main():
    extracted = PDFExtractor().extract(PDF_PATH)
    cleaned = PDFCleaner().clean(extracted)

    result = StructureDiscovery().discover(cleaned)

    print("=" * 80)
    print("DOCUMENT PROFILE")
    print("=" * 80)

    for key, value in result["document_profile"].items():
        print(f"{key}: {value}")

    print()
    print("=" * 80)
    print("NUMBERING PATTERNS")
    print("=" * 80)

    for item in result["numbering_patterns"]:
        print(
            f'{item["pattern"]} | '
            f'count={item["count"]} | '
            f'depth={item["depth"]} | '
            f'examples={item["examples"]}'
        )

    print()
    print("=" * 80)
    print("HEADING CANDIDATES")
    print("=" * 80)

    for item in result["heading_candidates"]:
        print(
            f'{item["page_number"]:03d} | '
            f'score={item["score"]:4.1f} | '
            f'font={item["font_size"]:5.1f} | '
            f'bold={item["bold"]} | '
            f'{item["text"]}'
        )

    print()
    print("=" * 80)
    print("SPECIAL REGIONS")
    print("=" * 80)

    for item in result["special_regions"]:
        print(
            f'{item["page_number"]:03d} | '
            f'{item["type"]:25} | '
            f'{item["text"]}'
        )


if __name__ == "__main__":
    main()