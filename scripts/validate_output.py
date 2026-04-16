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

    if len(out_segments) == 0:
        raise ValueError("Output JSON has zero segments.")

    if len(out_segments) < len(src_segments):
        raise ValueError(
            f"Output segment count is smaller than input: input={len(src_segments)} output={len(out_segments)}"
        )

    for i, seg in enumerate(out_segments):
        if "speaker" not in seg:
            raise ValueError(f"Missing speaker in output segment {i}")
        if "start" not in seg:
            raise ValueError(f"Missing start time in output segment {i}")
        if "duration" not in seg:
            raise ValueError(f"Missing duration in output segment {i}")

    with open(output_csv, "r", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    if len(rows) < 2:
        raise ValueError("CSV has no data rows.")

    csv_data_rows = len(rows) - 1

    if csv_data_rows != len(out_segments):
        raise ValueError(
            f"CSV row mismatch: csv={csv_data_rows} json={len(out_segments)}"
        )

    print(
        f"Validation passed. Input segments={len(src_segments)}, "
        f"Output segments={len(out_segments)}, CSV rows={csv_data_rows}"
    )


if __name__ == "__main__":
    main()
