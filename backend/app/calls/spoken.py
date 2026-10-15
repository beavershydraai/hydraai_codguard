"""Amounts and dates as the call reads them out. The call instruction reads every `_spoken`
field word for word, so the model never has to turn digits into words itself."""

from datetime import datetime, timedelta

from app.data.orders import VN_TIME
from app.schemas.enums import CallLanguage

_VI_DIGITS = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]
_VI_GROUPS = ["", "nghìn", "triệu", "tỷ"]
_EN_ONES = [
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
    "nineteen",
]  # fmt: skip
_EN_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
_EN_GROUPS = ["", "thousand", "million", "billion"]
_EN_MONTHS = [
    "January", "February", "March", "April", "May", "June", "July", "August", "September",
    "October", "November", "December",
]  # fmt: skip


def _groups(n: int) -> list[int]:
    """Groups of three digits, lowest first: 1_250_000 -> [0, 250, 1]."""
    groups = []
    while True:
        n, rest = divmod(n, 1000)
        groups.append(rest)
        if n == 0:
            return groups


def _vi_three(n: int, full: bool) -> str:
    """0-999 in Vietnamese. `full` reads the hundreds even when they are zero, as in the middle
    of a larger number: 1_005_000 is "một triệu không trăm linh năm nghìn"."""
    hundreds, tens, units = n // 100, n // 10 % 10, n % 10
    words = []
    if hundreds or full:
        words += [_VI_DIGITS[hundreds], "trăm"]
    if tens == 0:
        if units and (hundreds or full):
            words.append("linh")
        if units:
            words.append(_VI_DIGITS[units])
    elif tens == 1:
        words.append("mười")
        if units:
            words.append("lăm" if units == 5 else _VI_DIGITS[units])
    else:
        words += [_VI_DIGITS[tens], "mươi"]
        if units:
            words.append({1: "mốt", 4: "tư", 5: "lăm"}.get(units, _VI_DIGITS[units]))
    return " ".join(words)


def vi_number(n: int) -> str:
    if n == 0:
        return "không"
    groups = _groups(n)
    words = []
    for i in range(len(groups) - 1, -1, -1):
        if groups[i] == 0:
            continue
        words.append(_vi_three(groups[i], full=i < len(groups) - 1))
        if _VI_GROUPS[i]:
            words.append(_VI_GROUPS[i])
    return " ".join(words)


def _en_three(n: int) -> str:
    hundreds, rest = divmod(n, 100)
    words = []
    if hundreds:
        words += [_EN_ONES[hundreds], "hundred"]
    if rest >= 20:
        tens, units = divmod(rest, 10)
        words.append(_EN_TENS[tens] + (f"-{_EN_ONES[units]}" if units else ""))
    elif rest:
        words.append(_EN_ONES[rest])
    return " ".join(words)


def en_number(n: int) -> str:
    if n == 0:
        return "zero"
    groups = _groups(n)
    words = []
    for i in range(len(groups) - 1, -1, -1):
        if groups[i]:
            words.append(_en_three(groups[i]))
            if _EN_GROUPS[i]:
                words.append(_EN_GROUPS[i])
    return " ".join(words)


def amount(vnd: int, language: CallLanguage) -> str:
    """450000 -> "bốn trăm năm mươi nghìn đồng" / "four hundred fifty thousand dong"."""
    if language == CallLanguage.EN:
        return f"{en_number(vnd)} dong"
    return f"{vi_number(vnd)} đồng"


def _part_of_day(hour: int, language: CallLanguage) -> str:
    if language == CallLanguage.EN:
        if 5 <= hour < 12:
            return "morning"
        if 12 <= hour < 18:
            return "afternoon"
        return "evening" if 18 <= hour < 23 else "night"
    if 5 <= hour < 11:
        return "sáng"
    if 11 <= hour < 13:
        return "trưa"
    if 13 <= hour < 18:
        return "chiều"
    return "tối" if 18 <= hour < 23 else "đêm"


def placed_at(at: datetime, now: datetime, language: CallLanguage) -> str:
    """When the order was placed, in Vietnam time: "chiều nay", "tối hôm qua",
    "tối ngày 7 tháng 10" / "this afternoon", "yesterday evening", "on the evening of 7 October"."""
    local, today = at.astimezone(VN_TIME), now.astimezone(VN_TIME).date()
    part = _part_of_day(local.hour, language)
    if language == CallLanguage.EN:
        if local.date() == today:
            return "tonight" if part == "night" else f"this {part}"
        if local.date() == today - timedelta(days=1):
            return "last night" if part == "night" else f"yesterday {part}"
        return f"on the {part} of {local.day} {_EN_MONTHS[local.month - 1]}"
    if local.date() == today:
        return f"{part} nay"
    if local.date() == today - timedelta(days=1):
        return f"{part} hôm qua"
    return f"{part} ngày {local.day} tháng {local.month}"
