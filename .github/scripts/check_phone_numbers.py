"""Fail if a tracked file contains what looks like a real Vietnamese, Singapore or Philippine
phone number.

AGENTS.md forbids real phone numbers anywhere in the repo. Use the invalid prefixes +84000...,
+65000... or +63000... for examples. If a match is a false positive, add `pii-allow` on the line.
"""

import re
import subprocess
import sys

PHONE = re.compile(
    r"(?<![\w+])(?:"
    r"(?:\+84|84|0)[235789]\d{8}"  # Vietnam: 0 / 84 / +84, a digit 2-9, 8 digits
    r"|\+65 ?[3689]\d{3} ?\d{4}"  # Singapore: +65, then 3, 6, 8 or 9 and 7 digits
    r"|(?:\+63|0)9\d{2} ?\d{3} ?\d{4}"  # Philippines mobile: +63 / 0, then 9 and 9 digits
    r")(?!\w)"
)
SKIP_SUFFIXES = (".lock", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".woff", ".woff2")
SKIP_NAMES = {"package-lock.json", "pnpm-lock.yaml", "uv.lock"}


def main() -> int:
    files = subprocess.run(
        ["git", "ls-files"], check=True, capture_output=True, text=True
    ).stdout.splitlines()
    hits = []
    for path in files:
        if path.endswith(SKIP_SUFFIXES) or path.rsplit("/", 1)[-1] in SKIP_NAMES:
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                lines = fh.readlines()
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
        for number, line in enumerate(lines, 1):
            if "pii-allow" in line:
                continue
            for match in PHONE.finditer(line):
                hits.append((path, number, match.group()))
    for path, number, value in hits:
        masked = value[:4] + "*" * (len(value) - 7) + value[-3:]
        print(f"::error file={path},line={number}::Possible real phone number {masked}")
    if hits:
        print(f"{len(hits)} possible real phone number(s). Use +84000..., +65000... or "
              "+63000... in examples, "
              "or add `pii-allow` on the line if it is not a phone number.")
        return 1
    print(f"Checked {len(files)} files: no real phone numbers.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
