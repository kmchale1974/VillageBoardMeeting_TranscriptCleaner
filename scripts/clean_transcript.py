import json
import re
import sys
from copy import deepcopy
from pathlib import Path


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data: dict) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_config(config_dir: str) -> tuple[dict, dict]:
    officials = load_json(str(Path(config_dir) / "officials.json"))
    corrections = load_json(str(Path(config_dir) / "corrections.json"))
    return officials, corrections


def extract_text(segment: dict) -> str:
    if "text" in segment and str(segment["text"]).strip():
        return str(segment["text"]).strip()

    words = []
    for w in segment.get("words", []):
        txt = str(w.get("text", "")).strip()
        if txt:
            words.append(txt)
    return " ".join(words).strip()


def rebuild_text_field(segment: dict, text: str) -> None:
    segment["text"] = text


def apply_replacements(text: str, replacements: dict[str, str], log: list, start: float, rule: str) -> str:
    original = text
    for wrong, correct in replacements.items():
        text = re.sub(rf"\b{re.escape(wrong)}\b", correct, text, flags=re.IGNORECASE)
    if text != original:
        log.append({
            "start": start,
            "rule": rule,
            "original": original,
            "cleaned": text
        })
    return text


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def sentence_case(text: str) -> str:
    if not text:
        return text
    return text[0].upper() + text[1:]


def ensure_terminal_punctuation(text: str) -> str:
    if not text:
        return text
    if text.endswith((".", "?", "!", "…")):
        return text
    return text + "."


def title_caps(text: str) -> str:
    replacements = {
        " village ": " Village ",
        " board ": " Board ",
        " mayor ": " Mayor ",
        " trustee ": " Trustee ",
        " clerk ": " Clerk ",
        " chief ": " Chief ",
        " director ": " Director ",
        " village manager ": " Village Manager ",
        " village attorney ": " Village Attorney ",
        " raec ": " RAEC "
    }
    padded = f" {text} "
    for wrong, correct in replacements.items():
        padded = re.sub(re.escape(wrong), correct, padded, flags=re.IGNORECASE)
    return padded.strip()


def normalize_legislative_numbers(text: str, log: list, start: float) -> str:
    original = text

    text = re.sub(r"(?i)\b(ordinance|resolution)\s+26[, ]*(\d{4})\b", r"\1 26-\2", text)
    text = re.sub(r"(?i)\b(ordinance|resolution)\s+2641[ -]?(\d{2})\b", r"\1 26-41\2", text)
    text = re.sub(r"(?i)\b(ordinance|resolution)\s+26\s+(\d{2})\s*(\d{2})\b", r"\1 26-\2\3", text)
    text = re.sub(r"(?i)\b(ordinance|resolution)\s+26[ ,]+(\d{4})\b", r"\1 26-\2", text)
    text = re.sub(r"(?i)\b(schedule)\s+([A-Z])\b", lambda m: f"{m.group(1).title()} {m.group(2)}", text)

    text = re.sub(r"(?i)\bresolution\b", "Resolution", text)
    text = re.sub(r"(?i)\bordinance\b", "Ordinance", text)
    text = re.sub(r"(?i)\bschedule\b", "Schedule", text)
    text = re.sub(r"(?i)\bproclamation\b", "Proclamation", text)
    text = re.sub(r"(?i)\bpublic hearing\b", "Public Hearing", text)

    if text != original:
        log.append({
            "start": start,
            "rule": "legislative_format",
            "original": original,
            "cleaned": text
        })
    return text


def is_vote_word(text: str, vote_words: dict[str, str]) -> bool:
    return text.strip().lower().strip(".?!,") in vote_words


def normalize_vote_text(text: str, vote_words: dict[str, str]) -> str:
    key = text.strip().lower().strip(".?!,")
    return vote_words.get(key, text)


def looks_like_trustee_call(text: str) -> bool:
    t = text.lower().strip()
    return t.startswith("trustee") and len(t.split()) <= 3


def normalize_trustee_call(text: str) -> str:
    text = re.sub(r"(?i)\bpalmer\b", "Palmiter", text)
    text = re.sub(r"(?i)\bgary\b", "Aguirre", text)
    text = re.sub(r"(?i)\bgeary\b", "Aguirre", text)
    text = re.sub(r"(?i)\btrustee\.\s*", "Trustee ", text)
    return sentence_case(normalize_whitespace(text))


def detect_group(segment: dict, corrections: dict) -> bool:
    text = extract_text(segment).lower()
    for trigger in corrections.get("group_triggers", []):
        if trigger in text:
            return True
    return False


def normalize_motion_text(text: str) -> str:
    t = text.strip().lower()
    if t in {"moved", "move", "motion"}:
        return "Motion to approve."
    if t in {"second", "second."}:
        return "Second."
    if t in {"motion carried", "motion carried."}:
        return "Motion carries."
    return text


def build_v2(data: dict, officials: dict, corrections: dict) -> tuple[dict, list, list]:
    segments = data.get("segments", [])
    cleaned = []
    correction_log = []
    error_report = []

    for idx, seg in enumerate(segments):
        new_seg = deepcopy(seg)
        start = float(seg.get("start", 0))
        text = extract_text(seg)
        original_text = text

        if detect_group(seg, corrections):
            new_seg["speaker"] = "Group"

        text = apply_replacements(
            text,
            corrections.get("text_replacements", {}),
            correction_log,
            start,
            "text_replacements"
        )

        text = normalize_motion_text(text)
        text = normalize_legislative_numbers(text, correction_log, start)

        if looks_like_trustee_call(text):
            text = normalize_trustee_call(text)

        prev_text = extract_text(segments[idx - 1]) if idx > 0 else ""
        prev_prev_text = extract_text(segments[idx - 2]) if idx > 1 else ""

        if is_vote_word(text, corrections.get("vote_words", {})):
            if looks_like_trustee_call(prev_text) or "roll call" in prev_prev_text.lower() or "all those in favor" in prev_prev_text.lower():
                new_vote = normalize_vote_text(text, corrections["vote_words"])
                if new_vote != original_text:
                    correction_log.append({
                        "start": start,
                        "rule": "vote_normalization",
                        "original": original_text,
                        "cleaned": new_vote
                    })
                text = new_vote

        text = normalize_whitespace(text)
        text = title_caps(text)
        text = sentence_case(text)

        if text and text.lower() not in {"aye", "nay", "here", "yes", "no"}:
            text = ensure_terminal_punctuation(text)
        elif text:
            text = sentence_case(text.strip(".?!,")) + "."

        rebuild_text_field(new_seg, text)

        if not text:
            error_report.append(f"Blank text at segment starting {start}")

        if re.search(r"\b26[ ,]\d{4}\b", text):
            error_report.append(f"Possible unformatted legislative number at {start}: {text}")

        cleaned.append(new_seg)

    data["segments"] = cleaned
    return data, correction_log, error_report


def main() -> None:
    if len(sys.argv) < 5:
        print("Usage: python clean_transcript.py <input_json> <output_json> <correction_log_json> <error_report_txt> [config_dir]")
        sys.exit(1)

    input_json = sys.argv[1]
    output_json = sys.argv[2]
    correction_log_json = sys.argv[3]
    error_report_txt = sys.argv[4]
    config_dir = sys.argv[5] if len(sys.argv) > 5 else "config"

    data = load_json(input_json)
    officials, corrections = load_config(config_dir)

    cleaned_data, correction_log, error_report = build_v2(data, officials, corrections)

    save_json(output_json, cleaned_data)
    save_json(correction_log_json, correction_log)

    Path(error_report_txt).parent.mkdir(parents=True, exist_ok=True)
    with open(error_report_txt, "w", encoding="utf-8") as f:
        if error_report:
            f.write("\n".join(error_report))
        else:
            f.write("No errors flagged.\n")

    print("V2 cleaning complete.")


if __name__ == "__main__":
    main()
