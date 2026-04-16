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


def visible_words(segment: dict) -> list[dict]:
    return [segment["words"][i] for i in visible_word_indices(segment)]


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


def apply_phrase_replacements(text: str, replacements: dict[str, str]) -> str:
    for wrong, correct in replacements.items():
        text = re.sub(re.escape(wrong), correct, text, flags=re.IGNORECASE)
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


def normalize_labeled_numbers(text: str) -> str:
    # Resolution 2641 97 -> Resolution 26-4197
    text = re.sub(
        r"(?i)\b(Resolution|Ordinance|Proclamation|Schedule)\s+(\d{4})[\s,.-]+(\d{2})\b",
        lambda m: f"{m.group(1).title()} 26-{m.group(2)[2:]}{m.group(3)}",
        text,
    )

    # Resolution 264197 -> Resolution 26-4197
    text = re.sub(
        r"(?i)\b(Resolution|Ordinance|Proclamation|Schedule)\s+(26\d{4})\b",
        lambda m: f"{m.group(1).title()} 26-{m.group(2)[2:]}",
        text,
    )

    # Resolution 26 4197 / 26, 4197 -> Resolution 26-4197
    text = re.sub(
        r"(?i)\b(Resolution|Ordinance|Proclamation|Schedule)\s+26[\s,.-]+(\d{4})\b",
        lambda m: f"{m.group(1).title()} 26-{m.group(2)}",
        text,
    )

    return text


def normalize_bare_26_numbers(text: str) -> str:
    # 2641 97 -> 26-4197
    text = re.sub(
        r"\b(26\d{2})[\s,.-]+(\d{2})\b",
        lambda m: f"26-{m.group(1)[2:]}{m.group(2)}",
        text,
    )

    # 264197 -> 26-4197
    text = re.sub(
        r"\b(26\d{4})\b",
        lambda m: f"26-{m.group(1)[2:]}",
        text,
    )

    # 26 4197 / 26, 4197 -> 26-4197
    text = re.sub(r"\b26[\s,.-]+(\d{4})\b", r"26-\1", text)

    return text


def normalize_legislative_labels(text: str) -> str:
    text = re.sub(r"(?i)\bresolution\b", "Resolution", text)
    text = re.sub(r"(?i)\bordinance\b", "Ordinance", text)
    text = re.sub(r"(?i)\bproclamation\b", "Proclamation", text)
    text = re.sub(r"(?i)\bschedule\b", "Schedule", text)
    text = re.sub(r"(?i)\bpublic hearing\b", "Public Hearing", text)
    return text


def detect_group_from_text(text: str, group_triggers: list[str]) -> bool:
    t = text.lower()
    return any(trigger in t for trigger in group_triggers)


def detect_rollcall_start(text: str, corrections: dict) -> bool:
    t = text.lower()
    return any(p in t for p in corrections.get("rollcall_start_patterns", []))


def detect_rollcall_end(text: str, corrections: dict) -> bool:
    t = text.lower()
    return any(p in t for p in corrections.get("rollcall_end_patterns", []))


def token_clean(token: str) -> str:
    return token.strip().strip(".,?!;:").lower()


def is_vote_word(token: str, corrections: dict) -> bool:
    return token_clean(token) in corrections.get("vote_words", {})


def normalize_vote_token(token: str, corrections: dict) -> str:
    key = token_clean(token)
    normalized = corrections.get("vote_words", {}).get(key, token)
    if token.endswith(".") or token.endswith(","):
        return normalized + token[-1]
    return normalized


def looks_like_rollcall_segment(text: str) -> bool:
    t = text.lower()
    return ("trustee" in t and ("here" in t or "aye" in t or "nay" in t or " i " in f" {t} ")) or "mayor" in t


def apply_rollcall_cleanup_to_words(segment: dict, corrections: dict) -> tuple[dict, list[dict]]:
    seg = deepcopy(segment)
    idxs = visible_word_indices(seg)
    log = []

    for idx in idxs:
        original = str(seg["words"][idx].get("text", ""))
        cleaned = original

        cleaned = re.sub(r"(?i)^palmer([.,?!]?)$", r"Palmiter\1", cleaned)
        cleaned = re.sub(r"(?i)^gary([.,?!]?)$", r"Aguirre\1", cleaned)
        cleaned = re.sub(r"(?i)^geary([.,?!]?)$", r"Aguirre\1", cleaned)
        cleaned = re.sub(r"(?i)^carry([.,?!]?)$", r"Aguirre\1", cleaned)
        cleaned = re.sub(r"(?i)^mcgarry([.,?!]?)$", r"Aguirre\1", cleaned)

        if is_vote_word(cleaned, corrections):
            cleaned = normalize_vote_token(cleaned, corrections)

        if cleaned != original:
            seg["words"][idx]["text"] = cleaned
            log.append({
                "start": seg["words"][idx].get("start", seg.get("start", 0)),
                "speaker": seg.get("speaker", ""),
                "original": original,
                "cleaned": cleaned,
                "rule": "rollcall_cleanup"
            })

    seg["text"] = segment_text_from_words(seg)
    return seg, log


def sync_segment_words_to_text(segment: dict, cleaned_text: str) -> dict:
    seg = deepcopy(segment)
    visible_idxs = visible_word_indices(seg)
    if not visible_idxs:
        seg["text"] = cleaned_text
        return seg

    cleaned_tokens = cleaned_text.split()

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


def clean_text_for_segment(text: str, corrections: dict) -> str:
    text = apply_phrase_replacements(text, corrections.get("phrase_replacements", {}))
    text = apply_text_replacements(text, corrections.get("text_replacements", {}))
    text = normalize_motion_text(text)
    text = normalize_legislative_labels(text)
    text = normalize_labeled_numbers(text)
    text = normalize_bare_26_numbers(text)

    # Cleanup after number normalization
    text = re.sub(r"\b(Village of Romeoville) of Romeoville\b", r"\1", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(p\.m\.|a\.m\.)\.+", r"\1", text, flags=re.IGNORECASE)

    text = normalize_whitespace(text)
    text = title_caps(text)
    text = sentence_case(text)

    short_response = text.strip().lower().strip(".")
    if short_response in {"aye", "nay", "here", "yes", "no"}:
        text = sentence_case(short_response) + "."
    elif text:
        text = ensure_terminal_punctuation(text)

    return text


def build_v32(data: dict, corrections: dict) -> tuple[dict, list[dict], list[str]]:
    segments = data.get("segments", [])
    cleaned_segments = []
    correction_log = []
    error_report = []

    in_rollcall = False

    for seg in segments:
        original_text = segment_text_from_words(seg)
        working_seg = deepcopy(seg)

        if detect_rollcall_start(original_text, corrections):
            in_rollcall = True

        if in_rollcall and looks_like_rollcall_segment(original_text):
            working_seg, rc_log = apply_rollcall_cleanup_to_words(working_seg, corrections)
            correction_log.extend(rc_log)

        current_text = segment_text_from_words(working_seg)
        cleaned_text = clean_text_for_segment(current_text, corrections)
        final_seg = sync_segment_words_to_text(working_seg, cleaned_text)

        if detect_group_from_text(cleaned_text, corrections.get("group_triggers", [])):
            pass

        if cleaned_text != original_text:
            correction_log.append({
                "start": seg.get("start", 0),
                "speaker": seg.get("speaker", ""),
                "original": original_text,
                "cleaned": cleaned_text,
                "rule": "general_cleanup"
            })

        if not cleaned_text:
            error_report.append(f"Blank cleaned text at start={seg.get('start', 0)}")

        cleaned_segments.append(final_seg)

        if detect_rollcall_end(cleaned_text, corrections):
            in_rollcall = False

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

    cleaned_data, correction_log, error_report = build_v32(data, corrections)

    save_json(output_json, cleaned_data)
    save_json(correction_log_json, correction_log)

    Path(error_report_txt).parent.mkdir(parents=True, exist_ok=True)
    with open(error_report_txt, "w", encoding="utf-8") as f:
        if error_report:
            f.write("\n".join(error_report))
        else:
            f.write("No errors flagged.\n")

    print("V3.2 cleaning complete.")


if __name__ == "__main__":
    main()
