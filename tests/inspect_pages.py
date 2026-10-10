from backend.services.pdf.extractor import PDFExtractor
from backend.services.pdf.cleaner import PDFCleaner

PDF_PATH = r"C:\Users\YC\Downloads\Data-Cybersecurity-Controls-.pdf"


def main():
    extracted = PDFExtractor().extract(PDF_PATH)
    cleaned = PDFCleaner().clean(extracted)

    for page in cleaned.pages:
        if not 11 <= page.page_number <= 19:
            continue
        

        print()
        print("=" * 80)
        print(f"PAGE {page.page_number}")
        print("=" * 80)

        for block in page.blocks:
            print(
                f"{block.block_number:03d} | "
                f"font={block.font_size:5.1f} | "
                f"bold={str(block.is_bold):5} | "
                f"x={block.x0:6.1f} | "
                f"y={block.y0:6.1f} | "
                f"{block.text}"
            )


if __name__ == "__main__":
    main()