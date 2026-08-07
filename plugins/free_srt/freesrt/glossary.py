"""Personal glossary validation and Whisper prompt construction."""


def validate_glossary(entries):
    if not isinstance(entries, list) or len(entries) > 500:
        raise ValueError("Glossary must contain no more than 500 entries")
    cleaned, seen = [], set()
    for item in entries:
        if not isinstance(item, dict):
            raise ValueError("Invalid glossary entry")
        source = str(item.get("from", "")).strip()
        replacement = str(item.get("to", "")).strip()
        if not source or len(source) > 100 or len(replacement) > 100:
            raise ValueError("Each glossary entry needs a short From value; To may be empty to delete the term")
        key = source.casefold()
        if key in seen:
            raise ValueError(f"Duplicate glossary term: {source}")
        seen.add(key)
        cleaned.append({"from": source, "to": replacement})
    return cleaned


def build_initial_prompt(entries):
    # Empty replacements are editor deletion rules, not useful Whisper prompt terms.
    terms = [entry["to"] for entry in entries if entry.get("to")]
    return ", ".join(terms)[:1000]

