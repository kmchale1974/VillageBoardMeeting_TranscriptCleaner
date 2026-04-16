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
        r"\bRAEC\b": "RAEC",
        r"\bSchedule A\b": "Schedule A",
        r"\bSchedule B\b": "Schedule B",
        r"\bSchedule C\b": "Schedule C"
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


def looks_like_vote_context(text: str) -> bool:
    t = text.lower()
    triggers = [
        "roll call",
        "all those in favor",
        "signify by saying",
        "nays",
        "motion carried",
        "motion carries",
        "motion denied",
        "consent agenda",
        "trustee",
        "mayor",
        "hearing none"
    ]
    return any(trigger in t for trigger in triggers)


def token_clean(token: str) -> str:
    return token.strip().strip(".,?!;:").lower()


def apply_vote_word_cleanup_to_words(segment: dict, corrections: dict) -> tuple[dict, list[dict]]:
    seg = deepcopy(segment)
    idxs = visible_word_indices(seg)
    log = []

    if not looks_like_vote_context(segment_text_from_words(seg)):
        return seg, log

    for idx in idxs:
        original = str(seg["words"][idx].get("text", ""))
        cleaned = original

        # High-confidence name fixes inside vote/roll call contexts
        cleaned = re.sub(r"(?i)^palmer([.,?!]?)$", r"Palmiter\1", cleaned)
        cleaned = re.sub(r"(?i)^gary([.,?!]?)$", r"Aguirre\1", cleaned)
        cleaned = re.sub(r"(?i)^geary([.,?!]?)$", r"Aguirre\1", cleaned)
        cleaned = re.sub(r"(?i)^carry([.,?!]?)$", r"Aguirre\1", cleaned)
        cleaned = re.sub(r"(?i)^mcgarry([.,?!]?)$", r"Aguirre\1", cleaned)

        # Convert isolated vote words
        key = token_clean(cleaned)
        if key in corrections.get("vote_words", {}):
            normalized = corrections["vote_words"][key]
            punct = cleaned[-1] if cleaned and cleaned[-1] in ".,?!;:" else ""
            cleaned = normalized + punct

        if cleaned != original:
            seg["words"][idx]["text"] = cleaned
            log.append({
                "start": seg["words"][idx].get("start", seg.get("start", 0)),
                "speaker": seg.get("speaker", ""),
                "original": original,
                "cleaned": cleaned,
                "rule": "vote_word_cleanup"
            })

    seg["text"] = segment_text_from_words(seg)
    return seg, log


def normalize_legislative_labels(text: str) -> str:
    text = re.sub(r"(?i)\bresolution\b", "Resolution", text)
    text = re.sub(r"(?i)\bordinance\b", "Ordinance", text)
    text = re.sub(r"(?i)\bproclamation\b", "Proclamation", text)
    text = re.sub(r"(?i)\bschedule\b", "Schedule", text)
    text = re.sub(r"(?i)\bminutes\b", "Minutes", text)
    text = re.sub(r"(?i)\bpublic hearing\b", "Public Hearing", text)
    return text


def normalize_labeled_numbers(text: str, default_year_prefix: str) -> str:
    """
    Examples:
    Resolution 2641 97 -> Resolution 26-4197
    Schedule 826 3603 -> Schedule 26-3603
    Schedule 26 3603 -> Schedule 26-3603
    Minutes 26-1024 stays as-is
    """

    label_group = r"(Resolution|Ordinance|Proclamation|Schedule|Minutes)"

    # Label + 4 digits + 2 digits => YY-NNNN using first two digits as year
    text = re.sub(
        rf"(?i)\b{label_group}\s+(\d{{4}})[\s,.-]+(\d{{2}})\b",
        lambda m: f"{m.group(1).title()} {m.group(2)[:2]}-{m.group(2)[2:]}{m.group(3)}",
        text,
    )

    # Label + 4 digits + 3 digits => YY-NNNN using first two digits of first chunk as year
    # Example: Schedule 2630 602 -> Schedule 26-3602
    text = re.sub(
        rf"(?i)\b{label_group}\s+(\d{{4}})[\s,.-]+(\d{{3}})\b",
        lambda m: f"{m.group(1).title()} {m.group(2)[:2]}-{m.group(2)[2:]}{m.group(3)[-1]}",
        text,
    )

    # Label + odd prefix + 4 digits => fallback to current/default year
    # Example: Schedule 826 3603 -> Schedule 26-3603
    text = re.sub(
        rf"(?i)\b{label_group}\s+\d{{2,3}}[\s,.-]+(\d{{4}})\b",
        lambda m: f"{m.group(1).title()} {default_year_prefix}-{m.group(2)}",
        text,
    )

    # Label + YY + NNNN => YY-NNNN
    text = re.sub(
        rf"(?i)\b{label_group}\s+(\d{{2}})[\s,.-]+(\d{{4}})\b",
        lambda m: f"{m.group(1).title()} {m.group(2)}-{m.group(3)}",
        text,
    )

    # Label + 6 mashed digits => YY-NNNN
    text = re.sub(
        rf"(?i)\b{label_group}\s+(\d{{6}})\b",
        lambda m: f"{m.group(1).title()} {m.group(2)[:2]}-{m.group(2)[2:]}",
        text,
    )

    return text


def normalize_bare_numbers(text: str, default_year_prefix: str) -> str:
    """
    Conservative bare-number normalization:
    2641 97 -> 26-4197
    2630 602 -> 26-3602
    26 3603 -> 26-3603
    826 3603 -> 26-3603 (fallback default year)
    """

    # 4+2 => YY-NNNN
    text = re.sub(
        r"\b(\d{4})[\s,.-]+(\d{2})\b",
        lambda m: f"{m.group(1)[:2]}-{m.group(1)[2:]}{m.group(2)}",
        text,
    )

    # 4+3 => YY-NNNN
    text = re.sub(
        r"\b(\d{4})[\s,.-]+(\d{3})\b",
        lambda m: f"{m.group(1)[:2]}-{m.group(1)[2:]}{m.group(2)[-1]}",
        text,
    )

    # 2+4 => YY-NNNN
    text = re.sub(r"\b(\d{2})[\s,.-]+(\d{4})\b", r"\1-\2", text)

    # 3+4 => default year + NNNN
    text = re.sub(
        r"\b\d{3}[\s,.-]+(\d{4})\b",
        lambda m: f"{default_year_prefix}-{m.group(1)}",
        text,
    )

    # 6 mashed digits => YY-NNNN
    text = re.sub(
        r"\b(\d{6})\b",
        lambda m: f"{m.group(1)[:2]}-{m.group(1)[2:]}",
        text,
    )

    return text


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
    default_year_prefix = str(corrections.get("default_year_prefix", "26"))

    text = apply_phrase_replacements(text, corrections.get("phrase_replacements", {}))
    text = apply_text_replacements(text, corrections.get("text_replacements", {}))
    text = normalize_motion_text(text)
    text = normalize_legislative_labels(text)
    text = normalize_labeled_numbers(text, default_year_prefix)
    text = normalize_bare_numbers(text, default_year_prefix)

    # Cleanup after normalization
    text = re.sub(r"\b(Village of Romeoville) of Romeoville\b", r"\1", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(p\.m\.|a\.m\.)\.+", r"\1", text, flags=re.IGNORECASE)
    text = re.sub(r"\bMinutes\.?\s+Minutes\b", "Minutes", text, flags=re.IGNORECASE)

    text = normalize_whitespace(text)
    text = title_caps(text)
    text = sentence_case(text)

    short_response = text.strip().lower().strip(".")
    if short_response in {"aye", "nay", "here", "yes", "no"}:
        text = sentence_case(short_response) + "."
    elif text:
        text = ensure_terminal_punctuation(text)

    return text


def build_minimal_cleaner(data: dict, corrections: dict) -> tuple[dict, list[dict], list[str]]:
    segments = data.get("segments", [])
    cleaned_segments = []
    correction_log = []
    error_report = []

    for seg in segments:
        original_text = segment_text_from_words(seg)
        working_seg = deepcopy(seg)

        working_seg, vote_log = apply_vote_word_cleanup_to_words(working_seg, corrections)
        correction_log.extend(vote_log)

        current_text = segment_text_from_words(working_seg)
        cleaned_text = clean_text_for_segment(current_text, corrections)
        final_seg = sync_segment_words_to_text(working_seg, cleaned_text)

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

    cleaned_data, correction_log, error_report = build_minimal_cleaner(data, corrections)

    save_json(output_json, cleaned_data)
    save_json(correction_log_json, correction_log)

    Path(error_report_txt).parent.mkdir(parents=True, exist_ok=True)
    with open(error_report_txt, "w", encoding="utf-8") as f:
        if error_report:
            f.write("\n".join(error_report))
        else:
            f.write("No errors flagged.\n")

    print("Minimal conservative cleaning complete.")


if __name__ == "__main__":
    main()
