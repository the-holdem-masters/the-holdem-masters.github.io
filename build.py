"""구글 시트의 싯드로우를 읽어 seats.js 를 다시 만든다.

사용법:  python build.py            (시트가 링크 공개일 때)
         python build.py 시트.csv   (시트가 제한됨이면 CSV로 내려받아서)
시트가 바뀌면 실행 후 커밋/푸시하면 사이트에 반영된다.

seats.js 에는 이름·전화번호가 그대로 들어가지 않는다.
  키:  sha256("이름") 앞 12자리
  값:  [[테이블, 좌석, 칩량, sha256("이름|뒷4자리") 앞 6자리], ...]
동명이인일 때만 페이지가 뒷번호를 추가로 묻고 마지막 값으로 구분한다.
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
GID = "1982395788"
URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"
OUT = Path(__file__).with_name("seats.js")
# 시트에 번호가 없을 때 쓰는 보충 명단 (이름\t010-****-1234\t칩량). 커밋하지 않는다.
PHONES = Path(__file__).with_name("phones.tsv")


def norm_name(s):
    # index.html 의 normName() 과 반드시 같은 규칙이어야 한다
    s = unicodedata.normalize("NFC", s)
    return re.sub(r"\s+", "", s).upper()


def sha(s, n):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:n]


def name_key(name):
    return sha(norm_name(name), 12)


def phone_key(name, last4):
    return sha(f"{norm_name(name)}|{last4}", 6) if last4 else ""


def load_phones():
    # (이름, 칩량) -> 뒷4자리, 이름 하나뿐이면 이름만으로도 찾는다
    by_chips, by_name = {}, {}
    if not PHONES.exists():
        return by_chips, by_name
    for line in PHONES.read_text(encoding="utf-8-sig").splitlines():
        parts = line.split("\t") + ["", ""]
        digits = re.sub(r"\D", "", parts[1])
        if len(digits) < 4:
            continue
        name, last4 = norm_name(parts[0]), digits[-4:]
        chips = int(re.sub(r"\D", "", parts[2]) or 0)
        by_chips[(name, chips)] = last4
        by_name.setdefault(name, []).append(last4)
    return by_chips, by_name


def read_rows():
    if len(sys.argv) > 1:
        text = Path(sys.argv[1]).read_text(encoding="utf-8-sig")
    else:
        text = urllib.request.urlopen(URL, timeout=30).read().decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text)))


def main():
    by_chips, by_name = load_phones()
    rows = read_rows()

    start = next(i for i, r in enumerate(rows) if r and "상세 싯드로우" in r[0])
    entries, table, problems = [], None, []
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
        if table is None or not r[1].isdigit():
            problems.append(("좌석 정보 없음", r[:6]))
            continue
        digits = re.sub(r"\D", "", r[3])
        chips = int(re.sub(r"\D", "", r[4]) or 0)
        if len(digits) < 4:
            found = by_chips.get((norm_name(r[2]), chips))
            names = by_name.get(norm_name(r[2]), [])
            digits = found or (names[0] if len(names) == 1 else "")
        entries.append((r[2], digits[-4:] if len(digits) >= 4 else "", table, int(r[1]), chips))

    seats, count = {}, {}
    for name, _, _, _, _ in entries:
        count[norm_name(name)] = count.get(norm_name(name), 0) + 1
    for name, last4, table, seat, chips in entries:
        dup = count[norm_name(name)] > 1
        if dup and not last4:
            # 동명이인인데 번호가 없으면 페이지에서 구분할 수 없다
            problems.append(("동명이인·번호 없음 (진행요원 안내 필요)", [name, table, seat]))
        seats.setdefault(name_key(name), []).append(
            [table, seat, chips, phone_key(name, last4) if dup else ""]
        )

    if problems:
        print("확인 필요:", file=sys.stderr)
        for why, p in problems:
            print("  ", why, p, file=sys.stderr)
    if not seats:
        sys.exit("좌석 데이터를 찾지 못했습니다. 시트 형식을 확인하세요.")

    kst = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")
    body = json.dumps(seats, separators=(",", ":"))
    OUT.write_text(
        f'window.SEATS_UPDATED="{kst}";\nwindow.SEATS={body};\n', encoding="utf-8"
    )
    dups = sum(1 for n in count.values() if n > 1)
    tables = len({e[2] for e in entries})
    print(f"{len(entries)}명 / {tables}개 테이블 / 동명이인 {dups}쌍 -> {OUT.name} ({kst} KST)")


if __name__ == "__main__":
    main()
