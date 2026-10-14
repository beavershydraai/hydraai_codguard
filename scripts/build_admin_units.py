"""Build backend/app/signals/data/admin_units_2025.json (tasks/E3.1-address-quality.md).

Source: the data files of `vietnamadminunits` (MIT licence, (c) 2025 Tran Ngoc Minh Hieu,
https://github.com/tranngocminhhieu/vietnamadminunits), built from Resolution 202/2025/QH15 and the
2025 commune-level resolutions. The pinned wheel is downloaded from PyPI and checked against its
SHA-256; only its JSON files are read, nothing from it is imported or run.

Run from the repo root with any Python 3.11+ (standard library only):

    python scripts/build_admin_units.py
"""

import hashlib
import io
import json
import sys
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

PACKAGE = "vietnamadminunits"
VERSION = "1.0.4"
WHEEL_URL = (
    "https://files.pythonhosted.org/packages/6e/ce/"
    "69bd8f43fea385cfa8935641f899dd20583e559c8fb3b1bdb9288519f71a/"
    "vietnamadminunits-1.0.4-py3-none-any.whl"
)
WHEEL_SHA256 = "737ee3662e877290386c1c45ed4d71f2e5fae34ab6fb9c64bfb4cb74b216ea35"
OUT = Path(__file__).resolve().parents[1] / "backend/app/signals/data/admin_units_2025.json"
TYPES = ("Thành phố", "Thị trấn", "Thị xã", "Đặc khu", "Tỉnh", "Quận", "Huyện", "Phường", "Xã")
COLUMNS = {
    "provinces": ["code", "name"],
    "wards": ["code", "name", "province"],
    "old_provinces": ["code", "name", "province"],
    "old_districts": ["code", "name", "old_province", "wards"],
    "old_wards": ["code", "name", "old_district", "wards"],
}


def _load() -> tuple[dict, dict, dict]:
    raw = urllib.request.urlopen(WHEEL_URL, timeout=60).read()
    if hashlib.sha256(raw).hexdigest() != WHEEL_SHA256:
        raise SystemExit("Wheel checksum mismatch")
    with zipfile.ZipFile(io.BytesIO(raw)) as wheel:
        files = [
            json.loads(wheel.read(f"{PACKAGE}/data/{name}.json"))
            for name in ("parser_from_2025", "parser_legacy", "converter_2025")
        ]
    return files[0], files[1], files[2]


def _name(name: str) -> str:
    """'Thành Phố Bắc Kạn' -> 'Thành phố Bắc Kạn': the type word in its usual case."""
    kind = next(t for t in TYPES if name.lower().startswith(t.lower() + " "))
    return kind + name[len(kind) :]


def build() -> dict:
    new, legacy, conv = _load()

    provinces = {
        key: (p["provinceCode"], _name(p["province"])) for key, p in new["DICT_PROVINCE"].items()
    }
    ward_code, wards = {}, {}
    for table in ("DICT_PROVINCE_WARD_NO_ACCENTED", "DICT_PROVINCE_WARD_ACCENTED"):
        for pkey, by_ward in new[table].items():
            for wkey, w in by_ward.items():
                ward_code[pkey, wkey] = w["wardCode"]
                wards[w["wardCode"]] = [w["wardCode"], _name(w["ward"]), provinces[pkey][0]]

    old_to_new = {old: new_key for new_key, olds in conv["DICT_PROVINCE"].items() for old in olds}
    old_provinces = {
        key: [p["provinceCode"], _name(p["province"]), provinces[old_to_new[key]][0]]
        for key, p in legacy["DICT_PROVINCE"].items()
    }

    # "province_district_ward" key of an old ward -> new ward codes; the default comes first.
    mapping = {}
    for pkey, by_new in conv["DICT_PROVINCE_WARD_NO_DIVIDED"].items():
        for wkey, olds in by_new.items():
            for old in olds:
                mapping.setdefault(old, []).append(ward_code[pkey, wkey])
    for pkey, by_old in conv["DICT_PROVINCE_WARD_DIVIDED"].items():
        for old, options in by_old.items():
            options = sorted(options, key=lambda o: not o["isDefaultNewWard"])
            mapping[old] = [ward_code[pkey, o["newWardKey"]] for o in options]

    districts, old_wards = {}, {}
    for pkey, by_district in legacy["DICT_PROVINCE_DISTRICT"].items():
        for dkey, d in by_district.items():
            # Island districts had no wards; each became one special zone (đặc khu).
            districts[pkey, dkey] = [
                d["districtCode"],
                _name(d["district"]),
                old_provinces[pkey][0],
                mapping.get(f"{pkey}_{dkey}_", []),
            ]
    for accents in ("NO_ACCENTED", "ACCENTED"):
        for pkey, by_district in legacy[f"DICT_PROVINCE_DISTRICT_WARD_{accents}"].items():
            for dkey, by_ward in by_district.items():
                for wkey, w in by_ward.items():
                    if wkey == "NaN":  # placeholder row of an island district
                        continue
                    old_wards[w["wardCode"]] = [
                        w["wardCode"],
                        _name(w["ward"]),
                        districts[pkey, dkey][0],
                        mapping[f"{pkey}_{dkey}_{wkey}"],
                    ]

    data = {
        "source": f"{PACKAGE} {VERSION} (PyPI), https://github.com/tranngocminhhieu/{PACKAGE}; "
        "from Resolution 202/2025/QH15 and the 2025 commune-level resolutions, "
        "in force 1 July 2025",
        "licence": "MIT, Copyright (c) 2025 Tran Ngoc Minh Hieu",
        "built": date.today().isoformat(),
        "built_by": "scripts/build_admin_units.py",
        "columns": COLUMNS,
        "provinces": sorted([list(p) for p in provinces.values()]),
        "wards": sorted(wards.values()),
        "old_provinces": sorted(old_provinces.values()),
        "old_districts": sorted(districts.values()),
        "old_wards": sorted(old_wards.values()),
    }
    _check(data)
    return data


def _check(data: dict) -> None:
    codes = {w[0] for w in data["wards"]}
    assert len(data["provinces"]) == 34, len(data["provinces"])
    assert len(codes) == len(data["wards"]) == 3321, len(data["wards"])
    assert len(data["old_provinces"]) == 63, len(data["old_provinces"])
    assert all(w[3] and set(w[3]) <= codes for w in data["old_wards"])
    assert all(set(d[3]) <= codes for d in data["old_districts"])


def dump(data: dict) -> str:
    """One row per line, so a data update shows up as a readable diff."""
    lines = ["{"]
    for key, value in data.items():
        if isinstance(value, list):
            rows = ",\n".join("  " + json.dumps(row, ensure_ascii=False) for row in value)
            lines.append(f'"{key}": [\n{rows}\n],')
        else:
            lines.append(f'"{key}": {json.dumps(value, ensure_ascii=False)},')
    lines[-1] = lines[-1].rstrip(",")
    return "\n".join(lines + ["}", ""])


def main() -> int:
    data = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(dump(data), encoding="utf-8", newline="\n")
    sizes = {k: len(v) for k, v in data.items() if isinstance(v, list)}
    print(f"Wrote {OUT}: {sizes}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
