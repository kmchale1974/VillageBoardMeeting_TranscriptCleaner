import json
import csv
import sys

INPUT_FILE = sys.argv[1]
OUTPUT_FILE = sys.argv[2]

with open(INPUT_FILE,'r',encoding='utf-8') as f:
    data=json.load(f)

segments=data["segments"]

with open(OUTPUT_FILE,'w',newline='',encoding='utf-8') as csvfile:

    writer=csv.writer(csvfile)

    writer.writerow([
        "Speaker",
        "Start Time",
        "End Time",
        "Text"
    ])

    for seg in segments:

        speaker=seg.get("speaker","")

        start=seg.get("start","")
        end=seg.get("end","")

        text=seg.get("text","")

        writer.writerow([
            speaker,
            start,
            end,
            text
        ])

print("CSV created")
