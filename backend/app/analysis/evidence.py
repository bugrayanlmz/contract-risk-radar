import re
import unicodedata


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = value.translate(
        str.maketrans({"‘": "'", "’": "'", "‚": "'", "“": '"', "”": '"', "„": '"'})
    )
    # Only join letters separated by a hyphen and an actual line break.
    value = re.sub(r"([^\W\d_])[-‐\u00ad][ \t]*\r?\n[ \t]*([^\W\d_])", r"\1\2", value)
    return re.sub(r"\s+", " ", value).strip()


def verify_quote(quote: str | None, text: str) -> bool:
    normalized = normalize_text(quote or "")
    return bool(normalized) and normalized in normalize_text(text)
