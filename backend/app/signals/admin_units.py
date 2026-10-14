"""Vietnamese administrative units before and after the 1 July 2025 merger, and a resolver that
finds them in address text (tasks/E3.1-address-quality.md).

`data/admin_units_2025.json` is built by `scripts/build_admin_units.py`. Names match without case,
diacritics or type prefixes ("P.", "Q.", "TP"), and with common aliases ("HCM", "Sài Gòn", "BRVT").
Matching is literal: a unit is found only when its name is written in the text.
"""

import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

DATA_FILE = Path(__file__).parent / "data" / "admin_units_2025.json"
PROVINCE, WARD = "province", "ward"  # current (2025) units
OLD_PROVINCE, OLD_DISTRICT, OLD_WARD = "old_province", "old_district", "old_ward"
TYPES = ("Thành phố", "Thị trấn", "Thị xã", "Đặc khu", "Tỉnh", "Quận", "Huyện", "Phường", "Xã")
# Type words written before a name (folded, longest first) and the levels they introduce.
PREFIXES = (
    (("thanh", "pho"), (PROVINCE, OLD_PROVINCE, OLD_DISTRICT)),
    (("thi", "tran"), (WARD, OLD_WARD)),
    (("thi", "xa"), (OLD_DISTRICT,)),
    (("dac", "khu"), (WARD,)),
    (("tinh",), (PROVINCE, OLD_PROVINCE)),
    (("quan",), (OLD_DISTRICT,)),
    (("huyen",), (OLD_DISTRICT,)),
    (("phuong",), (WARD, OLD_WARD)),
    (("xa",), (WARD, OLD_WARD)),
)
ALIASES = {  # folded alias -> folded short name of the province
    "hcm": "hochiminh",
    "tphcm": "hochiminh",
    "saigon": "hochiminh",
    "sg": "hochiminh",
    "hn": "hanoi",
    "thuathienhue": "hue",
    "brvt": "bariavungtau",
    "baria": "bariavungtau",
    "vungtau": "bariavungtau",
}
MAX_NAME = 6  # tokens in the longest unit name
_SEGMENT = re.compile(r"[,;()\[\]|\n]+")  # not " - ": it is part of "Bà Rịa - Vũng Tàu"
_TOKEN = re.compile(r"[^\W_]+")
_REWRITES = (  # on lower-case text: abbreviations people write -> the full type word
    (re.compile(r"([^\W\d_])(\d)"), r"\1 \2"),  # q5 -> q 5, phường2 -> phường 2
    (re.compile(r"\btt\b\.?\s*huế\b"), "thừa thiên huế"),
    (re.compile(r"\btp\b\.?\s*"), "thành phố "),
    (re.compile(r"\btx\b\.?\s*"), "thị xã "),
    (re.compile(r"\btt\b\.?\s*"), "thị trấn "),
    (re.compile(r"\b[pf]\b\.?\s*(?=\w)"), "phường "),  # P.2, F2 (Sài Gòn usage)
    (re.compile(r"\bq\b\.?\s*(?=\w)"), "quận "),
    (re.compile(r"\bx\.\s*"), "xã "),
    (re.compile(r"\bh\.\s*"), "huyện "),
)


def fold(text: str) -> str:
    """Lower case without diacritics: 'Phường Láng' -> 'phuong lang'."""
    text = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    return "".join(c for c in text if not unicodedata.combining(c))


def _fold_token(token: str) -> str:
    folded = fold(token)
    return str(int(folded)) if folded.isdigit() else folded  # "Phường 02" = "Phường 2"


def _key(text: str) -> tuple[str, str]:
    """(folded, accented) matching keys of a name: 'Cẩm Giàng' -> ('camgiang', 'cẩmgiàng')."""
    tokens = _TOKEN.findall(unicodedata.normalize("NFC", text.lower()))
    return "".join(_fold_token(t) for t in tokens), "".join(tokens)


@dataclass(frozen=True)
class Unit:
    level: str
    code: str
    name: str  # official name with its type: "Phường Láng", "Thành phố Hồ Chí Minh"
    type: str
    parent: str | None  # ward -> province; old province -> new province; old ward -> old district
    wards: tuple[str, ...] = ()  # old ward or island district -> new ward codes, default first
    key: str = ""
    akey: str = ""

    @property
    def short(self) -> str:
        return self.name[len(self.type) :].strip()


class Tables:
    def __init__(self, data: dict):
        self.data = data
        self.units: dict[tuple[str, str], Unit] = {}
        self.index: dict[str, dict[str, list[Unit]]] = {}
        sources = {
            PROVINCE: "provinces",
            WARD: "wards",
            OLD_PROVINCE: "old_provinces",
            OLD_DISTRICT: "old_districts",
            OLD_WARD: "old_wards",
        }
        for level, source in sources.items():
            self.index[level] = defaultdict(list)
            for code, name, *rest in data[source]:
                kind = next(t for t in TYPES if name.startswith(t + " "))
                key, akey = _key(name[len(kind) :])
                parent = rest[0] if rest else None
                wards = tuple(rest[1]) if len(rest) > 1 else ()
                unit = Unit(level, code, name, kind, parent, wards, key, akey)
                self.units[level, code] = unit
                self.index[level][key].append(unit)
        for level in (PROVINCE, OLD_PROVINCE):
            for alias, target in ALIASES.items():
                if target in self.index[level]:
                    self.index[level][alias] = self.index[level][target]
        self.merged_into: dict[str, set[str]] = defaultdict(set)  # new province -> old provinces
        for unit in self.of(OLD_PROVINCE):
            self.merged_into[unit.parent].add(unit.code)

    def of(self, level: str) -> list[Unit]:
        return [u for (lvl, _), u in self.units.items() if lvl == level]

    def get(self, level: str, code: str | None) -> Unit | None:
        return self.units.get((level, code)) if code else None

    def old_province_of(self, unit: Unit) -> str:
        """Old province code of an old ward or district."""
        district = unit if unit.level == OLD_DISTRICT else self.units[OLD_DISTRICT, unit.parent]
        return district.parent


@lru_cache
def tables() -> Tables:
    return Tables(json.loads(DATA_FILE.read_text(encoding="utf-8")))


@dataclass
class _Segment:
    text: str  # as written
    tokens: list[str]  # lower case, accented, abbreviations expanded
    folded: list[str]


def _segments(text: str) -> list[_Segment]:
    out = []
    for part in _SEGMENT.split(unicodedata.normalize("NFC", text)):
        low = part.lower()
        for pattern, repl in _REWRITES:
            low = pattern.sub(repl, low)
        tokens = _TOKEN.findall(low)
        if tokens:
            out.append(_Segment(part.strip(), tokens, [_fold_token(t) for t in tokens]))
    return out


def normalise(text: str) -> str:
    """Folded text with abbreviations expanded: 'P.2, Q.5, TP.HCM' -> 'phuong 2, quan 5, thanh pho
    hcm'. Equal for spellings that differ only in case, diacritics, spacing or abbreviations."""
    return ", ".join(" ".join(s.folded) for s in _segments(text))


def _prefix_at(folded: list[str], i: int):
    for words, levels in PREFIXES:
        if tuple(folded[i : i + len(words)]) == words:
            return words, levels
    return None


@dataclass(frozen=True)
class _Match:
    level: str
    units: tuple[Unit, ...]
    seg: int
    start: int  # first token, the type word included
    first: int  # first token of the name
    end: int
    prefix: str  # folded type word written before the name, "" when none
    akey: str
    whole: bool  # the name (with its type word) is the whole segment

    @property
    def strong(self) -> bool:
        """Written with a type word, or alone between commas. Bare names inside other text are
        only trusted for provinces: "Láng" in "ngõ 34 Láng" is a street, not the ward."""
        return bool(self.prefix) or self.whole

    @property
    def tokens(self) -> set[tuple[int, int]]:
        return {(self.seg, i) for i in range(self.start, self.end)}

    def size(self) -> int:
        """Words in the name."""
        return self.end - self.first


def _matches(segments: list[_Segment], t: Tables) -> list[_Match]:
    out = []
    for s, seg in enumerate(segments):
        f, a, n = seg.folded, seg.tokens, len(seg.folded)
        inside = set()  # second word of a two-word type ("xã" in "thị xã")
        for i in range(n):
            prefix = None if i in inside else _prefix_at(f, i)
            if prefix:
                words, levels = prefix
                inside.update(range(i + 1, i + len(words)))
                first, kind = i + len(words), "".join(words)
                for j in range(first + 1, min(n, first + MAX_NAME) + 1):
                    key, akey = "".join(f[first:j]), "".join(a[first:j])
                    for level in levels:
                        if units := t.index[level].get(key):
                            whole = i == 0 and j == n
                            out.append(
                                _Match(level, tuple(units), s, i, first, j, kind, akey, whole)
                            )
            for j in range(i + 1, min(n, i + MAX_NAME) + 1):
                key, akey = "".join(f[i:j]), "".join(a[i:j])
                if key.isdigit():  # "Phường 5" needs its type word
                    continue
                whole = i == 0 and j == n
                levels = [PROVINCE, OLD_PROVINCE]
                if whole:
                    levels += [OLD_DISTRICT, WARD, OLD_WARD]
                for level in levels:
                    if units := t.index[level].get(key):
                        out.append(_Match(level, tuple(units), s, i, i, j, "", akey, whole))
    return out


def _narrow(units, match: _Match) -> list[Unit]:
    """Among same-named units in scope, prefer the written type, then the written accents
    ("Cẩm Giang" and "Cẩm Giàng" are two wards of Hải Phòng)."""
    units = list(units)
    if len(units) > 1 and match.prefix:
        units = [u for u in units if fold(u.type).replace(" ", "") == match.prefix] or units
    if len(units) > 1:
        units = [u for u in units if u.akey == match.akey] or units
    return units


@dataclass
class Resolution:
    province: Unit | None = None  # current (2025) province, written or inferred
    ward: Unit | None = None  # current ward, when the text resolves to exactly one
    old_province: Unit | None = None  # merged-away province written in the text
    old_district: Unit | None = None
    old_ward: Unit | None = None
    ward_candidates: list[Unit] = field(default_factory=list)
    # resolved | split | ambiguous (several provinces) | mismatch | unknown | missing
    ward_status: str = "missing"
    province_written: bool = False
    old_names: bool = False  # a name that exists only before the merger
    new_names: bool = False  # a name that exists only after it
    street_parts: list[str] = field(default_factory=list)  # segments before the first unit
    street_inline: str = ""  # words before the first unit inside that unit's segment

    @property
    def admin_format(self) -> str:
        if self.old_names:
            return "mixed" if self.new_names else "old"
        found = self.province or self.ward or self.ward_candidates or self.ward_status != "missing"
        return "new" if found else "unknown"


def resolve_units(text: str) -> Resolution:
    """Find the province, the old district and the ward written in `text`, and map old names to
    the current units. Only names that are in the official tables are returned."""
    t = tables()
    segments = _segments(text)
    matches = _matches(segments, t)
    res, used = Resolution(), set()

    # Province: written with its type word or alone between commas first, then the last one.
    typed = [m for m in matches if m.prefix and m.level not in (PROVINCE, OLD_PROVINCE)]
    provinces = [
        m
        for m in matches
        if m.level in (PROVINCE, OLD_PROVINCE)
        # "Hòa Bình" in "Xã Hòa Bình" names the ward, not the old province
        and not any(
            p.seg == m.seg and p.start < m.start and m.end <= p.end and not m.prefix for p in typed
        )
    ]
    best = max(provinces, key=lambda m: (m.strong, m.seg, m.start, m.end), default=None)
    old_scope = None  # old provinces the district and ward may belong to
    if best:
        same = [m for m in provinces if (m.seg, m.start, m.end) == (best.seg, best.start, best.end)]
        new = next((m.units[0] for m in same if m.level == PROVINCE), None)
        old = next((m.units[0] for m in same if m.level == OLD_PROVINCE), None)
        res.province_written, used = True, best.tokens
        if new:
            res.province, old_scope = new, t.merged_into[new.code]
        else:
            res.province, res.old_province = t.get(PROVINCE, old.parent), old
            res.old_names, old_scope = True, {old.code}

    def in_scope(unit: Unit) -> bool:
        if unit.level == WARD:
            return res.province is None or unit.parent == res.province.code
        return old_scope is None or t.old_province_of(unit) in old_scope

    def new_ward_named(m: _Match) -> bool:
        units = t.index[WARD].get("".join(segments[m.seg].folded[m.first : m.end]), [])
        return any(in_scope(u) for u in units)

    def typed_ward_besides(m: _Match) -> bool:
        return any(
            w.level in (WARD, OLD_WARD) and w.prefix and not (w.tokens & (used | m.tokens))
            for w in matches
        )

    # Old district.
    districts = []
    for m in matches:
        if m.level == OLD_DISTRICT and m.strong and not (m.tokens & used):
            # A bare name that is also a current ward ("Hoàn Kiếm") is read as the ward, unless
            # the province is a merged-away one or a ward is written beside it ("P.5, Gò Vấp").
            if (
                not m.prefix
                and not res.old_province
                and new_ward_named(m)
                and not typed_ward_besides(m)
            ):
                continue
            if units := _narrow([u for u in m.units if in_scope(u)], m):
                districts.append((m, units))
    district_codes = set()
    if districts:
        m, units = max(districts, key=lambda d: (d[0].size(), d[0].seg, d[0].start))
        used = used | m.tokens
        res.old_district, res.old_names = units[0], True
        district_codes = {u.code for u in units}
        if old_scope is None and len({u.parent for u in units}) == 1:
            old_scope = {units[0].parent}
            res.province = t.get(PROVINCE, t.get(OLD_PROVINCE, units[0].parent).parent)

    # Ward: written with its type word first, then the longest name, then the old table first
    # when the text is in the old format.
    old_first = bool(district_codes or res.old_province)
    wards = []
    for m in matches:
        if m.level not in (WARD, OLD_WARD) or not m.strong or m.tokens & used:
            continue
        units = [u for u in m.units if in_scope(u)]
        if m.level == OLD_WARD and district_codes:
            units = [u for u in units if u.parent in district_codes]
        if units := _narrow(units, m):
            wards.append((m, units))
    if wards:
        m, units = max(
            wards,
            key=lambda w: (
                bool(w[0].prefix),
                w[0].size(),
                (w[0].level == OLD_WARD) == old_first,
                w[0].seg,
                w[0].start,
            ),
        )
        used = used | m.tokens
        if m.level == WARD:
            if len({u.parent for u in units}) == 1:
                res.ward, res.ward_status = units[0], "resolved"
                res.province = res.province or t.get(PROVINCE, units[0].parent)
                old_named = t.index[OLD_WARD].get(units[0].key, [])
                scope = t.merged_into[units[0].parent]
                res.new_names = not any(t.old_province_of(u) in scope for u in old_named)
            else:
                res.ward_status = "ambiguous"
        else:
            res.old_ward, res.old_names = units[0], True
            codes = list(dict.fromkeys(c for u in units for c in u.wards))
            res.ward_candidates = [t.units[WARD, c] for c in codes]
            provinces_of = {w.parent for w in res.ward_candidates}
            if len(provinces_of) == 1:
                res.province = res.province or t.get(PROVINCE, provinces_of.pop())
                if len(codes) == 1:
                    res.ward, res.ward_candidates, res.ward_status = (
                        res.ward_candidates[0],
                        [],
                        "resolved",
                    )
                else:
                    res.ward_status = "split"
            else:
                res.ward_candidates, res.ward_status = [], "ambiguous"
    elif res.old_district and res.old_district.wards:  # island district -> special zone
        res.ward, res.ward_status = t.units[WARD, res.old_district.wards[0]], "resolved"
    else:
        mention = _ward_mention(segments, used)
        if mention:
            found = any(
                m.level in (WARD, OLD_WARD) and (m.seg, m.start) == mention for m in matches
            )
            res.ward_status = "mismatch" if found and res.province else "unknown"
            used = used | {mention}

    first = min(used, default=None)
    if first is None:
        res.street_parts = [s.text for s in segments]
    else:
        res.street_parts = [s.text for s in segments[: first[0]]]
        res.street_inline = " ".join(segments[first[0]].tokens[: first[1]])
    return res


def _ward_mention(segments: list[_Segment], used: set) -> tuple[int, int] | None:
    """Position of a ward type word followed by a name ("phường Không Tồn Tại") outside the
    units already found."""
    for s, seg in enumerate(segments):
        i = 0
        while i < len(seg.folded):
            prefix = _prefix_at(seg.folded, i)
            if not prefix:
                i += 1
                continue
            words, levels = prefix
            if WARD in levels and (s, i) not in used and i + len(words) < len(seg.folded):
                return s, i
            i += len(words)
    return None
