import json
import re
import sys
from copy import deepcopy

INPUT_FILE = sys.argv[1]
OUTPUT_FILE = sys.argv[2]

with open(INPUT_FILE, 'r', encoding='utf-8') as f:
    data = json.load(f)

segments = data.get("segments", [])

corrections = {

    # Names
    "Palmer": "Palmiter",
    "Noack": "Noak",
    "Vogler": "Vogel",
    "Romoville": "Romeoville",
    "Romeovile": "Romeoville",

    # Departments
    "Park District": "Parks and Recreation",

}

vote_words = {
    "I": "Aye",
    "Eye": "Aye",
    "Hi": "Aye",
    "A": "Aye",
    "Nah": "Nay",
    "Na": "Nay"
}

def clean_text(text):

    original = text

    # Apply spelling corrections
    for wrong, correct in corrections.items():
        text = re.sub(r'\b'+wrong+r'\b', correct, text)

    # Fix Resolution numbers
    text = re.sub(
        r'(?i)resolution\s+26[, ]*(\d{4})',
        r'Resolution 26-\1',
        text
    )

    # Fix Ordinance numbers
    text = re.sub(
        r'(?i)ordinance\s+26[, ]*(\d{4})',
        r'Ordinance 26-\1',
        text
    )

    # Fix broken 2641 83 style
    text = re.sub(
        r'26\s*(\d{2})\s*(\d{2})',
        r'26-\1\2',
        text
    )

    # Clean double spaces
    text = re.sub(r'\s+', ' ', text)

    # Capitalize first letter
    if len(text) > 1:
        text = text[0].upper() + text[1:]

    return text


def is_vote_segment(segment, previous_segment):

    text = segment.get("text","").strip()

    if text in vote_words:

        if previous_segment is None:
            return True

        prev_text = previous_segment.get("text","").lower()

        if "trustee" in prev_text:
            return True

        if "roll call" in prev_text:
            return True

        return True

    return False


cleaned_segments = []

for i, segment in enumerate(segments):

    new_segment = deepcopy(segment)

    text = segment.get("text","").strip()

    prev = None
    if i > 0:
        prev = segments[i-1]

    # Vote correction
    if is_vote_segment(segment, prev):

        if text in vote_words:
            text = vote_words[text]

    text = clean_text(text)

    # Light punctuation
    if len(text) > 3:
        if not text.endswith((".", "?", "!")):
            text = text + "."

    new_segment["text"] = text

    cleaned_segments.append(new_segment)

data["segments"] = cleaned_segments

with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2)

print("Transcript cleaned.")
