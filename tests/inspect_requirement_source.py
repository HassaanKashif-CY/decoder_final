import re

from backend.services.pdf.extractor import PDFExtractor
from backend.services.pdf.cleaner import PDFCleaner


PDF_PATH = r"C:\Users\YC\Downloads\Data-Cybersecurity-Controls-.pdf"


ID_PATTERN = re.compile(
    r"(?<!\d)(\d+(?:-\d+){1,8})(?!\d)"
)


TARGET_IDS = {
    "1-2-1",
    "1-2-1-1",
    "1-2-1-2",
}


def main():
    print("=" * 120)
    print("SAHL REQUIREMENT SOURCE DIAGNOSTIC")
    print("=" * 120)

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
    print("3. Searching for target IDs...")

    found_targets = []

    for page in cleaned.pages:
        for block in page.blocks:

            matches = list(
                ID_PATTERN.finditer(
                    block.text
                )
            )

            for match in matches:
                reference = match.group(1)

                if reference not in TARGET_IDS:
                    continue

                found_targets.append(
                    (
                        page.page_number,
                        block.block_id,
                        block.block_number,
                        reference,
                        block.text,
                    )
                )

    print()

    if not found_targets:
        print(
            "NO TARGET IDs FOUND IN CLEANED BLOCKS."
        )
        print()
        print(
            "This means the problem occurs "
            "before requirement extraction."
        )

        print()
        print("Searching raw extracted PDF...")

        for page in extracted.pages:
            for block in page.blocks:

                matches = list(
                    ID_PATTERN.finditer(
                        block.text
                    )
                )

                for match in matches:
                    reference = match.group(1)

                    if reference not in TARGET_IDS:
                        continue

                    print()
                    print(
                        "-" * 120
                    )

                    print(
                        f"PAGE: "
                        f"{page.page_number}"
                    )

                    print(
                        f"BLOCK: "
                        f"{block.block_id}"
                    )

                    print(
                        f"REFERENCE: "
                        f"{reference}"
                    )

                    print()
                    print(
                        block.text
                    )

        return

    print(
        f"Found {len(found_targets)} "
        f"target occurrences."
    )

    print()

    for (
        page_number,
        block_id,
        block_number,
        reference,
        text,
    ) in found_targets:

        print("=" * 120)

        print(
            f"TARGET REFERENCE: {reference}"
        )

        print(
            f"PAGE: {page_number}"
        )

        print(
            f"BLOCK ID: {block_id}"
        )

        print(
            f"BLOCK NUMBER: {block_number}"
        )

        print()

        print("CURRENT BLOCK TEXT:")

        print(text)

        print()

        print(
            "FOLLOWING BLOCKS:"
        )

        current_page = None
        current_index = None

        for page in cleaned.pages:
            for index, block in enumerate(
                page.blocks
            ):
                if block.block_id == block_id:
                    current_page = page
                    current_index = index
                    break

            if current_page is not None:
                break

        if (
            current_page is None
            or current_index is None
        ):
            print(
                "Unable to locate block."
            )
            continue

        shown = 0

        for index in range(
            current_index + 1,
            len(current_page.blocks),
        ):
            next_block = (
                current_page.blocks[index]
            )

            print()
            print(
                f"[SAME PAGE BLOCK "
                f"{next_block.block_number}]"
            )

            print(
                next_block.text
            )

            shown += 1

            if shown >= 8:
                break

        if shown < 8:
            next_page_number = (
                current_page.page_number + 1
            )

            if (
                next_page_number
                <= len(cleaned.pages)
            ):
                next_page = cleaned.pages[
                    next_page_number - 1
                ]

                for next_block in next_page.blocks:
                    print()
                    print(
                        f"[NEXT PAGE "
                        f"BLOCK "
                        f"{next_block.block_number}]"
                    )

                    print(
                        next_block.text
                    )

                    shown += 1

                    if shown >= 8:
                        break

        print()

    print("=" * 120)
    print("DIAGNOSTIC COMPLETED")
    print("=" * 120)


if __name__ == "__main__":
    main()