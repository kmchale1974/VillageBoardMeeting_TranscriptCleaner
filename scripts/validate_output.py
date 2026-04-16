import csv
import json
import sys


def main() -> None:
    if len(sys.argv) != 4:
        print("Usage: python validate_output.py <input_json> <output_json> <output_csv>")
        sys.exit(1)

    input_json, output_json, output_csv = sys.argv[1], sys.argv[2], sys.argv[3]

    with open(input_json, "r", encoding="utf-8") as f:
        src = json.load(f)
    with open(output_json, "r", encoding="utf-8") as f:
        out = json.load(f)

    src_segments = src.get("segments", [])
    out_segments = out.get("segments", [])

    if len(src_segments) != len(out_segments):
        raise ValueError(f"Segment count mismatch: input={len(src_segments)} output={len(out_segments)}")

    with open(output_csv, "r", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    if len(rows) - 1 != len(out_segments):
        raise ValueError(f"CSV row mismatch: csv={len(rows)-1} json={len(out_segments)}")

    print("Validation passed.")


if __name__ == "__main__":
    main()
