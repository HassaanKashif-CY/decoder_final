from backend.services.pdf.extractor import PDFExtractor


PDF_PATH = r"C:\Users\YC\Downloads\Data-Cybersecurity-Controls-.pdf"


def main():
    print("=" * 120)
    print("SAHL PDF TABLE EXTRACTION TEST")
    print("=" * 120)

    document = PDFExtractor().extract(
        PDF_PATH
    )

    total_tables = 0

    for page in document.pages:

        if not page.tables:
            continue

        print()
        print("=" * 120)
        print(
            f"PAGE {page.page_number}"
        )
        print("=" * 120)

        for table in page.tables:

            total_tables += 1

            print()
            print(
                f"TABLE: {table.table_id}"
            )

            print(
                f"BBOX: {table.bbox}"
            )

            print(
                f"ROWS: {len(table.rows)}"
            )

            print()

            for row_index, row in enumerate(
                table.rows
            ):
                print(
                    f"ROW {row_index}:"
                )

                for column_index, cell in enumerate(
                    row
                ):
                    print(
                        f"  COL {column_index}: "
                        f"{cell}"
                    )

    print()
    print("=" * 120)
    print(
        f"TOTAL TABLES: {total_tables}"
    )
    print("=" * 120)


if __name__ == "__main__":
    main()