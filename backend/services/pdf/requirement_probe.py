import re

from backend.services.pdf.extractor import PDFExtractor
from backend.services.pdf.cleaner import PDFCleaner


PDF_PATH = r"C:\Users\YC\Downloads\Data-Cybersecurity-Controls-.pdf"


NUMBER_PATTERN = re.compile(
    r"(?<![\w-])\d+(?:-\d+){1,8}(?![\w-])"
)


def show_matches(text: str):
    matches = list(NUMBER_PATTERN.finditer(text))

    for index, match in enumerate(matches, start=1):
        value = match.group(0)

        start = max(0, match.start() - 100)
        end = min(len(text), match.end() + 180)

        before_after = text[start:end]
        before_after = re.sub(r"\s+", " ", before_after)

        print()
        print(f"{index:03d}. {value}")
        print(f"    position: {match.start()} - {match.end()}")
        print(f"    context: ...{before_after}...")


def main():
    extracted = PDFExtractor().extract(PDF_PATH)
    cleaned = PDFCleaner().clean(extracted)

    print("=" * 100)
    print("RAW NUMBERING DIAGNOSTIC")
    print("=" * 100)

    for page in cleaned.pages:
        if not 11 <= page.page_number <= 19:
            continue

        for block in page.blocks:
            if len(block.text) < 20:
                continue

            matches = list(NUMBER_PATTERN.finditer(block.text))

            if not matches:
                continue

            print()
            print("=" * 100)
            print(
                f"PAGE {page.page_number} | "
                f"BLOCK {block.block_number} | "
                f"TOTAL MATCHES: {len(matches)}"
            )
            print("=" * 100)

            show_matches(block.text)


if __name__ == "__main__":
    main()