"""Address quality (E3.1, tasks/E3.1-address-quality.md): a 0–1 completeness score and flags.

Code decides, Gemini reads. The rules always run and need no network. Gemini (optional, cached,
capped) only parses messy text and spots vague wording; every unit it names must be written in the
text and found in the official tables, or it is dropped. The score is computed here from the
verified flags. Model features use the rules only, so training and serving compute the same values.
"""

import hashlib
import logging
import re
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

from app.schemas.common import Address
from app.schemas.enums import AddressFlag
from app.schemas.scoring import AddressCheck
from app.signals.admin_units import PREFIXES, Resolution, fold, normalise, resolve_units
from app.signals.gemini import Gemini

log = logging.getLogger(__name__)
F = AddressFlag
RULES_VERSION = "rules-1"
PROMPT_FILE = Path(__file__).parent / "prompts" / "address.md"
PENALTY = {  # initial weights, to be tuned on the E3.4 evaluation set
    F.PLACEHOLDER_TEXT: 1.0,
    F.MISSING_WARD: 0.35,
    F.UNKNOWN_WARD: 0.35,
    F.MISSING_HOUSE_NUMBER: 0.25,
    F.VAGUE_LANDMARK: 0.25,
    F.WARD_PROVINCE_MISMATCH: 0.25,
    F.MISSING_STREET: 0.15,
    F.MISSING_PROVINCE: 0.10,  # 0 when the ward or district resolves to one province
    F.AMBIGUOUS_NEW_WARD: 0.10,
    F.OLD_ADMIN_NAME: 0.05,  # not a fraud signal: many genuine buyers still write old names
}
LABEL_VI = {
    F.PLACEHOLDER_TEXT: "Địa chỉ không có nghĩa",
    F.MISSING_WARD: "Địa chỉ thiếu phường / xã",
    F.UNKNOWN_WARD: "Không tìm thấy phường / xã này",
    F.MISSING_HOUSE_NUMBER: "Địa chỉ thiếu số nhà",
    F.VAGUE_LANDMARK: "Địa chỉ chỉ mô tả mốc",
    F.WARD_PROVINCE_MISMATCH: "Phường / xã không thuộc tỉnh / thành đã ghi",
    F.MISSING_STREET: "Địa chỉ thiếu tên đường / ngõ / thôn",
    F.MISSING_PROVINCE: "Địa chỉ thiếu tỉnh / thành phố",
    F.AMBIGUOUS_NEW_WARD: "Phường / xã cũ đã tách, chưa rõ thuộc phường / xã mới nào",
    F.OLD_ADMIN_NAME: "Địa chỉ dùng tên đơn vị hành chính trước sáp nhập 2025",
}
# Folded, spaces removed.
PLACEHOLDERS = {
    "abc", "abcd", "abcdef", "xyz", "xxx", "test", "asdf", "qwerty", "na", "none", "null", "koco",
    "khongco", "kco", "kocodiachi", "khongcodiachi", "chuaco", "chuacodiachi", "khongbiet", "kb",
    "diachi", "address", "nodata",
}  # fmt: skip
# Accented phrases that place an address relative to something. A part that starts with one
# describes a landmark, so a number in it ("đối diện trường cấp 2") is not a house number.
RELATIVE = (
    "gần", "đối diện", "cạnh", "kế bên", "bên cạnh", "sát", "sau lưng", "phía sau", "phía trước",
    "trước cổng",
)  # fmt: skip
LANDMARKS = RELATIVE + (
    "đầu ngõ", "cuối ngõ", "đầu hẻm", "cuối hẻm", "ngã ba", "ngã tư", "khu vực", "quanh", "chỗ",
    "chợ", "trường", "cây xăng", "bệnh viện", "ủy ban", "ubnd", "nhà văn hóa", "nhà thờ", "chùa",
)  # fmt: skip
# Folded phrases of delivery instructions: not part of the address, and not vague on their own.
NOTES = (
    "goi truoc", "goi dien", "goi cho", "lien he", "giao gio", "giao hang", "giao trong",
    "giao ngoai", "giao buoi", "giao sang", "giao chieu", "giao toi", "ship", "xem hang",
    "de vo", "nhan hang",
)  # fmt: skip
_TYPE_WORDS = {" ".join(words) for words, _ in PREFIXES}
_DIGIT = re.compile(r"\d")


class AddressReading(BaseModel):
    """Gemini's reading of the address text (response schema). Unit names are claims, checked
    against the text and the official tables; nothing here sets the score."""

    house_number: str | None = None
    street: str | None = None
    ward: str | None = None
    district: str | None = None
    province: str | None = None
    vague_landmark: bool = False
    placeholder_text: bool = False
    missing_house_number: bool = False
    missing_street: bool = False


@lru_cache
def prompt() -> tuple[str, str]:
    """(instruction, version) from prompts/address.md and its front matter."""
    _, meta, body = PROMPT_FILE.read_text(encoding="utf-8").split("---\n", 2)
    version = next(line.split(":", 1)[1].strip() for line in meta.splitlines() if ":" in line)
    return body.strip(), version


def address_key(raw: str) -> str:
    """Hash of the normalised text (E2.3 `address_key`): spellings that differ only in case,
    diacritics, spacing or abbreviations share a key."""
    return hashlib.sha256(normalise(raw).encode()).hexdigest()


def _words(text: str) -> str:
    """Folded words between spaces, for whole-word containment checks."""
    return f" {normalise(text).replace(',', ' ')} "


def is_placeholder(raw: str) -> bool:
    joined = _words(raw).replace(" ", "")
    return not re.search(r"[a-z]", joined) or joined in PLACEHOLDERS or len(set(joined)) == 1


def _is_note(text: str) -> bool:
    words = _words(text)
    return any(f" {note} " in words for note in NOTES)


def _has_phrase(text: str, phrases: tuple[str, ...], *, first: bool = False) -> bool:
    """One of the accented `phrases` is in `text` (at its start, with `first`)."""
    words = " ".join(re.findall(r"[^\W_]+", text.lower()))
    plain = fold(words) == words  # written without diacritics
    for phrase in phrases:
        forms = [phrase]
        # Without diacritics most single words are ambiguous: "cho" is chợ, chỗ or cho.
        if plain and (" " in phrase or phrase == "gần"):
            forms.append(fold(phrase))
        for form in forms:
            if f"{words} ".startswith(f"{form} ") if first else f" {form} " in f" {words} ":
                return True
    return False


def _fields(address: Address | dict) -> tuple[str, str | None, str | None, str | None]:
    if isinstance(address, Address):
        return address.raw, address.street, address.ward, address.province
    return address["raw"], address.get("street"), address.get("ward"), address.get("province")


def _text(raw: str, ward: str | None, province: str | None) -> str:
    """The raw text plus the ward and province fields the shop sent, when the text lacks them."""
    words = _words(raw)
    extra = [part for part in (ward, province) if part and _words(part) not in words]
    return ", ".join([raw, *extra])


def read_address(raw: str, gemini: Gemini, cache=None) -> AddressReading | None:
    """Gemini's reading, from the cache when this text was read with the same prompt version."""
    instruction, version = prompt()
    key = address_key(raw)
    hit = cache.get(key) if cache is not None else None
    if hit and hit.get("version") == version:
        return AddressReading.model_validate(hit["reading"])
    reading = gemini.generate(instruction, raw, AddressReading)
    if reading is not None and cache is not None:
        cache.set(key, {"version": version, "model": gemini.model, "reading": reading.model_dump()})
    return reading


def _written(name: str, words: str) -> bool:
    """`name` without its type word appears in the text (`words` from `_words`)."""
    tokens = normalise(name).replace(",", " ").split()
    for type_words in sorted(_TYPE_WORDS, key=len, reverse=True):
        if " ".join(tokens).startswith(type_words + " "):
            tokens = tokens[len(type_words.split()) :]
            break
    return bool(tokens) and f" {' '.join(tokens)} " in words


def _verified(reading: AddressReading, raw: str, res: Resolution) -> Resolution:
    """Fill a ward the rules missed with one Gemini read, if the text has it and the tables know
    it. Unverifiable parts are dropped, so no flag is ever based on them."""
    if res.ward_status != "missing":
        return res
    words = _words(raw)
    parts = [
        p for p in (reading.ward, reading.district, reading.province) if p and _written(p, words)
    ]
    if not parts:
        return res
    found = resolve_units(", ".join(parts))
    if found.ward_status not in ("resolved", "split") or (
        res.province and found.province and found.province.code != res.province.code
    ):
        return res
    return replace(
        res,
        province=res.province or found.province,
        province_written=res.province_written or found.province_written,
        ward=found.ward,
        ward_candidates=found.ward_candidates,
        ward_status=found.ward_status,
        old_province=res.old_province or found.old_province,
        old_district=res.old_district or found.old_district,
        old_ward=found.old_ward,
        old_names=res.old_names or found.old_names,
        new_names=res.new_names or found.new_names,
    )


def score(flags: set[AddressFlag], *, province_resolved: bool) -> float:
    if F.PLACEHOLDER_TEXT in flags:
        return 0.0
    return round(max(0.0, 1.0 - sum(_penalty(f, province_resolved) for f in flags)), 2)


def _penalty(flag: AddressFlag, province_resolved: bool) -> float:
    return 0.0 if flag == F.MISSING_PROVINCE and province_resolved else PENALTY[flag]


def check_address(
    address: Address | dict, *, gemini: Gemini | None = None, cache=None
) -> AddressCheck:
    """Score and flags for one address. With `gemini`, the text is also read by Gemini (through
    `cache`); any Gemini problem leaves the rules-only result."""
    raw, street_field, ward_field, province_field = _fields(address)
    prompt_version = None
    if is_placeholder(raw):
        return AddressCheck(
            score=0.0,
            flags=[F.PLACEHOLDER_TEXT],
            admin_format="unknown",
            version=RULES_VERSION,
        )
    res = resolve_units(_text(raw, ward_field, province_field))
    reading = read_address(raw, gemini, cache) if gemini is not None else None
    if reading is not None:
        res = _verified(reading, raw, res)
        prompt_version = prompt()[1]

    street_parts = [p for p in res.street_parts if not _is_note(p)]
    if street_field:
        parts = [street_field]
    else:
        parts = street_parts + ([res.street_inline] if res.street_inline else [])
    flags = set()
    if not any(_DIGIT.search(p) for p in parts if not _has_phrase(p, RELATIVE, first=True)):
        flags.add(F.MISSING_HOUSE_NUMBER)
        if any(_has_phrase(p, LANDMARKS) for p in parts):
            flags.add(F.VAGUE_LANDMARK)
    if not parts:
        flags.add(F.MISSING_STREET)
    flags |= {
        "missing": {F.MISSING_WARD},
        "unknown": {F.UNKNOWN_WARD},
        "mismatch": {F.WARD_PROVINCE_MISMATCH},
        "split": {F.AMBIGUOUS_NEW_WARD},
    }.get(res.ward_status, set())
    if not res.province_written:
        flags.add(F.MISSING_PROVINCE)
    if res.admin_format in ("old", "mixed"):
        flags.add(F.OLD_ADMIN_NAME)
    if reading is not None:
        flags |= _gemini_flags(reading, res, flags)

    province_resolved = res.province is not None
    if F.PLACEHOLDER_TEXT in flags:
        flags = {F.PLACEHOLDER_TEXT}
    order = list(F)
    suggested = None
    if res.admin_format in ("old", "mixed") and res.ward and res.province and not res.street_inline:
        suggested = ", ".join([*street_parts, res.ward.name, res.province.name])
    return AddressCheck(
        score=score(flags, province_resolved=province_resolved),
        flags=sorted(flags, key=lambda f: (-_penalty(f, province_resolved), order.index(f))),
        admin_format=res.admin_format if F.PLACEHOLDER_TEXT not in flags else "unknown",
        province=res.province.short if res.province else None,
        ward=res.ward.name if res.ward else None,
        old_province=res.old_province.short if res.old_province else None,
        old_district=res.old_district.name if res.old_district else None,
        old_ward=res.old_ward.name if res.old_ward else None,
        ward_candidates=[w.name for w in res.ward_candidates],
        suggested_raw=suggested if F.PLACEHOLDER_TEXT not in flags else None,
        source="rules+gemini" if reading is not None else "rules",
        version=f"{RULES_VERSION}+{prompt_version}" if prompt_version else RULES_VERSION,
    )


def _gemini_flags(reading: AddressReading, res: Resolution, flags: set) -> set[AddressFlag]:
    """Wording flags Gemini may add. Each is kept only when it does not contradict the rules or
    Gemini's own parts."""
    out = set()
    found_unit = res.province_written or res.ward or res.ward_candidates or res.old_district
    if reading.placeholder_text and not found_unit:
        out.add(F.PLACEHOLDER_TEXT)
    if reading.missing_house_number and not reading.house_number:
        out.add(F.MISSING_HOUSE_NUMBER)  # "Thôn 3" has a digit but no house number
    if reading.missing_street and not reading.street:
        out.add(F.MISSING_STREET)
    if reading.vague_landmark and F.MISSING_HOUSE_NUMBER in flags | out:
        out.add(F.VAGUE_LANDMARK)
    return out


def address_signals(address: Address | dict, *, gemini: Gemini | None = None, cache=None):
    """`signals.address` for the order document, or None if the check fails: an address check
    never blocks order intake or an edit."""
    try:
        return check_address(address, gemini=gemini, cache=cache).model_dump(mode="json")
    except Exception:
        log.exception("Address check failed")
        return None


@lru_cache(maxsize=65_536)
def _rule_features(raw, street, ward, province) -> tuple[float, int, int]:
    check = check_address({"raw": raw, "street": street, "ward": ward, "province": province})
    return check.score, int(F.OLD_ADMIN_NAME in check.flags), int(F.VAGUE_LANDMARK in check.flags)


def address_features(address: dict) -> dict:
    """Model inputs from the rules only (E2.3 address quality group): the same in training and
    serving, with no network call."""
    quality, old_name, vague = _rule_features(*_fields(address))
    return {
        "address_quality_score": quality,
        "address_old_admin_name": old_name,
        "address_vague": vague,
    }
