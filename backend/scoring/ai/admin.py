"""Conservative, offline lookup of the 2025 administrative snapshot."""

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path


def name_key(value: str | None, level: str) -> str:
    """Match spelling/abbreviation variants; never fuzzy-match geographic units."""
    value = unicodedata.normalize("NFD", (value or "").strip().casefold().replace("đ", "d"))
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"[^a-z0-9]+", " ", value).strip()
    prefixes = {
        "province": r"^(?:thanh pho|tinh|tp)\s*",
        "district": r"^(?:thanh pho|quan|huyen|thi xa|q|h|tp|tx)\s*",
        "ward": r"^(?:phuong|xa|thi tran|dac khu|p|x|tt)\s*",
    }
    # The boundary keeps a prefix such as 'p' from consuming 'Phú Cường'.
    value = re.sub(prefixes[level].replace(r"\s*", r"(?:\s+|(?=\d)|$)"), "", value)
    return re.sub(r"\s+", " ", value).strip()


@lru_cache(maxsize=1)
def _table() -> dict:
    return json.loads((Path(__file__).parent / "data" / "admin_units.json").read_text("utf-8"))


def resolve_admin(
    province: str | None, ward: str | None, district: str | None
) -> tuple[str | None, str | None, bool]:
    """Return new province/ward only for a unique, fully sourced match, plus legacy use."""
    table = _table()
    province_key, ward_key, district_key = (
        name_key(province, "province"),
        name_key(ward, "ward"),
        name_key(district, "district"),
    )
    legacy = bool(district_key)
    province_matches = []
    province_is_legacy = False
    for entry in table["provinces"]:
        current_keys = {name_key(value, "province") for value in [entry["name"], *entry["aliases"]]}
        old_keys = {name_key(value, "province") for value in entry["legacy_names"]}
        if province_key in current_keys | old_keys:
            province_matches.append(entry["name"])
            legacy |= province_key in old_keys
            province_is_legacy |= province_key in old_keys
    if len(set(province_matches)) != 1 or not ward_key:
        return None, None, legacy
    canonical_province = province_matches[0]
    source_province_key = (
        province_key if province_is_legacy else name_key(canonical_province, "province")
    )
    # The same spelling can name a new ward and a partly split old ward. Without
    # an administrative version, even an omitted district cannot settle which
    # one the buyer meant. Do not treat current spelling as disambiguation.
    shared_split_name = any(
        ward_key == name_key(old["name"], "ward") and not old["whole_unit"]
        for entry in table["wards"]
        if entry["province"] == canonical_province
        for old in entry["legacy_names"]
    )
    known_current_name = any(
        ward_key == name_key(entry["name"], "ward")
        for entry in table["wards"]
        if entry["province"] == canonical_province
    )
    matches: set[str] = set()
    for entry in table["wards"]:
        if entry["province"] != canonical_province:
            continue
        historical_matches = [
            old
            for old in entry["legacy_names"]
            if ward_key == name_key(old["name"], "ward")
            and source_province_key == name_key(old["province"], "province")
        ]
        # A district or a legacy province declares a historical context. Names
        # shared with new wards then need the old district, not a current-name guess.
        historical_context = bool(district_key) or province_is_legacy
        if historical_matches and (historical_context or not known_current_name):
            legacy = True
        if (
            ward_key == name_key(entry["name"], "ward")
            and not historical_context
            and not shared_split_name
        ):
            matches.add(entry["name"])
        for old in historical_matches:
            if district_key == name_key(old["district"], "district") and old["whole_unit"]:
                matches.add(entry["name"])
        # Explicit new names can include a redundant old district when it lies
        # wholly in the current ward's known parent context.
        if (
            ward_key == name_key(entry["name"], "ward")
            and district_key
            and not historical_matches
            and not shared_split_name
            and not province_is_legacy
            and district_key in {name_key(value, "district") for value in entry["old_districts"]}
        ):
            matches.add(entry["name"])
    if len(matches) == 1:
        return canonical_province, matches.pop(), legacy
    return None, None, legacy
