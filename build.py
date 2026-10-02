"""구글 시트의 싯드로우를 읽어 seats.js 를 다시 만든다.

사용법:  python build.py
시트가 바뀌면 실행 후 커밋/푸시하면 사이트에 반영된다.

seats.js 에는 이름·전화번호가 그대로 들어가지 않고
sha256("이름|뒷4자리") 앞 12자리만 키로 들어간다.
"""
import csv
import hashlib
import io
import json
import re
import sys
import unicodedata
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

SHEET_ID = "1MLVZFRYAZORiZvW9CNXVQCdnst_FuXPoWOT9t_OFxOo"
URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"
OUT = Path(__file__).with_name("seats.js")


def norm_name(s):
    # index.html 의 normName() 과 반드시 같은 규칙이어야 한다
    s = unicodedata.normalize("NFC", s)
    return re.sub(r"\s+", "", s).upper()


def key(name, last4):
    raw = f"{norm_name(name)}|{last4}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:12]


def main():
    text = urllib.request.urlopen(URL, timeout=30).read().decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))

    start = next(i for i, r in enumerate(rows) if r and "상세 싯드로우" in r[0])
    seats, table, problems = {}, None, []
    for r in rows[start + 2:]:
        r = [c.strip() for c in r] + [""] * 6
        if r[0].startswith("【"):
            break
        m = re.fullmatch(r"Table\s*(\d+)", r[0])
        if m:
            table = int(m.group(1))
            continue
        if not r[2]:
            continue
        digits = re.sub(r"\D", "", r[3])
        if table is None or not r[1].isdigit() or len(digits) < 4:
            problems.append(r[:6])
            continue
        k = key(r[2], digits[-4:])
        if k in seats:
            problems.append(r[:6])
            continue
        chips = int(re.sub(r"\D", "", r[4]) or 0)
        seats[k] = [table, int(r[1]), chips]

    if problems:
        print("확인 필요한 행 (제외됨):", file=sys.stderr)
        for p in problems:
            print("  ", p, file=sys.stderr)
    if not seats:
        sys.exit("좌석 데이터를 찾지 못했습니다. 시트 형식을 확인하세요.")

    kst = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")
    body = json.dumps(seats, separators=(",", ":"))
    OUT.write_text(
        f'window.SEATS_UPDATED="{kst}";\nwindow.SEATS={body};\n', encoding="utf-8"
    )
    tables = len({v[0] for v in seats.values()})
    print(f"{len(seats)}명 / {tables}개 테이블 -> {OUT.name} ({kst} KST)")


if __name__ == "__main__":
    main()
