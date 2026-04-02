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
    with open(Path(config_dir) / "officials.json", "r", encoding="utf-8") as f:
        officials = json.load(f)
    with open(Path(config_dir) / "corrections.json", "r", encoding="utf-8") as f:
        corrections = json.load(f)
    return officials, corrections


def visible_word_indices(segment: dict) -> list[int]:
    idxs = []
    for i, w in enumerate(segment.get("words", [])):
        if w.get("type") != "word":
            continue
        if "disfluency" in w.get("tags", []):
            continue
        txt = str(w.get("text", "")).strip()
        if txt == "":
            continue
        idxs.append(i)
    return idxs


def segment_text_from_words(segment: dict) -> str:
    parts = []
    for i in visible_word_indices(segment):
        parts.append(str(segment["words"][i].get("text", "")).strip())
    text = " ".join(parts)
    text = re.sub(r"\s+([,.;:?!])", r"\1", text)
    return text.strip()


def normalize_whitespace(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,.;:?!])", r"\1", text)
    return text.strip()


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
        r"\bVillage\b": "Village",
        r"\bBoard\b": "Board",
        r"\bMayor\b": "Mayor",
        r"\bTrustee\b": "Trustee",
        r"\bClerk\b": "Clerk",
        r"\bChief\b": "Chief",
        r"\bDirector\b": "Director",
        r"\bVillage Manager\b": "Village Manager",
        r"\bVillage Attorney\b": "Village Attorney",
        r"\bRAEC\b": "RAEC"
    }
    for pat, repl in replacements.items():
        text = re.sub(pat, repl, text, flags=re.IGNORECASE)
    return text


def apply_text_replacements(text: str, replacements: dict[str, str]) -> str:
    for wrong, correct in replacements.items():
        text = re.sub(rf"\b{re.escape(wrong)}\b", correct, text, flags=re.IGNORECASE)
    return text


def normalize_motion_text(text: str) -> str:
    t = text.strip().lower()
    if t in {"moved", "move", "motion", "so moved"}:
        return "Motion to approve."
    if t in {"second", "second."}:
        return "Second."
    if t in {"motion carried", "motion carried."}:
        return "Motion carries."
    return text


def looks_like_trustee_call(text: str) -> bool:
    t = text.strip().lower().rstrip(".")
    return t.startswith("trustee") and len(t.split()) <= 3


def normalize_trustee_call(text: str) -> str:
    text = re.sub(r"(?i)\bpalmer\b", "Palmiter", text)
    text = re.sub(r"(?i)\bgary\b", "Aguirre", text)
    text = re.sub(r"(?i)\bgeary\b", "Aguirre", text)
    text = re.sub(r"(?i)\btrustee\.\s*", "Trustee ", text)
    text = normalize_whitespace(text)
    return sentence_case(text)


def normalize_legislative_numbers(text: str) -> str:
    # Resolution 2641 83 -> Resolution 26-4183
    text = re.sub(r"(?i)\b(Resolution|Ordinance)\s+2641\s*[-, ]?\s*(\d{2})\b", r"\1 26-41\2", text)
    # Resolution 26 4184 -> Resolution 26-4184
    text = re.sub(r"(?i)\b(Resolution|Ordinance)\s+26\s*[-, ]\s*(\d{4})\b", r"\1 26-\2", text)
    # Ordinance 26 2048 -> Ordinance 26-2048
    text = re.sub(r"(?i)\b(Resolution|Ordinance)\s+26\s+(\d{4})\b", r"\1 26-\2", text)
    # Generic capitalization
    text = re.sub(r"(?i)\bresolution\b", "Resolution", text)
    text = re.sub(r"(?i)\bordinance\b", "Ordinance", text)
    text = re.sub(r"(?i)\bschedule\b", "Schedule", text)
    text = re.sub(r"(?i)\bproclamation\b", "Proclamation", text)
    text = re.sub(r"(?i)\bpublic hearing\b", "Public Hearing", text)
    return text


def is_vote_word(text: str, vote_words: dict[str, str]) -> bool:
    key = text.strip().lower().strip(".,?!")
    return key in vote_words


def normalize_vote_text(text: str, vote_words: dict[str, str]) -> str:
    key = text.strip().lower().strip(".,?!")
    return vote_words.get(key, text)


def detect_group_from_text(text: str, group_triggers: list[str]) -> bool:
    t = text.lower()
    return any(trigger in t for trigger in group_triggers)


def sync_segment_words_to_text(segment: dict, cleaned_text: str) -> dict:
    """
    Premiere-safe sync:
    - preserves the original words array length and timing
    - rewrites visible word tokens in place
    - blanks unused extra visible tokens if cleaned text has fewer tokens
    - if cleaned text has more tokens, packs the remaining tail into the last visible token
    """
    seg = deepcopy(segment)
    idxs = visible_word_indices(seg)
    if not idxs:
        seg["text"] = cleaned_text
        return seg

    cleaned_tokens = cleaned_text.split()

    if len(cleaned_tokens) == len(idxs):
        assigned = cleaned_tokens
    elif len(cleaned_tokens) < len(idxs):
        assigned = cleaned_tokens + [""] * (len(idxs) - len(cleaned_tokens))
    else:
        head_count = max(0, len(idxs) - 1)
        assigned = cleaned_tokens[:head_count]
        assigned.append(" ".join(cleaned_tokens[head_count:]))

    for word_idx, token in zip(idxs, assigned):
        seg["words"][word_idx]["text"] = token
        seg["words"][word_idx]["eos"] = token.endswith((".", "?", "!"))

    # Clear any remaining visible words if needed
    if len(assigned) < len(idxs):
        for word_idx in idxs[len(assigned):]:
            seg["words"][word_idx]["text"] = ""
            seg["words"][word_idx]["eos"] = False

    seg["text"] = cleaned_text
    return seg


def clean_text_for_segment(text: str, previous_text: str, two_back_text: str, corrections: dict) -> str:
    text = apply_text_replacements(text, corrections.get("text_replacements", {}))
    text = normalize_motion_text(text)
    text = normalize_legislative_numbers(text)

    if looks_like_trustee_call(text):
        text = normalize_trustee_call(text)

    if is_vote_word(text, corrections.get("vote_words", {})):
        if looks_like_trustee_call(previous_text) or "roll call" in two_back_text.lower() or "all those in favor" in two_back_text.lower():
            text = normalize_vote_text(text, corrections["vote_words"])

    text = normalize_whitespace(text)
    text = title_caps(text)
    text = sentence_case(text)

    short_response = text.strip().lower().strip(".")
    if short_response in {"aye", "nay", "here", "yes", "no"}:
        text = sentence_case(short_response) + "."
    elif text:
        text = ensure_terminal_punctuation(text)

    return text


def build_premiere_safe(data: dict, corrections: dict) -> tuple[dict, list[dict], list[str]]:
    segments = data.get("segments", [])
    cleaned_segments = []
    correction_log = []
    error_report = []

    for i, seg in enumerate(segments):
        original_text = segment_text_from_words(seg)
        prev_text = segment_text_from_words(segments[i - 1]) if i > 0 else ""
        two_back_text = segment_text_from_words(segments[i - 2]) if i > 1 else ""

        cleaned_text = clean_text_for_segment(original_text, prev_text, two_back_text, corrections)

        new_seg = sync_segment_words_to_text(seg, cleaned_text)

        # Optional: only set Group if you are certain Premiere accepts that label in your exported JSON.
        # If speaker IDs are required, do not overwrite speaker here.
        if detect_group_from_text(cleaned_text, corrections.get("group_triggers", [])):
            # Leave speaker unchanged by default for Premiere safety.
            pass

        if cleaned_text != original_text:
            correction_log.append({
                "start": seg.get("start", 0),
                "speaker": seg.get("speaker", ""),
                "original": original_text,
                "cleaned": cleaned_text
            })

        if not cleaned_text:
            error_report.append(f"Blank cleaned text at start={seg.get('start', 0)}")

        if re.search(r"\b(Resolution|Ordinance)\s+26[ ,]\d{4}\b", cleaned_text):
            error_report.append(f"Possible unformatted legislative number at start={seg.get('start', 0)}: {cleaned_text}")

        cleaned_segments.append(new_seg)

    data["segments"] = cleaned_segments
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
    _, corrections = load_config(config_dir)

    cleaned_data, correction_log, error_report = build_premiere_safe(data, corrections)

    save_json(output_json, cleaned_data)
    save_json(correction_log_json, correction_log)

    Path(error_report_txt).parent.mkdir(parents=True, exist_ok=True)
    with open(error_report_txt, "w", encoding="utf-8") as f:
        if error_report:
            f.write("\n".join(error_report))
        else:
            f.write("No errors flagged.\n")

    print("Premiere-safe cleaning complete.")


if __name__ == "__main__":
    main()
