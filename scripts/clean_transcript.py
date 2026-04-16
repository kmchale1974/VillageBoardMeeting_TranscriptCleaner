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


def visible_words(segment: dict) -> list[dict]:
    out = []
    for w in segment.get("words", []):
        if w.get("type") != "word":
            continue
        if "disfluency" in w.get("tags", []):
            continue
        txt = str(w.get("text", "")).strip()
        if txt == "":
            continue
        out.append(w)
    return out


def segment_text_from_words(segment: dict) -> str:
    parts = [str(w.get("text", "")).strip() for w in visible_words(segment)]
    text = " ".join(parts)
    return re.sub(r"\s+([,.;:?!])", r"\1", text).strip()


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


def normalize_legislative_numbers(text: str) -> str:
    text = re.sub(r"(?i)\b(Resolution|Ordinance)\s+2641\s*[-, ]?\s*(\d{2})\b", r"\1 26-41\2", text)
    text = re.sub(r"(?i)\b(Resolution|Ordinance)\s+26\s*[-, ]\s*(\d{4})\b", r"\1 26-\2", text)
    text = re.sub(r"(?i)\b(Resolution|Ordinance)\s+26\s+(\d{4})\b", r"\1 26-\2", text)
    text = re.sub(r"(?i)\bresolution\b", "Resolution", text)
    text = re.sub(r"(?i)\bordinance\b", "Ordinance", text)
    text = re.sub(r"(?i)\bschedule\b", "Schedule", text)
    text = re.sub(r"(?i)\bproclamation\b", "Proclamation", text)
    text = re.sub(r"(?i)\bpublic hearing\b", "Public Hearing", text)
    return text


def detect_group_from_text(text: str, group_triggers: list[str]) -> bool:
    t = text.lower()
    return any(trigger in t for trigger in group_triggers)


def clone_segment_with_word_slice(segment: dict, start_idx: int, end_idx: int, speaker_value: str | None = None) -> dict:
    new_seg = deepcopy(segment)
    words = visible_words(segment)
    sliced = words[start_idx:end_idx]
    new_seg["words"] = deepcopy(sliced)

    if sliced:
        new_seg["start"] = float(sliced[0]["start"])
        end_time = float(sliced[-1]["start"]) + float(sliced[-1]["duration"])
        new_seg["duration"] = round(end_time - float(sliced[0]["start"]), 6)
    else:
        new_seg["duration"] = 0

    if speaker_value is not None:
        new_seg["speaker"] = speaker_value

    new_seg["text"] = segment_text_from_words(new_seg)
    return new_seg


def detect_rollcall_start(text: str, corrections: dict) -> bool:
    t = text.lower()
    return any(p in t for p in corrections.get("rollcall_start_patterns", []))


def detect_rollcall_end(text: str, corrections: dict) -> bool:
    t = text.lower()
    return any(p in t for p in corrections.get("rollcall_end_patterns", []))


def tokenize_lower(words: list[dict]) -> list[str]:
    return [str(w.get("text", "")).strip().lower().strip(".,?!") for w in words]


def is_vote_token(token: str, corrections: dict) -> bool:
    return token in corrections.get("vote_words", {})


def normalize_vote_token(token: str, corrections: dict) -> str:
    return corrections.get("vote_words", {}).get(token, token)


def find_trustee_match(tokens: list[str], idx: int, trustee_names: dict[str, str]) -> tuple[int, str, str] | None:
    if idx >= len(tokens):
        return None
    if tokens[idx] != "trustee":
        return None
    if idx + 1 >= len(tokens):
        return None

    name_token = tokens[idx + 1]
    if name_token in trustee_names:
        return idx + 2, name_token, f"Trustee {name_token.title()}."
    return None


def split_rollcall_segment(segment: dict, corrections: dict, correction_log: list[dict]) -> list[dict]:
    words = visible_words(segment)
    tokens = tokenize_lower(words)
    trustee_names = corrections.get("trustee_names", {})

    out = []
    i = 0
    while i < len(tokens):
        trustee_match = find_trustee_match(tokens, i, trustee_names)
        if trustee_match:
            next_idx, name_token, call_text = trustee_match

            clerk_seg = clone_segment_with_word_slice(segment, i, next_idx)
            clerk_seg["text"] = f"Trustee {name_token.title()}."
            out.append(clerk_seg)

            if next_idx < len(tokens) and is_vote_token(tokens[next_idx], corrections):
                vote_seg = clone_segment_with_word_slice(segment, next_idx, next_idx + 1)
                vote_seg["text"] = normalize_vote_token(tokens[next_idx], corrections) + "."
                out.append(vote_seg)
                correction_log.append({
                    "start": vote_seg.get("start", 0),
                    "speaker": vote_seg.get("speaker", ""),
                    "original": words[next_idx]["text"],
                    "cleaned": vote_seg["text"]
                })
                i = next_idx + 1
                continue

            i = next_idx
            continue

        if is_vote_token(tokens[i], corrections):
            vote_seg = clone_segment_with_word_slice(segment, i, i + 1)
            vote_seg["text"] = normalize_vote_token(tokens[i], corrections) + "."
            out.append(vote_seg)
            i += 1
            continue

        misc_seg = clone_segment_with_word_slice(segment, i, i + 1)
        misc_seg["text"] = sentence_case(normalize_whitespace(segment_text_from_words(misc_seg)))
        if misc_seg["text"]:
            misc_seg["text"] = ensure_terminal_punctuation(misc_seg["text"])
            out.append(misc_seg)
        i += 1

    return out if out else [segment]


def preprocess_rollcall_blocks(segments: list[dict], corrections: dict, correction_log: list[dict]) -> list[dict]:
    processed = []
    in_rollcall = False

    for seg in segments:
        text = segment_text_from_words(seg)

        if detect_rollcall_start(text, corrections):
            in_rollcall = True
            processed.append(seg)
            continue

        if in_rollcall:
            if detect_rollcall_end(text, corrections):
                processed.append(seg)
                in_rollcall = False
                continue

            split_segments = split_rollcall_segment(seg, corrections, correction_log)
            processed.extend(split_segments)
        else:
            processed.append(seg)

    return processed


def clean_text_for_segment(text: str, previous_text: str, two_back_text: str, corrections: dict) -> str:
    text = apply_text_replacements(text, corrections.get("text_replacements", {}))
    text = normalize_motion_text(text)
    text = normalize_legislative_numbers(text)

    if text.strip().lower().strip(".,?!") in corrections.get("vote_words", {}):
        if "trustee" in previous_text.lower() or "roll call" in two_back_text.lower() or "all those in favor" in two_back_text.lower():
            text = corrections["vote_words"][text.strip().lower().strip(".,?!")]

    text = normalize_whitespace(text)
    text = title_caps(text)
    text = sentence_case(text)

    short_response = text.strip().lower().strip(".")
    if short_response in {"aye", "nay", "here", "yes", "no"}:
        text = sentence_case(short_response) + "."
    elif text:
        text = ensure_terminal_punctuation(text)

    return text


def sync_segment_words_to_text(segment: dict, cleaned_text: str) -> dict:
    seg = deepcopy(segment)
    words = visible_words(seg)
    if not words:
        seg["text"] = cleaned_text
        return seg

    cleaned_tokens = cleaned_text.split()
    visible_idxs = []
    for idx, w in enumerate(seg.get("words", [])):
        if w.get("type") != "word":
            continue
        if "disfluency" in w.get("tags", []):
            continue
        txt = str(w.get("text", "")).strip()
        if txt == "":
            continue
        visible_idxs.append(idx)

    if len(cleaned_tokens) == len(visible_idxs):
        assigned = cleaned_tokens
    elif len(cleaned_tokens) < len(visible_idxs):
        assigned = cleaned_tokens + [""] * (len(visible_idxs) - len(cleaned_tokens))
    else:
        head_count = max(0, len(visible_idxs) - 1)
        assigned = cleaned_tokens[:head_count]
        assigned.append(" ".join(cleaned_tokens[head_count:]))

    for word_idx, token in zip(visible_idxs, assigned):
        seg["words"][word_idx]["text"] = token
        seg["words"][word_idx]["eos"] = token.endswith((".", "?", "!"))

    seg["text"] = cleaned_text
    return seg


def build_v3(data: dict, corrections: dict) -> tuple[dict, list[dict], list[str]]:
    original_segments = data.get("segments", [])
    correction_log = []
    error_report = []

    segments = preprocess_rollcall_blocks(original_segments, corrections, correction_log)

    cleaned_segments = []
    for i, seg in enumerate(segments):
        original_text = segment_text_from_words(seg)
        prev_text = segment_text_from_words(segments[i - 1]) if i > 0 else ""
        two_back_text = segment_text_from_words(segments[i - 2]) if i > 1 else ""

        cleaned_text = clean_text_for_segment(original_text, prev_text, two_back_text, corrections)
        new_seg = sync_segment_words_to_text(seg, cleaned_text)

        if detect_group_from_text(cleaned_text, corrections.get("group_triggers", [])):
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

    cleaned_data, correction_log, error_report = build_v3(data, corrections)

    save_json(output_json, cleaned_data)
    save_json(correction_log_json, correction_log)

    Path(error_report_txt).parent.mkdir(parents=True, exist_ok=True)
    with open(error_report_txt, "w", encoding="utf-8") as f:
        if error_report:
            f.write("\n".join(error_report))
        else:
            f.write("No errors flagged.\n")

    print("V3 cleaning complete.")


if __name__ == "__main__":
    main()
