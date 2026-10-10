"""Privacy helpers applied before text is sent to Gemini."""

import re
import unicodedata

_DIGIT_RUN = re.compile(
    r"(?<!\d)\+?\d(?:[\d\s()./\-\u00b7\u200b-\u200d\u2010-\u2015\u2212\ufeff]*\d)?(?!\d)"
)


def mask_phone_numbers(text: str) -> str:
    """Mask phone-like runs, including digit groups separated by punctuation.

    Conservatively mask long numeric identifiers too; we cannot tell an embedded
    phone number from an unrelated identifier in buyer-controlled text.
    """
    return _DIGIT_RUN.sub(
        lambda match: (
            "[PHONE]"
            if sum(character.isdigit() for character in match.group()) >= 9
            else match.group()
        ),
        text,
    )


def normalize_text(text: str) -> str:
    """Compare Vietnamese text without accents, case or repeated whitespace."""
    folded = unicodedata.normalize("NFKD", text.casefold().replace("đ", "d"))
    return " ".join("".join(c for c in folded if not unicodedata.combining(c)).split())
