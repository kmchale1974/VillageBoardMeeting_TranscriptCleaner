import csv
import json
import sys
from pathlib import Path


def extract_text(segment: dict) -> str:
    if "text" in segment and str(segment["text"]).strip():
        return str(segment["text"]).strip()
    words = []
    for w in segment.get("words", []):
        txt = str(w.get("text", "")).strip()
        if txt:
            words.append(txt)
    return " ".join(words).strip()


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: python json_to_csv.py <input_json> <output_csv>")
        sys.exit(1)

    input_json = sys.argv[1]
    output_csv = sys.argv[2]

    with open(input_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    segments = data.get("segments", [])

    Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Speaker", "Start Time", "End Time", "Text"])

        for seg in segments:
            start = seg.get("start", "")
            duration = seg.get("duration", 0)
            end = round(float(start) + float(duration), 3) if start != "" else ""
            writer.writerow([
                seg.get("speaker", ""),
                start,
                end,
                extract_text(seg)
            ])

    print("CSV export complete.")


if __name__ == "__main__":
    main()
